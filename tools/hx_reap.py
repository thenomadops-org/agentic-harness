#!/usr/bin/env python3
"""`hx reap`: report, and with --close clean up, what finished agents left. Stdlib only.

    hx reap [--close] [--max-age-hours N] [--chat] [--checkout DIR ...]

Report-only unless `--close`. An orphan is:

- a herdr workspace with one pane, labelled the way the launcher labels
  ticket panes, whose pane runs no agent (a bare shell; herdr restores these
  on restart), or whose ticket is Done;
- a worktree git marks prunable, or one that is clean and whose ticket is
  Done (the same guards as `hx done`);
- a scratch Postgres cluster (data directory under a scratch root) whose
  ticket is Done, or that has run past N hours with no client connected and
  no live pane naming its ticket; a container named after a ticket that is
  Done, or after a pull request that is merged or closed;
- a main checkout left on a Done ticket's branch with no changes.

Never touched: a pane with a live agent, any workspace with more than one
pane (the main agent workspace), a protected workspace from the config,
a worktree with changes, a lock, a process inside it or unpushed detached
commits. Old ticket folders under /tmp that are not worktrees are reported
only. The report goes to the state directory; `--chat` posts its summary
with `hx chat post`.
"""

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cleanup  # noqa: E402
from cleanup import CleanupError  # noqa: E402
from hx_done import Host  # noqa: E402


def plan_reap(host, max_age_hours, tmp_root="/tmp"):
    plan = cleanup.Plan()
    projects = host.config["projects"]
    done_cache = {}

    def done(key):
        if key not in done_cache:
            done_cache[key] = cleanup.is_done(host.jira.status(key), host.config["done_statuses"])
        return done_cache[key]

    def keys(*texts):
        return sorted(set().union(*(cleanup.find_keys(t, projects) for t in texts if t)))

    # herdr workspaces
    try:
        spaces = cleanup.herdr_state(host.run)
    except CleanupError as exc:
        plan.notes.append(f"herdr unavailable: {exc}")
        spaces = []
    protected = set(host.config["protect_workspaces"])
    live_keys = set()
    for space in spaces:
        for pane in space.panes:
            if pane.live:
                live_keys.update(keys(pane.label, space.label))
    for space in spaces:
        name = f"{space.workspace_id} {space.label}".strip()
        labels = [p.label for p in space.panes]
        if space.workspace_id in protected or space.label in protected:
            plan.skip("workspace", name, "protected")
            continue
        if len(space.panes) != 1:
            plan.skip("workspace", name, f"{len(space.panes)} panes; shared workspace")
            continue
        pane = space.panes[0]
        if pane.live:
            plan.skip("workspace", name, f"live agent ({pane.agent or ','.join(pane.processes)})")
            continue
        if not any(cleanup.LAUNCHER_LABEL.fullmatch(l or "") for l in labels + [space.label]):
            plan.skip("workspace", name, "bare shell, not a launcher ticket pane")
            continue
        finished = [k for k in keys(pane.label, space.label) if done(k)]
        why = f"ticket Done ({', '.join(finished)})" if finished else "no agent process"
        plan.act("workspace", f"{name} [{pane.label}]",
                 ["herdr", "workspace", "close", space.workspace_id], why)

    # worktrees and main checkouts
    cwds = host.procs.cwds()
    worktree_paths = set()
    for checkout in host.config["checkouts"]:
        try:
            trees = cleanup.worktrees(checkout, host.run)
        except CleanupError as exc:
            plan.notes.append(str(exc))
            continue
        for tree in trees:
            worktree_paths.add(os.path.realpath(tree.path))
            found = keys(tree.path, tree.branch)
            finished = [k for k in found if done(k)]
            if tree.main:
                if tree.branch and tree.branch != host.config["main_branch"] and finished:
                    cleanup.checkout_actions(plan, checkout, host.config["main_branch"],
                                             f"main checkout on Done {finished[0]} branch",
                                             host.run, trees)
                continue
            if tree.prunable:
                cleanup.worktree_action(plan, checkout, tree, "", cwds, host.run)
            elif finished and not [k for k in found if not done(k)]:
                cleanup.worktree_action(plan, checkout, tree,
                                        f"ticket Done ({', '.join(finished)})", cwds, host.run)

    # scratch databases
    limit = max_age_hours * 3600
    for pg in host.procs.postmasters():
        if not host.scratch(pg["datadir"]):
            continue
        found = keys(pg["datadir"])
        finished = [k for k in found if done(k)]
        hours = pg["age"] / 3600
        target = f"{pg['datadir']} (pid {pg['pid']}, up {hours:.1f}h, {pg['clients']} client(s))"
        if finished:
            cleanup.postgres_action(plan, pg, f"ticket Done ({', '.join(finished)})")
        elif pg["age"] > limit and pg["clients"] == 0 and not live_keys.intersection(found):
            cleanup.postgres_action(plan, pg, f"unused past {max_age_hours:g}h")
        else:
            plan.skip("postgres", target, "ticket open or in use")
    boxes = cleanup.containers(host.run)
    if boxes is None:
        plan.notes.append("docker unavailable; containers not checked")
    repos = host.repos()
    for box in boxes or []:
        name = box.get("Names", "")
        found = keys(name)
        if found:
            if all(done(k) for k in found):
                plan.act("container", name, ["docker", "stop", name], f"ticket Done ({', '.join(found)})")
            continue
        scratch = cleanup.SCRATCH_CONTAINER.fullmatch(name)
        if not scratch:
            continue
        states = []
        for repo in repos:
            try:
                states.append(host.github.pr_view(scratch.group(1), repo).get("state"))
            except CleanupError:
                continue
        if states and all(s in ("MERGED", "CLOSED") for s in states):
            plan.act("container", name, ["docker", "stop", name],
                     f"pull request #{scratch.group(1)} {'/'.join(sorted(set(states))).lower()}")
        else:
            plan.skip("container", name, "pull request open or unknown")

    # /tmp ticket folders: report only
    try:
        entries = sorted(os.listdir(tmp_root))
    except OSError:
        entries = []
    stale = []
    for entry in entries:
        path = os.path.join(tmp_root, entry)
        if not os.path.isdir(path) or os.path.realpath(path) in worktree_paths:
            continue
        found = keys(entry)
        if found and all(done(k) for k in found):
            stale.append(entry)
    if stale:
        plan.notes.append(f"{len(stale)} folder(s) under {tmp_root} for Done tickets "
                          f"(report only, not removed): {', '.join(stale[:20])}")
    return plan


def summary(plan, closing):
    counts = {}
    for kind, _target in {(a.kind, a.target) for a in plan.actions}:
        counts[kind] = counts.get(kind, 0) + 1
    verb = "closed" if closing else "would close"
    parts = [f"{n} {kind}" for kind, n in sorted(counts.items())] or ["nothing"]
    return f"agent reaper: {verb} {', '.join(parts)}; skipped {len(plan.skipped)}"


def main(argv=None, host=None, log=None, now=None, post=subprocess.run):
    parser = argparse.ArgumentParser(prog="hx reap", description="report or close agent leftovers")
    parser.add_argument("--close", action="store_true", help="act; default is report only")
    parser.add_argument("--dry-run", action="store_true", help="report only (the default)")
    parser.add_argument("--max-age-hours", type=float, default=None)
    parser.add_argument("--checkout", action="append", default=[])
    parser.add_argument("--config")
    parser.add_argument("--chat", action="store_true", help="post the summary with hx chat")
    parser.add_argument("--tmp-root", default="/tmp")
    args = parser.parse_args(argv)
    closing = args.close and not args.dry_run
    try:
        if host is None:
            host = Host(cleanup.load_config(args.config, checkouts=args.checkout))
        stamp = (now or _dt.datetime.now().astimezone()).strftime("%Y%m%d-%H%M%S")
        log = log or cleanup.Log(cleanup.state_dir() / "reaper" / f"reap-{stamp}.log")
        max_age = args.max_age_hours or host.config["max_scratch_age_hours"]
        log(f"reap {'--close' if closing else 'report only'}: max scratch age {max_age:g}h, "
            f"checkouts {', '.join(host.config['checkouts']) or 'none'}")
        plan = plan_reap(host, max_age, args.tmp_root)
        failures = cleanup.execute(plan, log, not closing, host.run)
        line = summary(plan, closing) + (f"; {failures} failed" if failures else "")
        log(line)
        if args.chat:
            hx = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "hx")
            text = re.sub(r"\s+", " ", line)
            sent = post([sys.executable, hx, "chat", "post", text], check=False)
            if sent.returncode != 0:
                log("chat post failed; the report is still in the log")
        return 1 if failures else 0
    except CleanupError as exc:
        print(f"hx reap: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
