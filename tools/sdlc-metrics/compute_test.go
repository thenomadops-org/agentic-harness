package main

import (
	"encoding/json"
	"errors"
	"math"
	"os"
	"strings"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// The computation is what these tests exercise. The fetch is the boring half;
// this is where a wrong number comes from.
//
// EVERY expectation below is a HAND-COMPUTED constant derived from
// testdata/known-answer.json, not a value recorded from a previous run. A
// golden file recorded from the implementation asserts only that the code has
// not changed, which is worth nothing when the code was wrong on the day the
// golden was taken.
// ---------------------------------------------------------------------------

func fixtureNow(t *testing.T) time.Time {
	t.Helper()
	n, err := time.Parse(time.RFC3339, "2026-06-15T00:00:00Z")
	if err != nil {
		t.Fatalf("parse fixture -now: %v", err)
	}
	return n
}

func loadDataset(t *testing.T, path string) Dataset {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	var ds Dataset
	if err := json.Unmarshal(raw, &ds); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
	return ds
}

func fixtureConfig(t *testing.T) Config {
	t.Helper()
	cfg := DefaultConfig()
	cfg.Repo = "fixture/repo"
	cfg.Now = fixtureNow(t)
	cfg.Window = NewWindow(cfg.Now, 14)
	// The known-answer fixture describes a MONOREPO — api/<service>,
	// mobile/<shell> — so the depth-2 roots are set here EXPLICITLY rather
	// than inherited. DefaultConfig ships them empty (a single-service
	// repository wants none, SCHEMA.md §10), and every surface expectation in
	// TestKnownAnswers is hand-computed against the monorepo reading. The
	// empty default is asserted separately, with its own hand computation, in
	// TestTheDefaultSurfaceRootsAreEmptyAndCollapseAMonorepo.
	cfg.Depth2Roots = []string{"api", "mobile", "tools", ".github"}
	return cfg
}

func computeFixture(t *testing.T) Report {
	t.Helper()
	rep, err := Compute(loadDataset(t, "testdata/known-answer.json"), fixtureConfig(t))
	if err != nil {
		t.Fatalf("Compute over the known-answer fixture failed: %v", err)
	}
	return rep
}

func recordByID(t *testing.T, rep Report, id string) Record {
	t.Helper()
	for _, m := range rep.Metrics {
		if m.MetricID == id {
			return m
		}
	}
	t.Fatalf("metric %q was not emitted at all; emitted: %s", id, strings.Join(metricIDs(rep), ", "))
	return Record{}
}

func metricIDs(rep Report) []string {
	out := make([]string, 0, len(rep.Metrics))
	for _, m := range rep.Metrics {
		out = append(out, m.MetricID)
	}
	return out
}

// TestKnownAnswers is the core assertion: one hand-computed number per metric.
//
// Break any single computation in compute.go and exactly one of these lines
// goes red, naming the metric — which is the property that makes it a test and
// not a smoke check.
func TestKnownAnswers(t *testing.T) {
	rep := computeFixture(t)

	cases := []struct {
		id       string
		want     float64
		subjects int
		// why states the hand computation, so a future failure can be
		// adjudicated without re-deriving it from the fixture.
		why string
	}{
		{"flow.open_issues_without_pr", 3, 4,
			"open issues are #101 #102 #103 #105; #103 has a linked pull request, so 3 have none"},
		{"flow.open_issues_without_pr_age_p50_days", 5, 3,
			"#101 45d, #102 5d, #105 3d at 2026-06-15; median of [3,5,45] is 5"},
		{"flow.open_prs", 3, 8,
			"PR5 PR6 PR7 are OPEN out of 8 examined"},
		{"flow.open_pr_age_p50_hours", 48, 3,
			"PR5 48h, PR6 24h, PR7 120h; median of [24,48,120] is 48"},
		{"flow.open_pr_awaiting_review_p50_hours", 48, 1,
			"only PR5 is waiting: PR6 is a draft, PR7 has a review after its last change. 48h since 2026-06-13"},
		{"flow.surfaces_in_flight", 4, 3,
			"PR5 -> .github/workflows and (root); PR6 -> api/media; PR7 -> admin"},
		{"flow.surfaces_touched_in_window", 11, 8,
			"api/gateway docs api/billing mobile/iosApp mobile/shared scripts .github/workflows (root) api/media admin api/social"},
		{"leading.issue_to_pr_p50_hours", 18, 2,
			"#103 -> PR3 is 24h, #104 -> PR1 is 12h; median of [12,24] is 18. #102 #105 #106 have no pull request"},
		{"leading.time_to_first_review_p50_hours", 2, 5,
			"PR1 2h, PR2 4h, PR3 2h, PR7 24h, PR8 2h; median of [2,2,2,4,24] is 2. PR4 PR5 PR6 got no review"},
		{"leading.first_pass_merge_rate", 0.25, 4,
			"of the 4 reviewed merged pull requests only PR1 took no change after review; PR4 merged unreviewed and is excluded"},
		{"lagging.rework_cycles_per_change_mean", 1, 4,
			"PR1 0, PR2 1, PR3 2, PR8 1; mean of [0,1,2,1] is 1"},
		{"lagging.defects_caught_before_merge", 3, 4,
			"PR2 PR3 PR8 each took a change after review; PR1 did not"},
		{"lagging.defects_escaped_to_production", 3, 6,
			"#104 #105 #106 opened in window carry a defect label"},
		{"lagging.defect_containment_rate", 0.5, 6,
			"3 caught, 3 escaped"},
		{"lagging.review_threads_settled_without_change_rate", 0.5, 2,
			"PR8 T1 resolved but a commit followed it; T2 resolved with nothing after; T3 unresolved and not counted"},
		{"lagging.repeat_defect_classes", 1, 3,
			"#104 and #105 are both proj:media; #106 has no class label and is excluded rather than bucketed"},
	}

	for _, c := range cases {
		t.Run(c.id, func(t *testing.T) {
			got := recordByID(t, rep, c.id)
			if got.Status != StatusOK {
				t.Fatalf("status = %q, want ok (%s)\n  detail: %s", got.Status, c.why, got.Detail)
			}
			if math.Abs(got.Value-c.want) > 1e-9 {
				t.Errorf("value = %v, want %v\n  hand computation: %s\n  detail: %s", got.Value, c.want, c.why, got.Detail)
			}
			if got.Subjects != c.subjects {
				t.Errorf("subjects = %d, want %d\n  hand computation: %s", got.Subjects, c.subjects, c.why)
			}
		})
	}

	// Every metric the code emits must be in the table above. Without this, a
	// new metric ships with no known answer and the suite still passes — the
	// exact shape of a guard that examines less than it claims to.
	covered := map[string]bool{}
	for _, c := range cases {
		covered[c.id] = true
	}
	for _, m := range rep.Metrics {
		if !covered[m.MetricID] {
			t.Errorf("metric %q is emitted but has no hand-computed expectation in TestKnownAnswers", m.MetricID)
		}
	}
	if len(rep.Metrics) != len(cases) {
		t.Errorf("emitted %d metrics, the table asserts %d", len(rep.Metrics), len(cases))
	}
}

func TestCensusMatchesTheFixture(t *testing.T) {
	rep := computeFixture(t)
	want := Totals{
		PullRequestsExamined: 8,
		PullRequestsMerged:   5,
		PullRequestsOpen:     3,
		IssuesExamined:       6,
		IssuesOpen:           4,
		ReviewEvents:         5, // PR1 1, PR2 1, PR3 2, PR7 1
		ReviewThreads:        3, // PR8 only
	}
	got := rep.Totals
	got.ReviewAuthors = nil
	if got.PullRequestsExamined != want.PullRequestsExamined ||
		got.PullRequestsMerged != want.PullRequestsMerged ||
		got.PullRequestsOpen != want.PullRequestsOpen ||
		got.IssuesExamined != want.IssuesExamined ||
		got.IssuesOpen != want.IssuesOpen ||
		got.ReviewEvents != want.ReviewEvents ||
		got.ReviewThreads != want.ReviewThreads {
		t.Errorf("totals = %+v, want %+v", got, want)
	}
	// The review-author breakdown must be published, and must be honest about
	// the author reviewing their own pull request.
	if n := rep.Totals.ReviewAuthors["app (= pull request author)"]; n != 5 {
		t.Errorf("review_authors[\"app (= pull request author)\"] = %d, want 5; got %+v", n, rep.Totals.ReviewAuthors)
	}
}

// ---------------------------------------------------------------------------
// THE VACUITY GUARD. Two fixtures, because there are two ways to examine
// nothing and only one of them looks empty.
// ---------------------------------------------------------------------------

func TestVacuityGuardRefusesAnEmptyDataset(t *testing.T) {
	cfg := fixtureConfig(t)
	cfg.Repo = "fixture/empty"
	_, err := Compute(loadDataset(t, "testdata/empty.json"), cfg)
	if err == nil {
		t.Fatal("Compute over an empty dataset returned no error — a row of zeroes is indistinguishable from a broken query, so this must refuse")
	}
	if !errors.Is(err, ErrNoSubjects) {
		t.Fatalf("error = %v, want it to wrap ErrNoSubjects so main can exit 3", err)
	}
}

func TestVacuityGuardRefusesAWindowThatSelectedNothing(t *testing.T) {
	cfg := fixtureConfig(t)
	cfg.Repo = "fixture/out-of-window"
	ds := loadDataset(t, "testdata/out-of-window.json")
	if len(ds.PullRequests) == 0 || len(ds.Issues) == 0 {
		t.Fatal("the out-of-window fixture is supposed to be NON-empty; it is the case where the fetch worked and the window selected nothing")
	}
	_, err := Compute(ds, cfg)
	if err == nil {
		t.Fatal("Compute over a dataset whose every subject falls outside the window returned no error — that is the case a naive implementation reports as a quiet fortnight")
	}
	if !errors.Is(err, ErrNoSubjects) {
		t.Fatalf("error = %v, want it to wrap ErrNoSubjects", err)
	}
}

// TestNoMetricIsEverZeroWithoutASubjectSet is the rule from schema.go, asserted
// rather than merely documented: a median or a ratio over an empty set is
// insufficient_data with value 0, and a count may be 0 while being ok.
func TestStatisticsOverAnEmptySetAreNeverReportedAsZero(t *testing.T) {
	// A dataset with exactly one open pull request, one open issue, and no
	// review, no merge, no defect anywhere. Every statistic has an empty
	// subject set; every count is legitimately zero.
	now := fixtureNow(t)
	ds := Dataset{
		Repo: "fixture/quiet",
		PullRequests: []PullRequest{{
			Number: 1, Author: "app", State: PROpen,
			CreatedAt: now.Add(-24 * time.Hour),
			Files:     []string{"docs/a.md"},
			Changes:   []ChangeEvent{{Kind: ChangeCommit, At: now.Add(-24 * time.Hour)}},
		}},
		Issues: []Issue{{
			Number: 100, State: "OPEN", CreatedAt: now.Add(-48 * time.Hour),
			LinkedPRs: []LinkedPR{{Number: 1, State: PROpen, CreatedAt: now.Add(-24 * time.Hour)}},
		}},
	}
	cfg := fixtureConfig(t)
	cfg.Repo = "fixture/quiet"
	rep, err := Compute(ds, cfg)
	if err != nil {
		t.Fatalf("Compute over a genuinely quiet but non-empty dataset must succeed: %v", err)
	}

	mustBeInsufficient := []string{
		"leading.time_to_first_review_p50_hours",
		"leading.first_pass_merge_rate",
		"lagging.rework_cycles_per_change_mean",
		"lagging.defect_containment_rate",
		"lagging.review_threads_settled_without_change_rate",
		"flow.open_issues_without_pr_age_p50_days",
	}
	for _, id := range mustBeInsufficient {
		m := recordByID(t, rep, id)
		if m.Status != StatusInsufficient {
			t.Errorf("%s: status = %q, want insufficient_data — its subject set is empty and a zero here would read as a measurement", id, m.Status)
		}
		if m.Value != 0 {
			t.Errorf("%s: insufficient_data must carry value 0, got %v", id, m.Value)
		}
	}

	mustBeOKAtZero := map[string]float64{
		"lagging.defects_caught_before_merge":   0,
		"lagging.defects_escaped_to_production": 0,
		"lagging.repeat_defect_classes":         0,
		"flow.open_issues_without_pr":           0,
	}
	for id, want := range mustBeOKAtZero {
		m := recordByID(t, rep, id)
		if m.Status != StatusOK {
			t.Errorf("%s: status = %q, want ok — it is a count over an enumerated population and zero is a fact about it", id, m.Status)
		}
		if m.Value != want {
			t.Errorf("%s: value = %v, want %v", id, m.Value, want)
		}
	}
}

// ---------------------------------------------------------------------------
// The two load-bearing definitions, tested directly.
// ---------------------------------------------------------------------------

// TestNothingIsAgedAgainstAnInstantItDidNotExistAt pins the bug the FIRST real
// run of this tool surfaced: flow.open_pr_age_p50_hours came back as -25.8
// hours, because a pull request opened after the measurement instant was still
// counted as "open now" and aged against a `now` that predates it.
//
// The fix is not to clamp the age at zero. It is to leave the subject out: it
// did not exist when this window was measured, so it is not part of what was
// in flight then. Clamping would have hidden the same wrong answer behind a
// plausible one.
func TestNothingIsAgedAgainstAnInstantItDidNotExistAt(t *testing.T) {
	cfg := fixtureConfig(t)
	cfg.Repo = "fixture/future"
	ds := loadDataset(t, "testdata/known-answer.json")
	future := cfg.Now.Add(26 * time.Hour)
	ds.PullRequests = append(ds.PullRequests, PullRequest{
		Number: 99, Author: "app", State: PROpen, CreatedAt: future,
		Files: []string{"docs/late.md"},
	})
	ds.Issues = append(ds.Issues, Issue{Number: 999, State: "OPEN", CreatedAt: future})

	rep, err := Compute(ds, cfg)
	if err != nil {
		t.Fatalf("Compute: %v", err)
	}
	for _, id := range []string{"flow.open_pr_age_p50_hours", "flow.open_issues_without_pr_age_p50_days"} {
		if got := recordByID(t, rep, id); got.Value < 0 {
			t.Errorf("%s = %v — an age can never be negative; a subject that postdates the measurement instant must be excluded, not aged", id, got.Value)
		}
	}
	// And it must be excluded outright, not merely clamped: the counts are
	// unchanged from the base fixture.
	if got := recordByID(t, rep, "flow.open_prs"); got.Value != 3 {
		t.Errorf("flow.open_prs = %v, want 3 — a pull request opened after the measurement instant is not open at it", got.Value)
	}
	if got := recordByID(t, rep, "flow.open_issues_without_pr"); got.Value != 3 {
		t.Errorf("flow.open_issues_without_pr = %v, want 3 — an issue opened after the measurement instant is not open at it", got.Value)
	}
}

func TestReworkCycleDefinition(t *testing.T) {
	at := func(h int) time.Time { return time.Date(2026, 6, 1, h, 0, 0, 0, time.UTC) }
	commit := func(h int) ChangeEvent { return ChangeEvent{Kind: ChangeCommit, At: at(h)} }
	force := func(h int) ChangeEvent { return ChangeEvent{Kind: ChangeForcePush, At: at(h)} }
	review := func(h int) Review { return Review{Author: "app", State: "COMMENTED", SubmittedAt: at(h)} }

	cases := []struct {
		name       string
		pr         PullRequest
		wantCycles int
		wantReview bool
	}{
		{"no review at all is unreviewed, never a first pass",
			PullRequest{Changes: []ChangeEvent{commit(1), commit(2)}}, 0, false},
		{"changes then a review is a first pass",
			PullRequest{Changes: []ChangeEvent{commit(1), commit(2)}, Reviews: []Review{review(3)}}, 0, true},
		{"one round trip",
			PullRequest{Changes: []ChangeEvent{commit(1), commit(4)}, Reviews: []Review{review(3)}}, 1, true},
		{"two reviews then one change is ONE round trip, not two",
			PullRequest{Changes: []ChangeEvent{commit(1), commit(5)}, Reviews: []Review{review(3), review(4)}}, 1, true},
		{"two round trips",
			PullRequest{Changes: []ChangeEvent{commit(1), commit(4), commit(7)}, Reviews: []Review{review(3), review(6)}}, 2, true},
		// THE DISCRIMINATING CASE, and it was missing from the first cut of this
		// table. Deleting the `armed = false` disarm in reworkCycles left every
		// other case in this file green, because none of them had two changes
		// answering ONE review. A rework CYCLE is a round trip, not a commit
		// count: pushing a fix as three small commits is still one round trip,
		// and counting it as three would make squashing look like an
		// improvement in the process.
		{"two changes answering ONE review is ONE round trip, not two",
			PullRequest{Changes: []ChangeEvent{commit(1), commit(4), commit(5)}, Reviews: []Review{review(3)}}, 1, true},
		{"three changes answering one review is still one round trip",
			PullRequest{Changes: []ChangeEvent{commit(1), commit(4), commit(5), commit(6)}, Reviews: []Review{review(3)}}, 1, true},
		{"a force push answers a review just as a commit does",
			PullRequest{Changes: []ChangeEvent{commit(1), force(4)}, Reviews: []Review{review(3)}}, 1, true},
		{"a review-thread comment is a review event",
			PullRequest{Changes: []ChangeEvent{commit(1), commit(4)},
				Threads: []ReviewThread{{ID: "t", Comments: []ThreadComment{{CreatedAt: at(3)}}}}}, 1, true},
		{"a change at the same instant as the review counts as answering it",
			PullRequest{Changes: []ChangeEvent{commit(1), commit(3)}, Reviews: []Review{review(3)}}, 1, true},
		{"changes are ordered by time, not by slice order",
			PullRequest{Changes: []ChangeEvent{commit(4), commit(1)}, Reviews: []Review{review(3)}}, 1, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			cycles, reviewed := reworkCycles(c.pr, Config{})
			if cycles != c.wantCycles || reviewed != c.wantReview {
				t.Errorf("reworkCycles = (%d, %v), want (%d, %v)", cycles, reviewed, c.wantCycles, c.wantReview)
			}
		})
	}
}

func TestSurfaceOf(t *testing.T) {
	roots := map[string]bool{"api": true, "mobile": true, "tools": true, ".github": true}
	cases := map[string]string{
		"api/gateway/internal/policy/policy.go": "api/gateway",
		"api/billing/x.go":                      "api/billing",
		"mobile/iosApp/A.swift":                 "mobile/iosApp",
		"mobile/shared/src/x/B.kt":              "mobile/shared",
		".github/workflows/x.yml":               ".github/workflows",
		"scripts/foo.sh":                        "scripts",
		"admin/a.go":                            "admin",
		"docs/x.md":                             "docs",
		"Makefile":                              "(root)",
		"./docs/x.md":                           "docs",
		"api/README.md":                         "api", // only two segments: no service to name
		"":                                      "",
	}
	for in, want := range cases {
		if got := surfaceOf(in, roots); got != want {
			t.Errorf("surfaceOf(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestMentionedIssuesOnlyResolvesKnownIssues(t *testing.T) {
	// Where a project's convention is a bare claim line — "#839" with no closing
	// keyword — this is the DOMINANT linkage, and getting it wrong reports that
	// almost no issue ever acquires a pull request.
	issues := map[int]bool{839: true, 846: true}
	got := mentionedIssues("#846: metrics", "closes #839 and supersedes #840, see api/x#846 and https://x/pull/840#issuecomment-9", issues)
	want := []int{839, 846}
	if len(got) != len(want) {
		t.Fatalf("mentionedIssues = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("mentionedIssues = %v, want %v", got, want)
		}
	}
	// #840 is a pull request, not an issue, and must not be counted.
	for _, n := range got {
		if n == 840 {
			t.Error("#840 is not in the issue set and must not be treated as issue linkage")
		}
	}
}

func TestAwaitingReviewIgnoresAPullRequestAlreadyReviewedAtItsTip(t *testing.T) {
	at := func(h int) time.Time { return time.Date(2026, 6, 1, h, 0, 0, 0, time.UTC) }
	pr := PullRequest{
		CreatedAt: at(1),
		Changes:   []ChangeEvent{{Kind: ChangeCommit, At: at(2)}},
		Reviews:   []Review{{SubmittedAt: at(3)}},
	}
	if _, waiting := awaitingReviewSince(pr, Config{}); waiting {
		t.Error("a pull request whose latest change has been reviewed is not waiting")
	}
	// Push again after the review and it is waiting once more, from the push.
	pr.Changes = append(pr.Changes, ChangeEvent{Kind: ChangeCommit, At: at(4)})
	since, waiting := awaitingReviewSince(pr, Config{})
	if !waiting {
		t.Fatal("a change after the last review puts the pull request back into waiting")
	}
	if !since.Equal(at(4)) {
		t.Errorf("waiting since %v, want %v — the clock restarts at the change, not at creation", since, at(4))
	}
}

func TestFirstPRAfterIgnoresAPullRequestThatPredatesTheIssue(t *testing.T) {
	issueAt := time.Date(2026, 6, 5, 0, 0, 0, 0, time.UTC)
	is := Issue{Number: 1, CreatedAt: issueAt, LinkedPRs: []LinkedPR{
		{Number: 9, CreatedAt: issueAt.Add(-48 * time.Hour)}, // predates: cannot have answered it
		{Number: 10, CreatedAt: issueAt.Add(24 * time.Hour)},
	}}
	got, ok := firstPRAfter(is, nil, nil)
	if !ok {
		t.Fatal("expected a pull request after the issue")
	}
	if !got.Equal(issueAt.Add(24 * time.Hour)) {
		t.Errorf("firstPRAfter = %v, want the one created AFTER the issue; a pull request that predates it would give a negative latency", got)
	}
}

func TestReportValidatesAndRoundTrips(t *testing.T) {
	rep := computeFixture(t)
	rep.Sinks = PublishAll(rep, []Sink{NewNotionSink(LoadNotionConfig(func(string) string { return "" }))})
	if err := rep.Validate(); err != nil {
		t.Fatalf("the fixture report fails its own contract: %v", err)
	}
	doc, err := rep.Encode()
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	var back Report
	if err := json.Unmarshal(doc, &back); err != nil {
		t.Fatalf("the encoded document does not decode as a Report: %v", err)
	}
	if back.SchemaVersion != SchemaVersion {
		t.Errorf("schema_version round-tripped as %q", back.SchemaVersion)
	}
	if len(back.Metrics) != len(rep.Metrics) {
		t.Errorf("round trip lost metrics: %d -> %d", len(rep.Metrics), len(back.Metrics))
	}
	if err := back.Validate(); err != nil {
		t.Errorf("the decoded document fails the contract: %v", err)
	}
	// Sorted by metric id, so a diff between two runs is a diff in the numbers.
	for i := 1; i < len(back.Metrics); i++ {
		if back.Metrics[i-1].MetricID > back.Metrics[i].MetricID {
			t.Fatalf("metrics are not sorted by id: %q before %q", back.Metrics[i-1].MetricID, back.Metrics[i].MetricID)
		}
	}
}

func TestEveryEmittedMetricHasADefinition(t *testing.T) {
	rep := computeFixture(t)
	for _, m := range rep.Metrics {
		def, ok := rep.Definitions[m.MetricID]
		if !ok || strings.TrimSpace(def) == "" {
			t.Errorf("metric %q ships with no operational definition — a metric nobody can reproduce is one nobody can trust", m.MetricID)
		}
	}
	for id := range rep.Definitions {
		found := false
		for _, m := range rep.Metrics {
			if m.MetricID == id {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("definitions carries %q, which no metric emits — a stale definition is worse than none", id)
		}
	}
}
