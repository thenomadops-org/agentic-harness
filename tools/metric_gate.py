#!/usr/bin/env python3
"""Coverage ratchet for agentic-harness; stdlib-only and mutation-free.

The committed history file holds the last `window` main merge measurements.
For a PR, append its measured values with `record` before merging. The gate
checks that candidate against the preceding main value and validates it again
on the resulting main push.
"""

import argparse
import ast
import copy
import datetime
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
METRIC_NAMES = ("python_tools", "python_plugin", "go_sdlc_metrics")
DEFAULT_WINDOW = 10
MAX_WINDOW = 50
MIN_TOOL_TESTS = 7
MIN_PLUGIN_TEST_DIRS = 9


class MetricGateError(ValueError):
    """Invalid, incomplete or failed metric gate input."""


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricGateError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not 0 < value <= 100:
        raise MetricGateError(f"{label} must be a finite, nonzero percentage up to 100")
    return value


def validate_metrics(metrics):
    if not isinstance(metrics, dict) or not metrics:
        raise MetricGateError("coverage report has zero metrics")
    if set(metrics) != set(METRIC_NAMES):
        missing = sorted(set(METRIC_NAMES) - set(metrics))
        extra = sorted(set(metrics) - set(METRIC_NAMES))
        raise MetricGateError(f"coverage metric set mismatch; missing={missing}, extra={extra}")
    return {name: _number(metrics[name], name) for name in METRIC_NAMES}


def relative_change(old, new):
    old, new = float(old), float(new)
    if old == 0:
        return 0.0 if new == 0 else 100.0
    return (new - old) * 100.0 / old


def _validate_counts(counts, label="coverage counts"):
    if not isinstance(counts, dict) or set(counts) != set(METRIC_NAMES):
        raise MetricGateError(f"{label} are missing or incomplete")
    clean = {}
    for name, row in counts.items():
        if not isinstance(row, dict):
            raise MetricGateError(f"{label} for {name} are malformed")
        covered, total = row.get("covered"), row.get("total")
        if (isinstance(covered, bool) or not isinstance(covered, int) or covered <= 0
                or isinstance(total, bool) or not isinstance(total, int) or total <= 0
                or covered > total):
            raise MetricGateError(f"{label} for {name} are empty or invalid")
        clean[name] = {"covered": covered, "total": total}
    return clean


def _read_report(path):
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MetricGateError(f"cannot read coverage metrics {path}: {exc}") from None
    if not isinstance(document, dict):
        raise MetricGateError("coverage report must be an object")
    metrics = document.get("metrics")
    return validate_metrics(metrics), _validate_counts(document.get("counts"), "coverage report counts")


def _read_metrics(path):
    return _read_report(path)[0]


def load_history(path):
    try:
        history = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MetricGateError(f"cannot read committed metric history {path}: {exc}") from None
    return validate_history(history)


def validate_history(history):
    if not isinstance(history, dict) or history.get("version") != 1:
        raise MetricGateError("metric history must be a version 1 object")
    window = history.get("window")
    if isinstance(window, bool) or not isinstance(window, int) or not 1 <= window <= MAX_WINDOW:
        raise MetricGateError(f"metric history window must be from 1 to {MAX_WINDOW}")
    baseline = history.get("baseline")
    if not isinstance(baseline, dict) or not isinstance(baseline.get("ref"), str) or not baseline["ref"]:
        raise MetricGateError("metric history has no baseline ref")
    if set(baseline) not in ({"ref", "metrics", "counts"},
                              {"ref", "metrics", "counts", "bootstrap"}):
        raise MetricGateError("metric history baseline has unexpected fields")
    baseline["metrics"] = validate_metrics(baseline.get("metrics"))
    baseline["counts"] = _validate_counts(baseline.get("counts"), "baseline counts")
    if not isinstance(baseline.get("ref"), str) or not baseline["ref"]:
        raise MetricGateError("metric history baseline has no source ref")
    bootstrap = baseline.get("bootstrap")
    if bootstrap is not None:
        if (not isinstance(bootstrap, dict)
                or not isinstance(bootstrap.get("source_run"), str)
                or not bootstrap["source_run"]
                or bootstrap.get("source_commit") != baseline["ref"]):
            raise MetricGateError("bootstrap baseline must name its source run and main commit")
    merges = history.get("merges")
    if not isinstance(merges, list):
        raise MetricGateError("metric history merges must be a list")
    if len(merges) > window:
        raise MetricGateError(f"metric history has {len(merges)} rows, above its {window}-merge window")
    seen = set()
    for row in merges:
        if not isinstance(row, dict):
            raise MetricGateError("metric history contains a malformed merge row")
        if set(row) != {"pr", "ref", "metrics", "counts"}:
            raise MetricGateError("metric history merge row has unexpected fields")
        pr = row.get("pr")
        if isinstance(pr, bool) or not isinstance(pr, int) or pr < 1:
            raise MetricGateError("each metric history row needs a positive PR number")
        if pr in seen:
            raise MetricGateError(f"duplicate PR #{pr} in metric history")
        seen.add(pr)
        if not isinstance(row.get("ref"), str) or not row["ref"]:
            raise MetricGateError(f"metric history PR #{pr} has no run ref")
        row["metrics"] = validate_metrics(row.get("metrics"))
        row["counts"] = _validate_counts(row.get("counts"), f"PR #{pr} counts")
    return history


def record(history_path, metrics_path, pr, ref):
    history = load_history(history_path)
    metrics, counts = _read_report(metrics_path)
    if isinstance(pr, bool) or not isinstance(pr, int) or pr < 1:
        raise MetricGateError("--pr must be a positive pull request number")
    if not ref:
        raise MetricGateError("--ref is required")
    row = {"pr": pr, "ref": ref, "metrics": metrics, "counts": counts}
    merges = history["merges"]
    if merges and merges[-1]["pr"] == pr:
        merges[-1] = row
    elif any(existing["pr"] == pr for existing in merges):
        raise MetricGateError(f"PR #{pr} is already recorded before the history tail")
    else:
        merges.append(row)
    history["merges"] = merges[-history["window"]:]
    _write_json(history_path, history)


def verify_pr_history(pr_history, current_metrics, current_counts, pr_number,
                      base_history=None, bootstrap_report=None, base_ref=None,
                      source_run=None):
    """Prove a PR changes main's committed history only by its candidate row."""
    current_metrics = validate_metrics(current_metrics)
    current_counts = _validate_counts(current_counts, "measured coverage counts")
    if base_history is None:
        if (not isinstance(bootstrap_report, tuple) or len(bootstrap_report) != 2
                or not base_ref or not source_run):
            raise MetricGateError("first metric history requires a CI-measured main bootstrap")
        base_metrics, base_counts = bootstrap_report
        if set(pr_history) != {"version", "window", "baseline", "merges"}:
            raise MetricGateError("bootstrap history has unexpected fields")
        baseline = pr_history["baseline"]
        if pr_history["window"] != DEFAULT_WINDOW:
            raise MetricGateError("bootstrap history must start with the default 10-merge window")
        if (baseline.get("ref") != base_ref
                or baseline.get("metrics") != base_metrics
                or baseline.get("counts") != base_counts
                or baseline.get("bootstrap") != {
                    "source_run": str(source_run),
                    "source_commit": base_ref,
                }):
            raise MetricGateError("bootstrap baseline does not match this CI measurement of main")
        previous_rows = []
    else:
        base = (load_history(base_history) if isinstance(base_history, (str, Path))
                else validate_history(copy.deepcopy(base_history)))
        if {key: value for key, value in pr_history.items() if key != "merges"} != {
                key: value for key, value in base.items() if key != "merges"}:
            if pr_history["window"] != base["window"]:
                raise MetricGateError("PR changed the metric history window from main")
            if pr_history["baseline"] != base["baseline"]:
                raise MetricGateError("PR changed the metric baseline from main")
            raise MetricGateError("PR changed metric history metadata from main")
        previous_rows = base["merges"]

    if not pr_history["merges"]:
        raise MetricGateError("PR history must append its measured candidate row")
    row = pr_history["merges"][-1]
    if row["pr"] != pr_number:
        raise MetricGateError(f"history candidate is PR #{row['pr']}, expected PR #{pr_number}")
    if row["metrics"] != current_metrics or row["counts"] != current_counts:
        raise MetricGateError("candidate history values do not match measured PR coverage")
    expected_rows = (previous_rows + [row])[-pr_history["window"]:]
    if pr_history["merges"] != expected_rows:
        raise MetricGateError("PR must preserve main's earlier history and append only its candidate row")
    return row


def _write_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _history_baseline(history, candidate):
    merges = history["merges"]
    if candidate:
        if not merges:
            return history["baseline"]["metrics"], history["baseline"]["ref"], []
        if len(merges) > 1:
            previous = merges[-2]
            return previous["metrics"], f"PR #{previous['pr']} ({previous['ref']})", merges[:-1]
        return history["baseline"]["metrics"], history["baseline"]["ref"], []
    if merges:
        latest = merges[-1]
        return latest["metrics"], f"PR #{latest['pr']} ({latest['ref']})", merges
    return history["baseline"]["metrics"], history["baseline"]["ref"], []


def _window_trend(history, rows):
    snapshots = [history["baseline"]["metrics"], *[row["metrics"] for row in rows]]
    snapshots = snapshots[-history["window"]:]
    if len(snapshots) < 2:
        return 0.0, len(snapshots)
    change = sum(
        relative_change(snapshots[0][name], snapshots[-1][name])
        for name in METRIC_NAMES
    )
    return change, len(snapshots)


def _metric_slip_lines(body):
    return [line.strip() for line in (body or "").splitlines()
            if line.strip().lower().startswith("metric slip:")]


def _fmt(value):
    return f"{value:.2f}"


def _validate_slip_note(body, drops, old, new, changes):
    if not drops:
        return []
    lines = _metric_slip_lines(body)
    errors = []
    if not lines:
        return ["a slip of 5% or more requires a `Metric slip:` line in the PR body"]
    joined = " ".join(lines)
    positive = [name for name, change in changes.items() if change > 0]
    for name in drops:
        if name.lower() not in joined.lower():
            errors.append(f"Metric slip line does not name {name}")
        if _fmt(old[name]) not in joined or _fmt(new[name]) not in joined:
            errors.append(f"Metric slip line must include {name} values {_fmt(old[name])} and {_fmt(new[name])}")
    if "offset" not in joined.lower() or not any(name.lower() in joined.lower() for name in positive):
        errors.append("Metric slip line must name an improving metric as the offset")
    return errors


def evaluate(history, current, mode, pr_number=None, body=""):
    if mode not in ("pull_request", "main"):
        raise MetricGateError("mode must be pull_request or main")
    current = validate_metrics(current)
    merges = history["merges"]
    if mode == "pull_request":
        if not merges:
            raise MetricGateError("missing baseline merge history; metric-gate refuses to pass")
        candidate = merges[-1]
        if pr_number is not None and candidate["pr"] != pr_number:
            raise MetricGateError(
                f"history candidate is PR #{candidate['pr']}, but this run is PR #{pr_number}"
            )
        if candidate["metrics"] != current:
            raise MetricGateError("candidate history values do not match the measured PR coverage")
        old, baseline_ref, prior_rows = _history_baseline(history, True)
    else:
        old, baseline_ref, prior_rows = _history_baseline(history, False)
        if old != current:
            raise MetricGateError("main coverage does not match the latest committed metric history row")
        trend, snapshot_count = _window_trend(history, merges)
        print(f"baseline run: {baseline_ref}")
        for name in METRIC_NAMES:
            print(f"{name}: {old[name]:.2f}% -> {current[name]:.2f}%")
        print("net change: +0.00% (recorded main merge)")
        print(f"window trend: {trend:+.2f}% across {snapshot_count} snapshot(s), window={history['window']}")
        return []

    changes = {name: relative_change(old[name], current[name]) for name in METRIC_NAMES}
    net = sum(changes.values())
    drops = [name for name in METRIC_NAMES if changes[name] <= -5.0]
    slips = [name for name in METRIC_NAMES if changes[name] < 0]
    trend, snapshot_count = _window_trend(history, prior_rows)

    print(f"baseline run: {baseline_ref}")
    for name in METRIC_NAMES:
        print(f"{name}: {old[name]:.2f}% -> {current[name]:.2f}% ({changes[name]:+.2f}% relative)")
    print(f"net change: {net:+.2f}% (sum of relative coverage changes)")
    print(f"window trend: {trend:+.2f}% across {snapshot_count} prior snapshot(s), window={history['window']}")

    problems = []
    for name in slips:
        if -changes[name] > 10.0 + 1e-9:
            problems.append(f"{name} slipped {-changes[name]:.2f}% relative, beyond the 10% hard limit")
    if slips and net < -1e-9:
        problems.append(f"net change {net:+.2f}% is below zero; a slip has no sufficient offset")
    if trend < -1e-9 and slips:
        problems.append(f"the {history['window']}-merge window trends down ({trend:+.2f}%); a further slip fails")
    problems.extend(_validate_slip_note(body, drops, old, current, changes))
    return problems


def _ast_lines(path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise MetricGateError(f"cannot parse coverage source {path}: {exc}") from None
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            lines.add(node.lineno)
    return lines


def _source_files(root, relative):
    directory = root / relative
    if not directory.is_dir():
        raise MetricGateError(f"coverage source directory is missing: {relative}")
    files = sorted(
        path for path in directory.rglob("*.py")
        if "__pycache__" not in path.parts
        and not path.name.startswith("test_")
    )
    if not files:
        raise MetricGateError(f"no production Python coverage subjects under {relative}")
    return files


def _run_python_tests(root, trace_dir):
    tool_tests = sorted((root / "tools").glob("test_*.py"))
    plugin_dirs = sorted({path.parent for path in (root / "plugin").rglob("test_*.py")})
    if len(tool_tests) < MIN_TOOL_TESTS:
        raise MetricGateError(f"found {len(tool_tests)} tools test files; expected at least {MIN_TOOL_TESTS}")
    if len(plugin_dirs) < MIN_PLUGIN_TEST_DIRS:
        raise MetricGateError(
            f"found {len(plugin_dirs)} plugin test directories; expected at least {MIN_PLUGIN_TEST_DIRS}"
        )
    data_dir = trace_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    sitecustomize = trace_dir / "sitecustomize.py"
    source = f'''\
import atexit, json, os, pathlib, sys, trace, uuid
_root = os.path.realpath({str(root)!r})
_out = pathlib.Path({str(data_dir)!r})
_tracer = trace.Trace(count=1, trace=0, ignoredirs=[sys.prefix])
sys.settrace(_tracer.globaltrace)
def _save():
    rows = {{}}
    sys.settrace(None)
    counts = dict(_tracer.results().counts)
    for (filename, lineno), count in counts.items():
        path = os.path.realpath(filename)
        if path == _root or path.startswith(_root + os.sep):
            rows.setdefault(path, []).append(lineno)
    target = _out / (str(os.getpid()) + "-" + uuid.uuid4().hex + ".json")
    target.write_text(json.dumps(rows, sort_keys=True), encoding="utf-8")
atexit.register(_save)
'''
    sitecustomize.write_text(source, encoding="utf-8")
    env = dict(os.environ)
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(trace_dir) + (os.pathsep + current_pythonpath if current_pythonpath else "")
    for test in tool_tests:
        print(f"coverage test: {test.relative_to(root)}")
        try:
            subprocess.run([sys.executable, str(test)], cwd=root, env=env,
                           check=True, text=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            print(exc.stdout or "", end="")
            print(exc.stderr or "", end="", file=sys.stderr)
            raise MetricGateError(f"Python coverage test failed: {test.relative_to(root)}") from None
    for directory in plugin_dirs:
        print(f"coverage tests: {directory.relative_to(root)}")
        try:
            subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", str(directory)],
                cwd=root, env=env, check=True, text=True, capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            print(exc.stdout or "", end="")
            print(exc.stderr or "", end="", file=sys.stderr)
            raise MetricGateError(f"Python coverage tests failed: {directory.relative_to(root)}") from None
    return data_dir


def _executed_lines(data_dir):
    counts = {}
    for path in sorted(data_dir.glob("*.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MetricGateError(f"invalid Python coverage trace {path}: {exc}") from None
        for filename, lines in rows.items():
            counts.setdefault(os.path.realpath(filename), set()).update(int(line) for line in lines)
    return counts


def _python_metric(files, counts):
    all_lines = set()
    hit_lines = set()
    for path in files:
        canonical = os.path.realpath(path)
        executable = _ast_lines(path)
        all_lines.update((canonical, line) for line in executable)
        hit_lines.update((canonical, line) for line in executable & counts.get(canonical, set()))
    total = len(all_lines)
    if total == 0:
        raise MetricGateError("Python coverage has zero executable source lines")
    return 100.0 * len(hit_lines) / total, len(hit_lines), total


def _go_metric(root, scratch):
    modules = sorted(root.rglob("go.mod"))
    if not modules:
        raise MetricGateError("Go coverage module census is empty")
    if len(modules) != 1 or modules[0].parent != root / "tools/sdlc-metrics":
        raise MetricGateError(f"unexpected Go module set: {[str(p.relative_to(root)) for p in modules]}")
    profile = scratch / "go.cover"
    module = modules[0].parent
    print(f"coverage tests: {module.relative_to(root)} (go test -coverprofile)")
    go_tmp, go_cache = scratch / "go-tmp", scratch / "go-cache"
    go_tmp.mkdir()
    go_cache.mkdir()
    env = dict(os.environ, GOTMPDIR=str(go_tmp), GOCACHE=str(go_cache))
    try:
        subprocess.run(
            ["go", "test", "-coverprofile", str(profile), "./..."],
            cwd=module, env=env, check=True, text=True, capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        print(exc.stdout or "", end="")
        print(exc.stderr or "", end="", file=sys.stderr)
        raise MetricGateError("Go coverage tests failed: tools/sdlc-metrics") from None
    statements = covered = 0
    if not profile.is_file():
        raise MetricGateError("go test did not write its coverage profile")
    for raw in profile.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("mode:"):
            continue
        pieces = raw.split()
        if len(pieces) != 3:
            raise MetricGateError(f"malformed Go coverage profile line: {raw!r}")
        count = int(pieces[2])
        statements += int(pieces[1])
        if count > 0:
            covered += int(pieces[1])
    if statements == 0:
        raise MetricGateError("Go coverage profile contains zero statements")
    return 100.0 * covered / statements, covered, statements


def measure(root, output):
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="metric-gate-") as temp:
        scratch = Path(temp)
        trace_data = _run_python_tests(root, scratch / "python-trace")
        executed = _executed_lines(trace_data)
        metrics, counts = {}, {}
        for metric, relative in (("python_tools", "tools"), ("python_plugin", "plugin")):
            value, covered, total = _python_metric(_source_files(root, relative), executed)
            metrics[metric] = value
            counts[metric] = {"covered": covered, "total": total}
        value, covered, total = _go_metric(root, scratch)
        metrics["go_sdlc_metrics"] = value
        counts["go_sdlc_metrics"] = {"covered": covered, "total": total}
    document = {
        "measured_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
        "metrics": metrics,
        "counts": counts,
    }
    _write_json(output, document)
    for name in METRIC_NAMES:
        print(f"{name}: {metrics[name]:.2f}% ({counts[name]['covered']}/{counts[name]['total']})")
    print(f"coverage report: {output}")
    return document


def check(history_path, current_path, event_path, base_history_path=None,
          bootstrap_path=None, source_run=None):
    history = load_history(history_path)
    current, current_counts = _read_report(current_path)
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MetricGateError(f"cannot read GitHub event file {event_path}: {exc}") from None
    action = event.get("action")
    pull = event.get("pull_request")
    if isinstance(pull, dict):
        pr = pull.get("number")
        if isinstance(pr, bool) or not isinstance(pr, int) or pr < 1:
            raise MetricGateError("pull_request event has no valid PR number")
        body = pull.get("body") or ""
        base_sha = pull.get("base", {}).get("sha") if isinstance(pull.get("base"), dict) else None
        head_sha = pull.get("head", {}).get("sha") if isinstance(pull.get("head"), dict) else None
        if base_history_path:
            verify_pr_history(
                history, current, current_counts, pr,
                base_history=base_history_path,
            )
        elif bootstrap_path:
            verify_pr_history(
                history, current, current_counts, pr,
                bootstrap_report=_read_report(bootstrap_path),
                base_ref=base_sha,
                source_run=source_run,
            )
        else:
            raise MetricGateError("PR gate must compare against main's committed metric history")
        if not head_sha or not base_sha:
            raise MetricGateError("pull_request event is missing its head or base commit")
        problems = evaluate(history, current, "pull_request", pr, body)
    elif event.get("ref") == "refs/heads/main":
        if not history["merges"]:
            raise MetricGateError("main has no recorded merge coverage history")
        if history["merges"][-1]["counts"] != current_counts:
            raise MetricGateError("main coverage counts do not match the latest committed history row")
        problems = evaluate(history, current, "main")
    else:
        raise MetricGateError(f"event {action!r} is neither a pull request nor a main push")
    if problems:
        for problem in problems:
            print(f"::error::{problem}")
        print(f"metric-gate: FAILED ({len(problems)} problem(s))")
        return 1
    print("metric-gate: PASS")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    actions = parser.add_subparsers(dest="action", required=True)
    measurement = actions.add_parser("measure", help="run coverage suites and write metrics JSON")
    measurement.add_argument("--repo", default=str(ROOT))
    measurement.add_argument("--out", required=True)
    recorder = actions.add_parser("record", help="append this PR's coverage to committed history")
    recorder.add_argument("--history", required=True)
    recorder.add_argument("--metrics", required=True)
    recorder.add_argument("--pr", type=int, required=True)
    recorder.add_argument("--ref", required=True, help="short tested head ref for the history row")
    checker = actions.add_parser("check", help="evaluate a PR or verify the committed main record")
    checker.add_argument("--history", required=True)
    checker.add_argument("--current", required=True)
    checker.add_argument("--event", required=True, help="GITHUB_EVENT_PATH JSON")
    checker.add_argument("--base-history", help="history file extracted from the PR base commit")
    checker.add_argument("--bootstrap-current", help="CI measurement of main for the first history PR")
    checker.add_argument("--source-run", help="CI run id that measured the bootstrap baseline")
    args = parser.parse_args(argv)
    try:
        if args.action == "measure":
            measure(args.repo, args.out)
            return 0
        if args.action == "record":
            record(args.history, args.metrics, args.pr, args.ref)
            return 0
        return check(args.history, args.current, args.event,
                     args.base_history, args.bootstrap_current, args.source_run)
    except MetricGateError as exc:
        print(f"metric-gate: REFUSED — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
