package main

import (
	"strings"
	"testing"
)

func TestSummaryPutsUnmeasuredMetricsFirstAndPrintsNoNumberForThem(t *testing.T) {
	rep := computeFixture(t)
	// Force one metric to be unmeasured so the block is exercised on data
	// where every other metric is real.
	for i := range rep.Metrics {
		if rep.Metrics[i].MetricID == "lagging.defect_containment_rate" {
			rep.Metrics[i].Status = StatusInsufficient
			rep.Metrics[i].Value = 0
			rep.Metrics[i].Subjects = 0
		}
	}
	rep.Sinks = PublishAll(rep, []Sink{NewNotionSink(LoadNotionConfig(env(nil)))})
	s := Summary(rep)

	notMeasured := strings.Index(s, "NOT MEASURED")
	measured := strings.Index(s, "MEASURED — ")
	if notMeasured < 0 {
		t.Fatal("the summary must carry a NOT MEASURED block; an unmeasurable metric buried among the numbers is how it goes unnoticed")
	}
	if measured < notMeasured {
		t.Error("NOT MEASURED must come BEFORE the measured numbers — it is the most interesting line in the document")
	}
	// The census has to be printed, because it is the evidence that the run
	// examined something at all.
	for _, want := range []string{"CENSUS", "pull requests examined 8", "issues examined        6"} {
		if !strings.Contains(s, want) {
			t.Errorf("the summary must contain %q, got:\n%s", want, s)
		}
	}
	// An unconfigured sink is printed, not omitted.
	if !strings.Contains(s, "NOT_CONFIGURED") {
		t.Errorf("the summary must announce the unconfigured sink, got:\n%s", s)
	}
	// The unmeasured metric must not appear with a numeric value anywhere.
	for _, line := range strings.Split(s, "\n") {
		if strings.Contains(line, "lagging.defect_containment_rate") && !strings.Contains(line, "insufficient_data") {
			t.Errorf("an insufficient_data metric printed with a value: %q", line)
		}
	}
	// The review-author breakdown is published, so nobody has to assume whose
	// review the review metrics counted.
	if !strings.Contains(s, "review events by author") {
		t.Errorf("the summary must publish the review-author breakdown, got:\n%s", s)
	}
}

func TestSummaryOnAFullyMeasuredReportHasNoNotMeasuredBlock(t *testing.T) {
	rep := computeFixture(t)
	rep.Sinks = PublishAll(rep, []Sink{NewNotionSink(LoadNotionConfig(env(nil)))})
	s := Summary(rep)
	if strings.Contains(s, "NOT MEASURED") {
		t.Errorf("the known-answer fixture measures every metric; a NOT MEASURED block here means one silently lost its subjects:\n%s", s)
	}
	if !strings.Contains(s, "MEASURED — 16 metrics") {
		t.Errorf("expected all 16 metrics measured, got:\n%s", s)
	}
}
