package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"time"
)

// ---------------------------------------------------------------------------
// THE OUTPUT CONTRACT.
//
// This file is the interface. Whatever consumes metrics.json — a dashboard, a
// spreadsheet importer, the Notion push in sink.go — is a SEPARATE program
// written against the JSON these types marshal to, so a change here is a
// breaking change to a consumer that is not in this repository and cannot be
// grepped for. SchemaVersion exists so that consumer can refuse a document it
// does not understand instead of silently reading a renamed field as absent.
//
// The prose version, with the operational definition of every metric id, is
// SCHEMA.md in this directory. The two are kept together on purpose: a metric
// whose definition lives only in the head of whoever wrote it is a number
// nobody can reproduce or argue with.
// ---------------------------------------------------------------------------

// SchemaVersion identifies the shape of Report as marshalled. It is a
// namespaced string rather than a bare integer so a consumer reading a
// document from some other collector cannot mistake it for this one.
//
// BUMP IT when a field is removed or renamed, or when the meaning of an
// existing metric id changes. Adding a NEW metric id, or a new optional field,
// is backward compatible and does not bump it — a consumer that iterates
// `metrics` and keys off `metric_id` keeps working.
const SchemaVersion = "sdlc-metrics/v1"

// Status is the per-record and per-sink outcome vocabulary. It is deliberately
// SMALL and every value is load-bearing:
//
//	StatusOK              the number was computed over a real subject set.
//	StatusInsufficient    the metric is a statistic (a median, a ratio) whose
//	                      subject set turned out empty, so there is no number.
//	                      Value is 0 and MUST NOT be read as a measurement.
//	StatusNotConfigured   a sink has no credential. Not an error, not a
//	                      success, and never silence.
//	StatusFailed          a sink was configured and the attempt failed.
//
// The distinction between StatusOK-at-zero and StatusInsufficient is the whole
// point of this vocabulary, and it is the rule that is easiest to get wrong:
//
//   - A COUNT over an enumerable population is StatusOK even when it is 0.
//     "There are zero open pull requests" is a real fact, and the census in
//     Report.Totals proves the query that produced it examined something.
//   - A MEDIAN or a RATIO over an empty set is StatusInsufficient, always.
//     There is no median of nothing. Emitting 0 there is the exact
//     "a quiet week and a broken query look identical" failure this tool
//     exists to prevent.
type Status string

const (
	StatusOK            Status = "ok"
	StatusInsufficient  Status = "insufficient_data"
	StatusNotConfigured Status = "not_configured"
	StatusFailed        Status = "failed"
)

// Unit is the dimension of Record.Value. A dashboard formats on this, so it is
// part of the contract; do not emit a unit that is not listed here.
type Unit string

const (
	UnitCount  Unit = "count"  // a whole number of things
	UnitHours  Unit = "hours"  // elapsed hours, fractional
	UnitDays   Unit = "days"   // elapsed days, fractional
	UnitRatio  Unit = "ratio"  // 0.0 .. 1.0
	UnitCycles Unit = "cycles" // rework cycles, fractional (it is a mean)
)

// Window is the measurement period. Every record carries the same one — a
// document is one repo over one window — but it is repeated per record anyway
// so a consumer that flattens `metrics` into a table row per record (which is
// exactly what a Notion database is) does not have to carry the envelope.
type Window struct {
	// ID is a stable human/primary key for the window, "YYYY-MM-DD..YYYY-MM-DD".
	// Combined with MetricID it uniquely identifies a row, which is what makes
	// re-running the collector for the same window an UPDATE and not a
	// duplicate row in the consumer.
	ID    string    `json:"id"`
	Start time.Time `json:"start"`
	End   time.Time `json:"end"`
	Days  int       `json:"days"`
}

// NewWindow builds the window ending at end and covering days days.
func NewWindow(end time.Time, days int) Window {
	end = end.UTC()
	start := end.AddDate(0, 0, -days)
	return Window{
		ID:    start.Format("2006-01-02") + ".." + end.Format("2006-01-02"),
		Start: start,
		End:   end,
		Days:  days,
	}
}

// Contains reports whether t falls inside the window, start-inclusive and
// end-inclusive.
func (w Window) Contains(t time.Time) bool {
	if t.IsZero() {
		return false
	}
	return !t.Before(w.Start) && !t.After(w.End)
}

// Record is ONE metric for ONE window: the row a Notion database stores.
type Record struct {
	// MetricID is the stable key. Format: "<family>.<name>", families are
	// flow / leading / lagging. NEVER reuse an id for a different meaning —
	// retire it and add a new one, or the consumer's history silently changes
	// what it was measuring halfway down the chart.
	MetricID string `json:"metric_id"`
	// Title is a short human label for a dashboard column header.
	Title string `json:"title"`
	// Family is the first segment of MetricID, denormalised so a consumer can
	// group without parsing the id.
	Family string `json:"family"`
	// Value is the measurement, in Unit. When Status is not StatusOK it is 0
	// and carries NO information — read Status first.
	Value float64 `json:"value"`
	Unit  Unit    `json:"unit"`
	// Status gates Value. See the Status doc comment.
	Status Status `json:"status"`
	// Subjects is how many things this metric actually examined: merged PRs,
	// open issues, resolved review threads. It is the anti-vacuity field —
	// a consumer can plot it beside the value and see a number that was
	// computed over nothing, which a bare value cannot show.
	Subjects int `json:"subjects"`
	// Window and MeasuredAt make the record self-describing when detached
	// from the envelope.
	Window     Window    `json:"window"`
	MeasuredAt time.Time `json:"measured_at"`
	// Detail is one human-readable sentence: what the number means, and the
	// counts behind it. It is what somebody reads in CI output when they have
	// no dashboard open. It is NOT parsed by anything and its wording may
	// change without a schema bump.
	Detail string `json:"detail"`
}

// SinkStatus records what happened to each destination this run was supposed
// to publish to.
//
// The unconfigured-rail rule, applied here verbatim: an unconfigured
// destination is ANNOUNCED, recorded as StatusNotConfigured rather than as a
// success, and never crash-loops the run. A metrics job that quietly does
// nothing because a token is missing is indistinguishable from one that
// published.
type SinkStatus struct {
	Name   string `json:"name"`
	Status Status `json:"status"`
	// Detail names the MISSING SETTINGS by env var name (never their values),
	// or the failure. It is the boot statement, in the document.
	Detail string `json:"detail"`
}

// Totals is the census: the raw subject counts this run drew on. It exists so
// a reader can tell "nothing happened" from "the query returned nothing", and
// so a consumer can refuse a document built on an implausibly small sample.
type Totals struct {
	PullRequestsExamined int `json:"pull_requests_examined"`
	PullRequestsMerged   int `json:"pull_requests_merged"`
	PullRequestsOpen     int `json:"pull_requests_open"`
	IssuesExamined       int `json:"issues_examined"`
	IssuesOpen           int `json:"issues_open"`
	ReviewEvents         int `json:"review_events"`
	ReviewThreads        int `json:"review_threads"`
	// ReviewAuthors is login -> review events submitted, over the examined
	// pull requests. An author reviewing their own pull request is suffixed
	// "(= pull request author)".
	//
	// It is published unconditionally, in BOTH modes of -review-excludes-author
	// (see Config.ReviewExcludesAuthor in compute.go), because whichever way
	// that switch is set the reader needs to see whose review is being counted
	// rather than assuming a human's. This census is the raw population and is
	// never filtered by the switch: with the switch on and every review by the
	// author, review_events is large and the review metrics are
	// insufficient_data, and that pair is the finding.
	ReviewAuthors map[string]int `json:"review_authors"`
}

// Report is the whole document: exactly what metrics.json contains.
type Report struct {
	SchemaVersion string       `json:"schema_version"`
	Repo          string       `json:"repo"`
	GeneratedAt   time.Time    `json:"generated_at"`
	Window        Window       `json:"window"`
	Collector     string       `json:"collector"`
	Totals        Totals       `json:"totals"`
	Sinks         []SinkStatus `json:"sinks"`
	Metrics       []Record     `json:"metrics"`
	// Definitions maps every emitted metric id to the one-line operational
	// definition used to compute it. It is IN the document, not only in
	// SCHEMA.md, so a dashboard can show the definition next to the number and
	// a reader never has to trust that the doc and the code agree.
	Definitions map[string]string `json:"definitions"`
}

// Collector names the program and is emitted into every Report, so a document
// found on its own says what produced it.
const Collector = "tools/sdlc-metrics"

// Validate checks the invariants a consumer is entitled to rely on. It runs
// before the document is written, so a malformed document is never produced at
// all rather than being produced and rejected downstream.
func (r Report) Validate() error {
	if r.SchemaVersion != SchemaVersion {
		return fmt.Errorf("schema_version is %q, want %q", r.SchemaVersion, SchemaVersion)
	}
	if r.Repo == "" {
		return fmt.Errorf("repo is empty")
	}
	if r.Window.ID == "" || r.Window.Days <= 0 {
		return fmt.Errorf("window is not set")
	}
	if len(r.Metrics) == 0 {
		return fmt.Errorf("report carries zero metric records")
	}
	seen := make(map[string]bool, len(r.Metrics))
	for _, m := range r.Metrics {
		if m.MetricID == "" {
			return fmt.Errorf("a record has an empty metric_id")
		}
		if seen[m.MetricID] {
			return fmt.Errorf("duplicate metric_id %q — a consumer keyed on (metric_id, window.id) would lose one of them", m.MetricID)
		}
		seen[m.MetricID] = true
		switch m.Status {
		case StatusOK, StatusInsufficient:
		default:
			return fmt.Errorf("metric %q has sink-only status %q", m.MetricID, m.Status)
		}
		switch m.Unit {
		case UnitCount, UnitHours, UnitDays, UnitRatio, UnitCycles:
		default:
			return fmt.Errorf("metric %q has unknown unit %q", m.MetricID, m.Unit)
		}
		if m.Unit == UnitRatio && m.Status == StatusOK && (m.Value < 0 || m.Value > 1) {
			return fmt.Errorf("metric %q is a ratio but its value is %v", m.MetricID, m.Value)
		}
		if m.Status == StatusInsufficient && m.Value != 0 {
			return fmt.Errorf("metric %q is insufficient_data but carries value %v — a consumer that ignores status would plot it", m.MetricID, m.Value)
		}
		if m.Detail == "" {
			return fmt.Errorf("metric %q has no detail string", m.MetricID)
		}
		if _, ok := r.Definitions[m.MetricID]; !ok {
			return fmt.Errorf("metric %q has no entry in definitions — every emitted metric states how it was computed", m.MetricID)
		}
		if m.Window.ID != r.Window.ID {
			return fmt.Errorf("metric %q carries window %q, envelope says %q", m.MetricID, m.Window.ID, r.Window.ID)
		}
	}
	if len(r.Sinks) == 0 {
		return fmt.Errorf("report names no sinks — an absent sink list is indistinguishable from a sink that was never attempted")
	}
	for _, s := range r.Sinks {
		if s.Status != StatusOK && s.Status != StatusNotConfigured && s.Status != StatusFailed {
			return fmt.Errorf("sink %q has status %q, which is not a sink status", s.Name, s.Status)
		}
		if s.Detail == "" {
			return fmt.Errorf("sink %q has no detail string — an unconfigured sink that does not say what is missing is silent", s.Name)
		}
	}
	return nil
}

// MarshalJSON is not overridden; this is the canonical encoder used by main so
// the on-disk bytes are stable (sorted metric ids, indented, trailing newline).
func (r Report) Encode() ([]byte, error) {
	sort.SliceStable(r.Metrics, func(i, j int) bool { return r.Metrics[i].MetricID < r.Metrics[j].MetricID })
	b, err := json.MarshalIndent(r, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(b, '\n'), nil
}
