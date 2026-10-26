package main

import (
	"errors"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// The unconfigured-rail rule, asserted: an unconfigured sink is ANNOUNCED, recorded as
// not_configured rather than ok, and never crashes the run.
// ---------------------------------------------------------------------------

func env(m map[string]string) func(string) string {
	return func(k string) string { return m[k] }
}

func TestUnconfiguredNotionSinkIsNotConfiguredAndSaysWhatIsMissing(t *testing.T) {
	s := NewNotionSink(LoadNotionConfig(env(nil)))
	if s.Configured() {
		t.Fatal("a sink with no token must not report itself configured")
	}
	d := s.Describe()
	for _, want := range []string{"NOT CONFIGURED", "NOTION_API_TOKEN", "NOTION_DATABASE_ID"} {
		if !strings.Contains(d, want) {
			t.Errorf("Describe() must name %q so the absence is announced, got: %s", want, d)
		}
	}
}

func TestAPartiallyConfiguredSinkNamesOnlyTheMissingHalf(t *testing.T) {
	s := NewNotionSink(LoadNotionConfig(env(map[string]string{"NOTION_API_TOKEN": "secret-value"})))
	if s.Configured() {
		t.Fatal("half a configuration is not a configuration")
	}
	d := s.Describe()
	if !strings.Contains(d, "NOTION_DATABASE_ID") {
		t.Errorf("the missing setting must be named, got: %s", d)
	}
	if strings.Contains(d, "NOTION_API_TOKEN") {
		t.Errorf("a setting that IS present must not be listed as missing, got: %s", d)
	}
	// The value of a secret is never printed, whatever else changes here.
	if strings.Contains(d, "secret-value") {
		t.Fatalf("the token's VALUE leaked into the announcement: %s", d)
	}
}

func TestADisabledSinkRefusesRatherThanReturningNil(t *testing.T) {
	// The whole point: publishing nothing must never be recordable as a
	// publish. A nil return here is how "we forgot to write the push" reads as
	// "the push worked".
	s := NewNotionSink(LoadNotionConfig(env(nil)))
	err := s.Publish(Report{})
	if err == nil {
		t.Fatal("Publish on an unconfigured sink returned nil — a caller cannot tell that from success")
	}
	if !errors.Is(err, ErrSinkNotConfigured) {
		t.Errorf("error = %v, want it to wrap ErrSinkNotConfigured", err)
	}
}

func TestPublishAllRecordsNotConfiguredNeverOK(t *testing.T) {
	got := PublishAll(Report{}, []Sink{NewNotionSink(LoadNotionConfig(env(nil)))})
	if len(got) != 1 {
		t.Fatalf("got %d sink statuses, want 1 — a sink that is not recorded at all is silent", len(got))
	}
	if got[0].Status != StatusNotConfigured {
		t.Errorf("status = %q, want %q", got[0].Status, StatusNotConfigured)
	}
	if got[0].Status == StatusOK {
		t.Error("an unconfigured sink recorded as ok is the exact failure this rule is about")
	}
	if got[0].Detail == "" {
		t.Error("a not_configured sink with no detail is silent by another name")
	}
}

// A sink that is configured and fails must be FAILED, not quietly dropped.
type failingSink struct{ err error }

func (failingSink) Name() string     { return "failing" }
func (failingSink) Configured() bool { return true }
func (failingSink) Describe() string { return "failing sink: configured" }
func (s failingSink) Publish(Report) error {
	return s.err
}

func TestPublishAllRecordsAFailedPublishAsFailed(t *testing.T) {
	got := PublishAll(Report{}, []Sink{failingSink{err: errors.New("notion returned 401")}})
	if got[0].Status != StatusFailed {
		t.Errorf("status = %q, want %q", got[0].Status, StatusFailed)
	}
	if !strings.Contains(got[0].Detail, "401") {
		t.Errorf("the failure reason must survive into the document, got: %s", got[0].Detail)
	}
}

func TestASinkThatClaimsConfiguredThenRefusesIsStillNotRecordedAsOK(t *testing.T) {
	got := PublishAll(Report{}, []Sink{failingSink{err: ErrSinkNotConfigured}})
	if got[0].Status == StatusOK {
		t.Fatal("a sink that refused as unconfigured must never be recorded as a successful publish")
	}
	if got[0].Status != StatusNotConfigured {
		t.Errorf("status = %q, want %q", got[0].Status, StatusNotConfigured)
	}
}

// The document contract refuses a sink list that is absent or silent, which is
// what stops a future edit from dropping the sink block and leaving the reader
// unable to tell whether anything was published.
func TestValidateRefusesAReportWithNoSinksAndASilentSink(t *testing.T) {
	base := func() Report {
		w := NewWindow(mustTime("2026-06-15T00:00:00Z"), 14)
		return Report{
			SchemaVersion: SchemaVersion, Repo: "a/b", Window: w,
			Definitions: map[string]string{"flow.open_prs": "d"},
			Metrics: []Record{{
				MetricID: "flow.open_prs", Title: "t", Unit: UnitCount,
				Status: StatusOK, Detail: "d", Window: w,
			}},
		}
	}
	r := base()
	if err := r.Validate(); err == nil {
		t.Error("a report naming no sinks must not validate")
	}
	r = base()
	r.Sinks = []SinkStatus{{Name: "notion", Status: StatusNotConfigured, Detail: ""}}
	if err := r.Validate(); err == nil {
		t.Error("a not_configured sink with an empty detail must not validate — that is silence")
	}
	r = base()
	r.Sinks = []SinkStatus{{Name: "notion", Status: StatusNotConfigured, Detail: "unset: NOTION_API_TOKEN"}}
	if err := r.Validate(); err != nil {
		t.Errorf("a well-formed report must validate: %v", err)
	}
}

func TestValidateRefusesAnInsufficientRecordCarryingAValue(t *testing.T) {
	w := NewWindow(mustTime("2026-06-15T00:00:00Z"), 14)
	r := Report{
		SchemaVersion: SchemaVersion, Repo: "a/b", Window: w,
		Sinks:       []SinkStatus{{Name: "notion", Status: StatusNotConfigured, Detail: "unset"}},
		Definitions: map[string]string{"leading.first_pass_merge_rate": "d"},
		Metrics: []Record{{
			MetricID: "leading.first_pass_merge_rate", Title: "t", Unit: UnitRatio,
			Status: StatusInsufficient, Value: 0.9, Detail: "d", Window: w,
		}},
	}
	if err := r.Validate(); err == nil {
		t.Fatal("an insufficient_data record carrying a non-zero value must not validate — a consumer that ignores status would plot it as a measurement")
	}
}
