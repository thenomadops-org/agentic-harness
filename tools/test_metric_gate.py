#!/usr/bin/env python3
"""Mutation-free tests for the coverage ratchet's rules."""

import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest

MODULE = pathlib.Path(__file__).with_name("metric_gate.py")
spec = importlib.util.spec_from_file_location("metric_gate", MODULE)
metric_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metric_gate)


def metrics(values):
    return dict(zip(metric_gate.METRIC_NAMES, values))


def counts(values):
    return {
        name: {"covered": round(value * 100), "total": 10000}
        for name, value in zip(metric_gate.METRIC_NAMES, values)
    }


BASE = metrics((80.0, 80.0, 80.0))
BASE_COUNTS = counts((80.0, 80.0, 80.0))


def history(previous=(), window=10):
    return {
        "version": 1,
        "window": window,
        "baseline": {"ref": "main-base", "metrics": copy.deepcopy(BASE), "counts": copy.deepcopy(BASE_COUNTS)},
        "merges": [
            {"pr": index + 1, "ref": f"merge-{index + 1}", "metrics": row,
             "counts": counts(tuple(row[name] for name in metric_gate.METRIC_NAMES))}
            for index, row in enumerate(previous)
        ],
    }


def candidate(document, values):
    document = copy.deepcopy(document)
    document["merges"].append({
        "pr": 99,
        "ref": "candidate-head",
        "metrics": metrics(values),
        "counts": counts(values),
    })
    return document


class MetricGateTests(unittest.TestCase):
    def test_slip_in_band_with_sufficient_offset_passes(self):
        doc = candidate(history(), (76.0, 84.8, 80.0))
        problems = metric_gate.evaluate(
            doc, metrics((76.0, 84.8, 80.0)), "pull_request", 99,
            "Metric slip: python_tools 80.00 to 76.00, offset by python_plugin 80.00 to 84.80.",
        )
        self.assertEqual([], problems)

    def test_slip_in_band_without_offset_fails(self):
        doc = candidate(history(), (76.0, 80.0, 80.0))
        problems = metric_gate.evaluate(doc, metrics((76.0, 80.0, 80.0)), "pull_request", 99)
        self.assertTrue(any("below zero" in problem for problem in problems))

    def test_tiny_slip_without_offset_fails(self):
        current = metrics((79.76, 80.0, 80.0))
        doc = candidate(history(), (79.76, 80.0, 80.0))
        problems = metric_gate.evaluate(doc, current, "pull_request", 99)
        self.assertTrue(any("below zero" in problem for problem in problems))

    def test_slip_over_ten_percent_fails_even_with_offset(self):
        doc = candidate(history(), (71.9, 90.0, 80.0))
        body = "Metric slip: python_tools 80.00 to 71.90, offset by python_plugin 80.00 to 90.00."
        problems = metric_gate.evaluate(doc, metrics((71.9, 90.0, 80.0)), "pull_request", 99, body)
        self.assertTrue(any("hard limit" in problem for problem in problems))

    def test_downward_window_rejects_a_further_slip(self):
        rows = [metrics((80 - index, 80, 80)) for index in range(1, 4)]
        doc = candidate(history(rows), (76.0, 85.0, 80.0))
        body = "Metric slip: python_tools 77.00 to 76.00, offset by python_plugin 80.00 to 85.00."
        problems = metric_gate.evaluate(doc, metrics((76.0, 85.0, 80.0)), "pull_request", 99, body)
        self.assertTrue(any("window trends down" in problem for problem in problems))

    def test_five_percent_slip_requires_metric_slip_line(self):
        doc = candidate(history(), (76.0, 85.0, 80.0))
        problems = metric_gate.evaluate(doc, metrics((76.0, 85.0, 80.0)), "pull_request", 99)
        self.assertTrue(any("requires a `Metric slip:`" in problem for problem in problems))

    def test_metric_slip_line_must_name_values_and_offset(self):
        doc = candidate(history(), (76.0, 85.0, 80.0))
        body = "Metric slip: python_tools declined; offset by tests."
        problems = metric_gate.evaluate(doc, metrics((76.0, 85.0, 80.0)), "pull_request", 99, body)
        self.assertTrue(any("must include" in problem for problem in problems))
        self.assertTrue(any("name an improving metric" in problem for problem in problems))

    def test_missing_history_is_a_failure(self):
        with self.assertRaisesRegex(metric_gate.MetricGateError, "missing baseline"):
            metric_gate.evaluate(history(), BASE, "pull_request", 99)

    def test_zero_or_missing_metric_set_is_a_failure(self):
        for report in ({}, {name: 0 for name in metric_gate.METRIC_NAMES[:-1]}):
            with self.subTest(report=report), self.assertRaises(metric_gate.MetricGateError):
                metric_gate.validate_metrics(report)

    def test_coverage_report_requires_nonzero_counts_for_every_metric(self):
        report = {
            "metrics": dict(BASE),
            "counts": {name: {"covered": 1, "total": 2} for name in metric_gate.METRIC_NAMES},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "coverage.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(BASE, metric_gate._read_metrics(path))
            report["counts"][metric_gate.METRIC_NAMES[0]]["total"] = 0
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(metric_gate.MetricGateError, "empty or invalid"):
                metric_gate._read_metrics(path)
            report["counts"][metric_gate.METRIC_NAMES[0]] = {"covered": 1, "total": 2}
            del report["counts"][metric_gate.METRIC_NAMES[1]]
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(metric_gate.MetricGateError, "missing or incomplete"):
                metric_gate._read_metrics(path)

    def test_relative_change_is_relative_and_handles_zero_baseline(self):
        self.assertAlmostEqual(-5.0, metric_gate.relative_change(80, 76))
        self.assertEqual(100.0, metric_gate.relative_change(0, 1))
        self.assertEqual(0.0, metric_gate.relative_change(0, 0))

    def test_history_candidate_must_match_measured_values_and_pr(self):
        doc = candidate(history(), (80.0, 80.0, 80.0))
        with self.assertRaisesRegex(metric_gate.MetricGateError, "do not match"):
            metric_gate.evaluate(doc, metrics((81.0, 80.0, 80.0)), "pull_request", 99)
        with self.assertRaisesRegex(metric_gate.MetricGateError, "this run is PR"):
            metric_gate.evaluate(doc, BASE, "pull_request", 98)

    def test_main_push_fails_if_coverage_differs_from_latest_row(self):
        with tempfile.TemporaryDirectory() as directory:
            history_path = pathlib.Path(directory) / "history.json"
            report_path = pathlib.Path(directory) / "coverage.json"
            event_path = pathlib.Path(directory) / "event.json"
            metric_gate._write_json(history_path, candidate(history(), (80.0, 80.0, 80.0)))
            report_path.write_text(json.dumps({"metrics": metrics((79.0, 80.0, 80.0)),
                                               "counts": BASE_COUNTS}), encoding="utf-8")
            event_path.write_text(json.dumps({"ref": "refs/heads/main"}), encoding="utf-8")
            with self.assertRaisesRegex(metric_gate.MetricGateError, "does not match"):
                metric_gate.check(history_path, report_path, event_path)

    def test_record_trims_old_rows_to_the_configured_window(self):
        document = history([metrics((79.0, 80.0, 80.0)), metrics((78.0, 81.0, 80.0))], window=2)
        with tempfile.TemporaryDirectory() as directory:
            history_path = pathlib.Path(directory) / "history.json"
            report_path = pathlib.Path(directory) / "coverage.json"
            metric_gate._write_json(history_path, document)
            report_path.write_text(json.dumps({"metrics": metrics((79.0, 82.0, 80.0)),
                                               "counts": counts((79.0, 82.0, 80.0))}, indent=2),
                                   encoding="utf-8")
            metric_gate.record(history_path, report_path, 99, "new-head")
            recorded = json.loads(history_path.read_text(encoding="utf-8"))
        self.assertEqual([2, 99], [row["pr"] for row in recorded["merges"]])

    def test_pr_history_must_preserve_main_baseline_window_and_prior_rows(self):
        base = history([metrics((79.0, 80.0, 80.0))])
        original = candidate(base, (80.0, 80.0, 80.0))
        metric_gate.verify_pr_history(original, BASE, BASE_COUNTS, 99, base_history=base)
        mutations = (
            ("baseline", lambda doc: doc["baseline"]["metrics"].update(python_tools=50.0), "baseline"),
            ("earlier row", lambda doc: doc["merges"][0]["metrics"].update(python_tools=50.0), "earlier history"),
            ("window", lambda doc: doc.update(window=9), "window"),
        )
        for label, mutate, message in mutations:
            with self.subTest(mutation=label):
                changed = copy.deepcopy(original)
                mutate(changed)
                with self.assertRaisesRegex(metric_gate.MetricGateError, message):
                    metric_gate.verify_pr_history(changed, BASE, BASE_COUNTS, 99, base_history=base)

    def test_pr_check_uses_main_history_instead_of_the_pr_copy(self):
        main = history([metrics((80.0, 80.0, 80.0))])
        edited = copy.deepcopy(main)
        edited["baseline"]["metrics"] = metrics((50.0, 50.0, 50.0))
        edited["merges"][0]["metrics"] = metrics((50.0, 50.0, 50.0))
        edited = candidate(edited, (50.0, 50.0, 50.0))
        current = metrics((50.0, 50.0, 50.0))
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)
            main_path, pr_path = path / "main.json", path / "pr.json"
            report_path, event_path = path / "current.json", path / "event.json"
            metric_gate._write_json(main_path, main)
            metric_gate._write_json(pr_path, edited)
            report_path.write_text(json.dumps({"metrics": current,
                                               "counts": counts((50.0, 50.0, 50.0))}),
                                   encoding="utf-8")
            event_path.write_text(json.dumps({"action": "opened", "pull_request": {
                "number": 99, "body": "", "base": {"sha": "main-sha"},
                "head": {"sha": "candidate-sha"},
            }}), encoding="utf-8")
            with self.assertRaisesRegex(metric_gate.MetricGateError, "changed the metric baseline"):
                metric_gate.check(pr_path, report_path, event_path, base_history_path=main_path)

    def test_first_pr_bootstrap_must_match_ci_measured_main(self):
        source_ref, source_run = "base-sha", "4100"
        baseline = {"ref": source_ref, "metrics": BASE, "counts": BASE_COUNTS,
                    "bootstrap": {"source_run": source_run, "source_commit": source_ref}}
        doc = candidate({"version": 1, "window": 10, "baseline": baseline, "merges": []},
                        (80.0, 80.0, 80.0))
        metric_gate.validate_history(doc)
        metric_gate.verify_pr_history(doc, BASE, BASE_COUNTS, 99,
                                      bootstrap_report=(BASE, BASE_COUNTS),
                                      base_ref=source_ref)
        doc["baseline"]["metrics"]["python_tools"] = 79.0
        with self.assertRaisesRegex(metric_gate.MetricGateError, "bootstrap baseline"):
            metric_gate.verify_pr_history(doc, BASE, BASE_COUNTS, 99,
                                          bootstrap_report=(BASE, BASE_COUNTS),
                                          base_ref=source_ref)


if __name__ == "__main__":
    unittest.main()
