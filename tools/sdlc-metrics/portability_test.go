package main

import (
	"encoding/json"
	"flag"
	"io"
	"math"
	"reflect"
	"strings"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// THE PORTABILITY GUARDS.
//
// This tool was extracted from one repository and generalised. Everything in
// this file guards a promise that generalisation made, and each one is a
// promise that would otherwise decay into a sentence in a document that nobody
// re-checks:
//
//   - the surface roots default to EMPTY, because they described somebody
//     else's directory layout;
//   - -review-excludes-author exists, defaults to false, and ACTUALLY changes
//     the numbers when set (a switch that is wired to nothing is worse than an
//     absent one, because it reads as a choice already made);
//   - the unit mismatch inside defect_containment_rate is visible in the
//     OUTPUT, not only in SCHEMA.md;
//   - every repository-shaped Config field has a flag.
// ---------------------------------------------------------------------------

func peerReviewConfig(t *testing.T, excludeAuthor bool) Config {
	t.Helper()
	cfg := DefaultConfig()
	cfg.Repo = "acme/widgets"
	cfg.Now = fixtureNow(t)
	cfg.Window = NewWindow(cfg.Now, 14)
	cfg.ReviewExcludesAuthor = excludeAuthor
	return cfg
}

func computeOrFail(t *testing.T, path string, cfg Config) Report {
	t.Helper()
	rep, err := Compute(loadDataset(t, path), cfg)
	if err != nil {
		t.Fatalf("Compute over %s failed: %v", path, err)
	}
	return rep
}

// ---------------------------------------------------------------------------
// 1. The surface roots default to empty.
// ---------------------------------------------------------------------------

func TestTheDefaultSurfaceRootsAreEmpty(t *testing.T) {
	if got := DefaultConfig().Depth2Roots; len(got) != 0 {
		t.Fatalf("DefaultConfig().Depth2Roots = %v, want empty.\n"+
			"A default naming particular top-level directories is a claim about somebody else's repository layout. "+
			"A single-service repository wants none; a monorepo passes -surface-depth2-roots. See SCHEMA.md §10.", got)
	}
}

// TestTheDefaultSurfaceRootsAreEmptyAndCollapseAMonorepo is the same fixture as
// TestKnownAnswers, computed with the SHIPPED default instead of the monorepo
// roots that fixture describes, and both numbers are hand-computed.
//
// It is here so the change of default is a measured difference rather than an
// assertion that was quietly relaxed: the surface counts do not merely "still
// pass", they move to a specific other value for a stated reason.
func TestTheDefaultSurfaceRootsAreEmptyAndCollapseAMonorepo(t *testing.T) {
	cfg := fixtureConfig(t)
	cfg.Depth2Roots = DefaultConfig().Depth2Roots // i.e. none
	rep := computeOrFail(t, "testdata/known-answer.json", cfg)

	// Hand computation, with no depth-2 roots. Every file contributes its first
	// path segment:
	//   PR1 api/gateway…, docs/x.md            -> api, docs
	//   PR2 api/billing/x.go                   -> api
	//   PR3 mobile/iosApp, mobile/shared       -> mobile
	//   PR4 scripts/foo.sh                     -> scripts
	//   PR5 .github/workflows/x.yml, Makefile  -> .github, (root)
	//   PR6 api/media/z.go                     -> api
	//   PR7 admin/a.go                         -> admin
	//   PR8 api/social/s.go                    -> api
	// distinct over all eight: api docs mobile scripts .github (root) admin = 7
	// (it is 11 when api/* and mobile/* are split at depth 2).
	if got := recordByID(t, rep, "flow.surfaces_touched_in_window"); got.Value != 7 {
		t.Errorf("surfaces_touched_in_window with the default (empty) roots = %v, want 7; it is 11 when api and mobile split at depth 2.\n  detail: %s", got.Value, got.Detail)
	}
	// Open pull requests are PR5 (.github, (root)), PR6 (api), PR7 (admin) = 4.
	// Unchanged from the monorepo reading, because none of those four collapse
	// into each other — which is exactly why asserting only this one would have
	// hidden the change.
	if got := recordByID(t, rep, "flow.surfaces_in_flight"); got.Value != 4 {
		t.Errorf("surfaces_in_flight with the default (empty) roots = %v, want 4\n  detail: %s", got.Value, got.Detail)
	}

	// And the document says which rule produced those numbers, so a reader
	// comparing two repositories' documents can see they were bucketed
	// differently instead of assuming one is busier.
	def := rep.Definitions["flow.surfaces_in_flight"]
	if !strings.Contains(def, "no depth-2 roots configured") {
		t.Errorf("the surface definition must state that no depth-2 roots are configured; it says: %s", def)
	}
}

// ---------------------------------------------------------------------------
// 2. -review-excludes-author. The flag has to MOVE the numbers.
// ---------------------------------------------------------------------------

// TestReviewExcludesAuthorChangesTheComputedReviewMetrics runs one fixture
// through both settings and asserts a hand-computed answer for each metric in
// each mode.
//
// testdata/peer-review.json, window 2026-06-01..2026-06-15:
//
//	PR1 author1, merged. commit 00:00, author1 review 01:00, commit 02:00,
//	    reviewer1 review 04:00.
//	PR2 author1, merged. commit 00:00, author1 CHANGES_REQUESTED 01:00,
//	    commit 02:00. No peer ever looked at it.
//	PR3 author2, merged. commit 00:00, reviewer1 review 03:00. Nothing after.
//	#10, #11 opened in window with a defect label; neither has a pull request.
//
// Counting self-review, PR2 is a reviewed pull request that caught a defect.
// Excluding it, PR2 is an UNREVIEWED merge — which is the true statement about
// human scrutiny and the false one about review activity. That is the whole
// argument for making this a switch instead of a decision.
func TestReviewExcludesAuthorChangesTheComputedReviewMetrics(t *testing.T) {
	cases := []struct {
		id            string
		counting      float64 // -review-excludes-author=false (the default)
		countingSubj  int
		excluding     float64 // -review-excludes-author=true
		excludingSubj int
		why           string
	}{
		{
			id:       "leading.time_to_first_review_p50_hours",
			counting: 1, countingSubj: 3,
			excluding: 3.5, excludingSubj: 2,
			why: "counting the author: PR1 1h, PR2 1h, PR3 3h -> median 1. " +
				"excluding: PR1 4h, PR3 3h, PR2 never reviewed -> median of [3,4] is 3.5",
		},
		{
			id:       "leading.first_pass_merge_rate",
			counting: 1.0 / 3.0, countingSubj: 3,
			excluding: 1.0, excludingSubj: 2,
			why: "counting: PR1 and PR2 each took a commit after the author's own review, PR3 did not -> 1 of 3. " +
				"excluding: PR1's commit precedes the peer review so it is a first pass, PR3 is a first pass, PR2 drops out unreviewed -> 2 of 2",
		},
		{
			id:       "lagging.rework_cycles_per_change_mean",
			counting: 2.0 / 3.0, countingSubj: 3,
			excluding: 0, excludingSubj: 2,
			why: "counting: [1,1,0] -> 2/3. excluding: [0,0] over PR1 and PR3 -> 0",
		},
		{
			id:       "lagging.defects_caught_before_merge",
			counting: 2, countingSubj: 3,
			excluding: 0, excludingSubj: 2,
			why: "counting: PR1 reworked, PR2 reworked and carries CHANGES_REQUESTED. " +
				"excluding: PR2's changes-requested review is the author's own and no longer counts, and nothing else reworked",
		},
		{
			id:       "lagging.defect_containment_rate",
			counting: 0.5, countingSubj: 4,
			excluding: 0, excludingSubj: 2,
			why: "escaped is 2 in both modes (#10, #11 are label-driven). caught 2 -> 2/4; caught 0 -> 0/2",
		},
	}

	counting := computeOrFail(t, "testdata/peer-review.json", peerReviewConfig(t, false))
	excluding := computeOrFail(t, "testdata/peer-review.json", peerReviewConfig(t, true))

	moved := 0
	for _, c := range cases {
		t.Run(c.id, func(t *testing.T) {
			a := recordByID(t, counting, c.id)
			b := recordByID(t, excluding, c.id)
			if a.Status != StatusOK || b.Status != StatusOK {
				t.Fatalf("status = %q counting / %q excluding, want ok in both (%s)", a.Status, b.Status, c.why)
			}
			if math.Abs(a.Value-c.counting) > 1e-9 || a.Subjects != c.countingSubj {
				t.Errorf("-review-excludes-author=false: value = %v (n=%d), want %v (n=%d)\n  hand computation: %s\n  detail: %s",
					a.Value, a.Subjects, c.counting, c.countingSubj, c.why, a.Detail)
			}
			if math.Abs(b.Value-c.excluding) > 1e-9 || b.Subjects != c.excludingSubj {
				t.Errorf("-review-excludes-author=true: value = %v (n=%d), want %v (n=%d)\n  hand computation: %s\n  detail: %s",
					b.Value, b.Subjects, c.excluding, c.excludingSubj, c.why, b.Detail)
			}
			if math.Abs(a.Value-b.Value) > 1e-9 {
				moved++
			}
		})
	}
	if moved != len(cases) {
		t.Errorf("only %d of %d review metrics moved when the flag was set; a flag that changes nothing is worse than an absent one, because it reads as a choice already made", moved, len(cases))
	}

	// The CENSUS is deliberately NOT filtered: it is the raw population, and it
	// is what tells a reader which of the two modes their repository is in.
	if a, b := counting.Totals.ReviewEvents, excluding.Totals.ReviewEvents; a != 4 || b != 4 {
		t.Errorf("totals.review_events = %d counting / %d excluding, want 4 in both — the census is the raw population, not the filtered one", a, b)
	}
	for _, rep := range []Report{counting, excluding} {
		if n := rep.Totals.ReviewAuthors["author1 (= pull request author)"]; n != 2 {
			t.Errorf("review_authors must show the self-review in BOTH modes; got %+v", rep.Totals.ReviewAuthors)
		}
		if n := rep.Totals.ReviewAuthors["reviewer1"]; n != 2 {
			t.Errorf("review_authors[reviewer1] = %d, want 2; got %+v", n, rep.Totals.ReviewAuthors)
		}
	}

	// And the emitted definition says which rule was applied, because the same
	// metric id means two different things under the two settings.
	if def := counting.Definitions["leading.time_to_first_review_p50_hours"]; !strings.Contains(def, "INCLUDING the pull request's author") {
		t.Errorf("the default's definition must say self-review is counted; it says: %s", def)
	}
	if def := excluding.Definitions["leading.time_to_first_review_p50_hours"]; !strings.Contains(def, "EXCEPT the pull request's own author") {
		t.Errorf("the excluding definition must say so; it says: %s", def)
	}
}

// TestReviewExcludesAuthorReportsNothingRatherThanZeroWhenEveryReviewIsTheAuthors
// is the case that decides the DEFAULT.
//
// The known-answer fixture is a repository where the pull-request author and
// the reviewer are the same login — an agent or bot that opens and approves, or
// a solo maintainer. With the switch on, every review metric correctly becomes
// insufficient_data. That is the honest answer, and it is also a useless
// dashboard: which is why this is the non-default and the tool says so out loud
// instead of shipping it silently.
func TestReviewExcludesAuthorReportsNothingRatherThanZeroWhenEveryReviewIsTheAuthors(t *testing.T) {
	cfg := fixtureConfig(t)
	cfg.ReviewExcludesAuthor = true
	rep := computeOrFail(t, "testdata/known-answer.json", cfg)

	for _, id := range []string{
		"leading.time_to_first_review_p50_hours",
		"leading.first_pass_merge_rate",
		"lagging.rework_cycles_per_change_mean",
	} {
		got := recordByID(t, rep, id)
		if got.Status != StatusInsufficient {
			t.Errorf("%s = %v (%s), want insufficient_data: every review in this fixture is by the pull request's own author\n  detail: %s", id, got.Value, got.Status, got.Detail)
		}
		if got.Value != 0 {
			t.Errorf("%s carries value %v while insufficient — a consumer ignoring status would plot it", id, got.Value)
		}
	}

	// The census still shows the five review events that exist. A reader seeing
	// "review_events 5" beside "insufficient_data" can tell this is the
	// self-review case and not a broken fetch; that pairing is the finding.
	if rep.Totals.ReviewEvents != 5 {
		t.Errorf("totals.review_events = %d, want 5 — the census must not be filtered by the switch, or the finding becomes invisible", rep.Totals.ReviewEvents)
	}
	// Thread resolution is not a review event, so this metric is unmoved, and
	// SCHEMA.md §7.1 says so.
	if got := recordByID(t, rep, "lagging.review_threads_settled_without_change_rate"); got.Status != StatusOK || math.Abs(got.Value-0.5) > 1e-9 {
		t.Errorf("review_threads_settled_without_change_rate = %v (%s), want 0.5/ok: it keys on thread RESOLUTION, not on review events", got.Value, got.Status)
	}
	rep.Sinks = PublishAll(rep, []Sink{NewNotionSink(LoadNotionConfig(func(string) string { return "" }))})
	if err := rep.Validate(); err != nil {
		t.Errorf("the report fails its own contract with the switch on: %v", err)
	}
}

// ---------------------------------------------------------------------------
// 3. The defect_containment_rate unit mismatch has to be visible in the OUTPUT.
// ---------------------------------------------------------------------------

// TestTheDefectContainmentUnitCaveatIsInTheEmittedDocument pins the caveat into
// the artefact a consumer actually reads.
//
// The metric divides a count of PULL REQUESTS by a count of PULL REQUESTS plus
// ISSUES. Documenting that in SCHEMA.md alone leaves it invisible to everyone
// downstream — a dashboard shows `value` and `detail`, never the design
// document — so it is asserted in the `definitions` entry AND in the `detail`
// string, on BOTH branches of the metric, and after a full encode/decode round
// trip.
func TestTheDefectContainmentUnitCaveatIsInTheEmittedDocument(t *testing.T) {
	const id = "lagging.defect_containment_rate"

	check := func(t *testing.T, rep Report, wantStatus Status) {
		t.Helper()
		doc, err := rep.Encode()
		if err != nil {
			t.Fatalf("encode: %v", err)
		}
		var back Report
		if err := json.Unmarshal(doc, &back); err != nil {
			t.Fatalf("decode: %v", err)
		}
		rec := recordByID(t, back, id)
		if rec.Status != wantStatus {
			t.Fatalf("status = %q, want %q", rec.Status, wantStatus)
		}
		if !strings.Contains(rec.Detail, DefectContainmentUnitCaveat) {
			t.Errorf("the %s DETAIL does not carry the unit caveat. A consumer reads detail, never SCHEMA.md.\n  detail: %s", id, rec.Detail)
		}
		if def := back.Definitions[id]; !strings.Contains(def, DefectContainmentUnitCaveat) {
			t.Errorf("the %s DEFINITION does not carry the unit caveat.\n  definition: %s", id, def)
		}
		if !strings.Contains(string(doc), "different units") {
			t.Errorf("the caveat's substance must survive into the emitted bytes")
		}
	}

	t.Run("the measured branch", func(t *testing.T) {
		check(t, computeFixture(t), StatusOK)
	})

	// The insufficient branch is the one most likely to lose the caveat, because
	// it is written separately and carries no numbers to attach it to.
	t.Run("the insufficient branch", func(t *testing.T) {
		at := func(d int) time.Time { return time.Date(2026, 6, d, 0, 0, 0, 0, time.UTC) }
		ds := Dataset{
			Repo: "acme/widgets",
			PullRequests: []PullRequest{{
				Number: 1, Author: "a", State: PRMerged,
				CreatedAt: at(2), MergedAt: at(3), Files: []string{"src/x.go"},
			}},
			Issues: []Issue{{
				Number: 9, Author: "b", State: "OPEN", CreatedAt: at(4),
				Labels: []string{"enhancement"}, // no defect label: nothing escaped
			}},
		}
		cfg := DefaultConfig()
		cfg.Repo = "acme/widgets"
		cfg.Now = fixtureNow(t)
		cfg.Window = NewWindow(cfg.Now, 14)
		rep, err := Compute(ds, cfg)
		if err != nil {
			t.Fatalf("Compute: %v", err)
		}
		check(t, rep, StatusInsufficient)
	})
}

// ---------------------------------------------------------------------------
// 4. Every repository-shaped knob is a flag — verified, not asserted in prose.
// ---------------------------------------------------------------------------

// TestEveryConfigKnobIsAFlag walks Config by reflection.
//
// SCHEMA.md §10 claims every repository-shaped setting is a flag. A claim in a
// document that nothing checks is a claim that quietly stops being true the
// first time somebody adds a field and reads it from an environment variable,
// a constant, or the repository's own layout. This is the check.
func TestEveryConfigKnobIsAFlag(t *testing.T) {
	fs := flag.NewFlagSet("sdlc-metrics", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	registerFlags(fs)

	typ := reflect.TypeOf(Config{})
	seen := map[string]bool{}
	for i := 0; i < typ.NumField(); i++ {
		name := typ.Field(i).Name
		seen[name] = true
		flagName, ok := configKnobs[name]
		if !ok {
			t.Errorf("Config.%s has no entry in configKnobs. Every repository-shaped setting is a flag (SCHEMA.md §10); "+
				"add the flag and the mapping, or this tool has a knob that can only be changed by editing it.", name)
			continue
		}
		if fs.Lookup(flagName) == nil {
			t.Errorf("Config.%s maps to flag -%s, which registerFlags does not register", name, flagName)
		}
	}
	for name := range configKnobs {
		if !seen[name] {
			t.Errorf("configKnobs names Config.%s, which does not exist — a stale mapping makes the guard pass while checking nothing", name)
		}
	}
}

// TestTheSelfReviewSwitchIsReachableFromTheCommandLine closes the loop the unit
// tests above leave open: they set Config directly, which proves the
// computation branches and not that anybody can ask for it.
func TestTheSelfReviewSwitchIsReachableFromTheCommandLine(t *testing.T) {
	for _, tc := range []struct {
		args []string
		want string
	}{
		{[]string{"-input", "testdata/peer-review.json", "-repo", "acme/widgets", "-now", "2026-06-15T00:00:00Z", "-window-days", "14", "-out", "-"},
			"INCLUDING the pull request's author"},
		{[]string{"-input", "testdata/peer-review.json", "-repo", "acme/widgets", "-now", "2026-06-15T00:00:00Z", "-window-days", "14", "-out", "-", "-review-excludes-author"},
			"EXCEPT the pull request's own author"},
	} {
		code, stdout, stderr := runCLI(t, tc.args...)
		if code != exitOK {
			t.Fatalf("exit = %d for %v\nstderr:\n%s", code, tc.args, stderr)
		}
		if !strings.Contains(stdout, tc.want) {
			t.Errorf("the emitted document does not state the review rule %q for args %v", tc.want, tc.args)
		}
	}
}
