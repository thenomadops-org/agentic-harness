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


BASE = metrics((80.0, 80.0, 80.0))


def history(previous=(), window=10):
    return {
        "version": 1,
        "window": window,
        "baseline": {"ref": "main-base", "metrics": copy.deepcopy(BASE)},
        "merges": [
            {"pr": index + 1, "ref": f"merge-{index + 1}", "metrics": row}
            for index, row in enumerate(previous)
        ],
    }


def candidate(document, values):
    document = copy.deepcopy(document)
    document["merges"].append({
        "pr": 99,
        "ref": "candidate-head",
        "metrics": metrics(values),
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
            with self.assertRaisesRegex(metric_gate.MetricGateError, "missing or zero"):
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


if __name__ == "__main__":
    unittest.main()
