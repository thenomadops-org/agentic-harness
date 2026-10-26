package main

import (
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// THE COMPUTATION.
//
// Pure: Dataset in, Report out. No clock (Config.Now is passed), no network, no
// environment. Every number in the pull-request body that ships this tool was
// produced by this function over a saved Dataset, and can be produced again.
//
// Read SCHEMA.md beside this file for the operational definition of each metric
// in prose. The definitions map at the bottom of this file is the same text,
// emitted INTO the document, so the dashboard and the doc cannot drift apart.
// ---------------------------------------------------------------------------

// ErrNoSubjects is the vacuity guard. A run that examined nothing is an ERROR,
// never a document full of zeroes.
//
// WHY IT IS AN ERROR AND NOT A WARNING. A quiet week and a broken query produce
// the identical output — a row of zeroes. On the project this tool came from,
// a single overnight audit found four separate checks that ran, examined
// nothing, and reported the reassuring answer. The reassuring answer is the
// dangerous one, because nobody investigates it. So the only output for "I
// examined nothing" is a non-zero exit and a message naming which census came
// back empty.
var ErrNoSubjects = errors.New("nothing to measure")

// Config is everything the computation needs that is not the data.
type Config struct {
	Repo   string
	Window Window
	// Now is the measurement instant. Ages of still-open things are measured
	// against it. Passed in rather than read from the clock so a fixture has a
	// fixed, known answer.
	Now time.Time

	// DefectLabels are the issue labels that mean "this is a defect that
	// reached main". Repository-specific by nature — the collector cannot
	// invent a taxonomy — so it is configuration, it is emitted into the
	// document's definitions, and a repository with no defect labels gets
	// insufficient_data rather than a flattering zero.
	DefectLabels []string
	// ClassLabelPrefixes group defects into classes for the repeat-incident
	// metric, e.g. "proj:". An issue whose labels match no prefix is
	// UNCLASSIFIED and is excluded from the repeat count (and named in the
	// detail), because bucketing everything unlabelled into one class would
	// manufacture a repeat out of a labelling gap.
	ClassLabelPrefixes []string
	// Depth2Roots are the top-level directories under which the SECOND path
	// segment is the meaningful surface: api/<service>, mobile/<shell>. Every
	// other path contributes its first segment.
	//
	// It DEFAULTS TO EMPTY, which is the right answer for a single-service
	// repository: every surface is then a top-level directory. A monorepo sets
	// it (-surface-depth2-roots api,mobile,tools) or every one of its services
	// collapses into the single surface "api" and the surface metrics stop
	// distinguishing anything.
	Depth2Roots []string
	// StaleIssueDays is the age at which an open issue with no pull request is
	// called aged, for the detail string.
	StaleIssueDays int

	// ReviewExcludesAuthor decides whether a review by the pull request's own
	// author counts as a review event. FALSE — self-review counts — is the
	// default, and the reasoning is in SCHEMA.md §7.1. In short: excluding the
	// author is the better definition wherever reviewers are distinct humans,
	// and it reports a flat zero wherever the author and the reviewer are the
	// same login (an agent-run repository, a bot that opens and approves, a
	// solo maintainer). Defaulting it on would make every such repository's
	// review metrics silently empty, which is the failure this tool exists to
	// prevent; defaulting it off overcounts visibly, and totals.review_authors
	// shows the overcount.
	//
	// A REPOSITORY WITH REAL HUMAN REVIEWERS SHOULD SET IT TO TRUE.
	//
	// When true, a review event whose author is empty is also excluded: an
	// unattributed review cannot be shown to be a peer's, and counting it would
	// let the thing the switch excludes back in through a blank field.
	ReviewExcludesAuthor bool
}

// DefaultConfig is the neutral starting point: what a repository gets when it
// passes no flags. It is not a claim about any particular repository, and every
// field in it is a flag (see configKnobs in main.go, which a test walks against
// Config by reflection so a new field cannot arrive without one).
//
// Depth2Roots is deliberately EMPTY here. The monorepo layout it wants —
// api/<service>, mobile/<shell> — belongs to the repository being measured, not
// to this tool, and a default naming somebody else's directories would silently
// mis-bucket every repository that does not share them.
func DefaultConfig() Config {
	return Config{
		DefectLabels:       []string{"bug", "type:bug", "incident", "regression", "defect"},
		ClassLabelPrefixes: []string{"proj:", "area:", "type:"},
		Depth2Roots:        nil,
		StaleIssueDays:     14,
	}
}

// DefectContainmentUnitCaveat is the wart in lagging.defect_containment_rate,
// stated in the DOCUMENT rather than only in SCHEMA.md.
//
// The numerator counts pull requests and the denominator counts issues. That is
// a real defect in the metric, not a rounding concern, and a caveat that lives
// only in a design document is a caveat the person reading metrics.json never
// sees. So it is appended to the metric's `detail` AND carried in its
// `definitions` entry, and a test asserts it is present in both.
const DefectContainmentUnitCaveat = "CAVEAT: the numerator counts PULL REQUESTS and the denominator counts ISSUES. They are different units, so this is a proportion of convenience — readable as a trend against its own history, not as an absolute share of defects."

// reviewEventCounts reports whether a review event by `author` on pr counts,
// under cfg. See Config.ReviewExcludesAuthor.
func (c Config) reviewEventCounts(pr PullRequest, author string) bool {
	if !c.ReviewExcludesAuthor {
		return true
	}
	return author != "" && author != pr.Author
}

// Compute turns one Dataset into one Report.
func Compute(ds Dataset, cfg Config) (Report, error) {
	w := cfg.Window
	now := cfg.Now.UTC()

	// ---- the census, and the vacuity guard over it -------------------------
	var (
		examinedPRs []PullRequest
		mergedPRs   []PullRequest
		openPRs     []PullRequest
	)
	// "Open now" means open AT THE MEASUREMENT INSTANT, which is not the same
	// as open at fetch time. A pull request opened after w.End did not exist
	// when this window was measured, and counting it produced a NEGATIVE age —
	// the first real run of this tool reported
	// flow.open_pr_age_p50_hours = -25.8, which is how the hole was found. A
	// negative age is not a small inaccuracy; it is the metric silently
	// answering a different question than the one it is labelled with.
	openAt := func(created time.Time) bool { return !created.After(w.End) }

	for _, pr := range ds.PullRequests {
		inWindow := w.Contains(pr.CreatedAt) || w.Contains(pr.MergedAt) || w.Contains(pr.ClosedAt)
		isOpen := pr.State == PROpen && openAt(pr.CreatedAt)
		if !inWindow && !isOpen {
			continue
		}
		examinedPRs = append(examinedPRs, pr)
		if isOpen {
			openPRs = append(openPRs, pr)
		}
		if pr.State == PRMerged && w.Contains(pr.MergedAt) {
			mergedPRs = append(mergedPRs, pr)
		}
	}

	var examinedIssues, openIssues []Issue
	for _, is := range ds.Issues {
		isOpen := is.State == "OPEN" && openAt(is.CreatedAt)
		if !w.Contains(is.CreatedAt) && !w.Contains(is.ClosedAt) && !isOpen {
			continue
		}
		examinedIssues = append(examinedIssues, is)
		if isOpen {
			openIssues = append(openIssues, is)
		}
	}

	if len(examinedPRs) == 0 {
		return Report{}, fmt.Errorf("%w: zero pull requests are open or fall in window %s over %d fetched — a quiet period and a broken query produce the same empty set, so this is refused rather than reported as zeroes", ErrNoSubjects, w.ID, len(ds.PullRequests))
	}
	if len(examinedIssues) == 0 {
		return Report{}, fmt.Errorf("%w: zero issues are open or fall in window %s over %d fetched — see above; an issue census that comes back empty is a broken query, not a healthy board", ErrNoSubjects, w.ID, len(ds.Issues))
	}

	reviewEvents, reviewThreads := 0, 0
	reviewAuthors := map[string]int{}
	for _, pr := range examinedPRs {
		reviewEvents += len(pr.Reviews)
		reviewThreads += len(pr.Threads)
		for _, r := range pr.Reviews {
			a := r.Author
			if a == "" {
				a = "(unknown)"
			}
			if a == pr.Author {
				a += " (= pull request author)"
			}
			reviewAuthors[a]++
		}
	}

	rep := Report{
		SchemaVersion: SchemaVersion,
		Repo:          cfg.Repo,
		GeneratedAt:   now,
		Window:        w,
		Collector:     Collector,
		Totals: Totals{
			PullRequestsExamined: len(examinedPRs),
			PullRequestsMerged:   len(mergedPRs),
			PullRequestsOpen:     len(openPRs),
			IssuesExamined:       len(examinedIssues),
			IssuesOpen:           len(openIssues),
			ReviewEvents:         reviewEvents,
			ReviewThreads:        reviewThreads,
			ReviewAuthors:        reviewAuthors,
		},
		Definitions: definitions(cfg),
	}

	add := func(r Record) {
		r.Window = w
		r.MeasuredAt = now
		r.Family = family(r.MetricID)
		if r.Status == StatusInsufficient {
			r.Value = 0
		}
		rep.Metrics = append(rep.Metrics, r)
	}

	// =======================================================================
	// FLOW — what is in motion right now.
	// =======================================================================

	// --- open issues with no pull request ----------------------------------
	var noPR []Issue
	for _, is := range openIssues {
		if len(is.LinkedPRs) == 0 {
			noPR = append(noPR, is)
		}
	}
	aged, oldest, oldestNum := 0, 0.0, 0
	var noPRAges []float64
	for _, is := range noPR {
		d := now.Sub(is.CreatedAt).Hours() / 24
		noPRAges = append(noPRAges, d)
		if d >= float64(cfg.StaleIssueDays) {
			aged++
		}
		if d > oldest {
			oldest, oldestNum = d, is.Number
		}
	}
	detail := fmt.Sprintf("%d of %d open issues have no pull request referencing them; %d are at least %d days old.",
		len(noPR), len(openIssues), aged, cfg.StaleIssueDays)
	if oldestNum != 0 {
		detail += fmt.Sprintf(" Oldest: #%d at %.0f days.", oldestNum, oldest)
	}
	add(Record{
		MetricID: "flow.open_issues_without_pr",
		Title:    "Open issues with no pull request",
		Value:    float64(len(noPR)),
		Unit:     UnitCount,
		Status:   StatusOK, // a count over an enumerated population; 0 is a fact
		Subjects: len(openIssues),
		Detail:   detail,
	})
	add(medianRecord("flow.open_issues_without_pr_age_p50_days",
		"Median age of open issues with no pull request", UnitDays, noPRAges,
		func(v float64, n int) string {
			return fmt.Sprintf("Median age %.1f days across %d issues with no pull request.", v, n)
		},
		"No open issue is without a pull request, so there is no age distribution to take a median of."))

	// --- open pull requests -------------------------------------------------
	var prAges, awaiting []float64
	for _, pr := range openPRs {
		prAges = append(prAges, now.Sub(pr.CreatedAt).Hours())
	}
	var awaitingNums []int
	for _, pr := range openPRs {
		if pr.Draft {
			continue // a draft is not waiting on anybody
		}
		since, waiting := awaitingReviewSince(pr, cfg)
		if !waiting {
			continue
		}
		awaiting = append(awaiting, now.Sub(since).Hours())
		awaitingNums = append(awaitingNums, pr.Number)
	}
	add(Record{
		MetricID: "flow.open_prs",
		Title:    "Open pull requests",
		Value:    float64(len(openPRs)),
		Unit:     UnitCount,
		Status:   StatusOK,
		Subjects: len(examinedPRs),
		Detail: fmt.Sprintf("%d pull requests are open out of %d examined in window %s.",
			len(openPRs), len(examinedPRs), w.ID),
	})
	add(medianRecord("flow.open_pr_age_p50_hours",
		"Median age of open pull requests", UnitHours, prAges,
		func(v float64, n int) string {
			return fmt.Sprintf("Median open pull request is %.1f hours old, across %d.", v, n)
		},
		"No pull request is open, so there is no age distribution."))
	add(medianRecord("flow.open_pr_awaiting_review_p50_hours",
		"Median wait on review, open pull requests", UnitHours, awaiting,
		func(v float64, n int) string {
			return fmt.Sprintf("%d open pull requests have had no review since their most recent branch change; median wait %.1f hours (%s).",
				n, v, numberList(awaitingNums, 5))
		},
		"Every open non-draft pull request has a review after its most recent branch change, so nothing is waiting."))

	// --- work in flight per surface ----------------------------------------
	surfaces := map[string]int{}
	truncated := 0
	for _, pr := range openPRs {
		for _, s := range surfacesOf(pr.Files, cfg.Depth2Roots) {
			surfaces[s]++
		}
		if pr.FilesTruncated {
			truncated++
		}
	}
	sdetail := fmt.Sprintf("%d distinct surfaces are touched by the %d open pull requests: %s.",
		len(surfaces), len(openPRs), topSurfaces(surfaces, 6))
	if truncated > 0 {
		sdetail += fmt.Sprintf(" %d of them had a truncated file list, so this under-counts.", truncated)
	}
	add(Record{
		MetricID: "flow.surfaces_in_flight",
		Title:    "Distinct surfaces with work in flight",
		Value:    float64(len(surfaces)),
		Unit:     UnitCount,
		Status:   StatusOK,
		Subjects: len(openPRs),
		Detail:   sdetail,
	})

	// Which surfaces are hot over the WHOLE window, not just right now. With
	// nothing open the metric above is 0 and true and useless; this one still
	// answers "where is the work".
	windowSurfaces := map[string]int{}
	for _, pr := range examinedPRs {
		for _, s := range surfacesOf(pr.Files, cfg.Depth2Roots) {
			windowSurfaces[s]++
		}
	}
	add(Record{
		MetricID: "flow.surfaces_touched_in_window",
		Title:    "Distinct surfaces touched in window",
		Value:    float64(len(windowSurfaces)),
		Unit:     UnitCount,
		Status:   StatusOK,
		Subjects: len(examinedPRs),
		Detail: fmt.Sprintf("%d distinct surfaces were touched by %d pull requests in window %s. Hottest: %s.",
			len(windowSurfaces), len(examinedPRs), w.ID, topSurfaces(windowSurfaces, 6)),
	})

	// =======================================================================
	// LEADING — the speed of the process.
	// =======================================================================

	// --- issue opened -> pull request opened --------------------------------
	prByNumber := map[int]PullRequest{}
	for _, pr := range ds.PullRequests {
		prByNumber[pr.Number] = pr
	}
	// A pull request's `#nnn` body mentions are the dominant linkage in this
	// repository (a closing keyword is forbidden here), so they are folded in
	// alongside the issue-side timeline links.
	mentionedBy := map[int][]PullRequest{}
	for _, pr := range ds.PullRequests {
		for _, n := range append(append([]int{}, pr.ClosingIssues...), pr.MentionedIssues...) {
			mentionedBy[n] = append(mentionedBy[n], pr)
		}
	}
	var issueToPR []float64
	linked, unlinked := 0, 0
	for _, is := range examinedIssues {
		if !w.Contains(is.CreatedAt) {
			continue
		}
		first, ok := firstPRAfter(is, mentionedBy[is.Number], prByNumber)
		if !ok {
			unlinked++
			continue
		}
		linked++
		issueToPR = append(issueToPR, first.Sub(is.CreatedAt).Hours())
	}
	add(medianRecord("leading.issue_to_pr_p50_hours",
		"Median hours from issue opened to first pull request", UnitHours, issueToPR,
		func(v float64, n int) string {
			return fmt.Sprintf("Median %.1f hours across %d issues opened in window that acquired a pull request; %d opened in window still have none.", v, n, unlinked)
		},
		fmt.Sprintf("No issue opened in this window has an associated pull request (%d issues opened, %d without), so there is no latency to measure.", linked+unlinked, unlinked)))

	// --- time to first review ------------------------------------------------
	var toFirstReview []float64
	unreviewed := 0
	for _, pr := range examinedPRs {
		if !w.Contains(pr.CreatedAt) {
			continue
		}
		rs, ok := firstReviewAt(pr, cfg)
		if !ok {
			unreviewed++
			continue
		}
		d := rs.Sub(pr.ReviewClockStart()).Hours()
		if d < 0 {
			d = 0 // a review submitted before ready-for-review; clamp, do not drop
		}
		toFirstReview = append(toFirstReview, d)
	}
	add(medianRecord("leading.time_to_first_review_p50_hours",
		"Median hours from ready-for-review to first review", UnitHours, toFirstReview,
		func(v float64, n int) string {
			return fmt.Sprintf("Median %.2f hours across %d pull requests opened in window that received a review; %d received none at all.", v, n, unreviewed)
		},
		"No pull request opened in this window received any review event, so there is no latency to measure. That is a finding, not a zero."))

	// --- first implementation pass -------------------------------------------
	firstPass, reviewedMerged, unreviewedMerged := 0, 0, 0
	var reworkPerPR []float64
	var reworkedNums []int
	for _, pr := range mergedPRs {
		cycles, reviewed := reworkCycles(pr, cfg)
		if !reviewed {
			unreviewedMerged++
			continue
		}
		reviewedMerged++
		reworkPerPR = append(reworkPerPR, float64(cycles))
		if cycles == 0 {
			firstPass++
		} else {
			reworkedNums = append(reworkedNums, pr.Number)
		}
	}
	if reviewedMerged == 0 {
		add(Record{
			MetricID: "leading.first_pass_merge_rate",
			Title:    "Share merging on the first implementation pass",
			Unit:     UnitRatio,
			Status:   StatusInsufficient,
			Subjects: 0,
			Detail: fmt.Sprintf("None of the %d pull requests merged in this window carried any review event, so there is no first pass to distinguish from a second. %d merged unreviewed.",
				len(mergedPRs), unreviewedMerged),
		})
	} else {
		add(Record{
			MetricID: "leading.first_pass_merge_rate",
			Title:    "Share merging on the first implementation pass",
			Value:    float64(firstPass) / float64(reviewedMerged),
			Unit:     UnitRatio,
			Status:   StatusOK,
			Subjects: reviewedMerged,
			Detail: fmt.Sprintf("%d of %d reviewed pull requests merged in window took no branch change after review began; %d merged with no review at all and are excluded.",
				firstPass, reviewedMerged, unreviewedMerged),
		})
	}

	// =======================================================================
	// LAGGING — quality and rework.
	// =======================================================================

	add(meanRecord("lagging.rework_cycles_per_change_mean",
		"Mean rework cycles per reviewed change", UnitCycles, reworkPerPR,
		func(v float64, n int) string {
			return fmt.Sprintf("Mean %.2f rework cycles across %d reviewed pull requests merged in window; %d of them took at least one (%s).",
				v, n, len(reworkedNums), numberList(reworkedNums, 5))
		},
		"No reviewed pull request merged in this window, so there is no rework distribution."))

	// --- defects caught before merge vs escaped ------------------------------
	defectLabels := map[string]bool{}
	for _, l := range cfg.DefectLabels {
		defectLabels[l] = true
	}
	caught := 0
	var caughtNums []int
	for _, pr := range mergedPRs {
		cycles, reviewed := reworkCycles(pr, cfg)
		if !reviewed {
			continue
		}
		if cycles > 0 || hasChangesRequested(pr, cfg) {
			caught++
			caughtNums = append(caughtNums, pr.Number)
		}
	}
	var escapedIssues []Issue
	for _, is := range examinedIssues {
		if w.Contains(is.CreatedAt) && hasAny(is.Labels, defectLabels) {
			escapedIssues = append(escapedIssues, is)
		}
	}
	escaped := len(escapedIssues)
	add(Record{
		MetricID: "lagging.defects_caught_before_merge",
		Title:    "Defects caught before merge",
		Value:    float64(caught),
		Unit:     UnitCount,
		Status:   StatusOK,
		Subjects: reviewedMerged,
		Detail: fmt.Sprintf("%d of %d reviewed pull requests merged in window required a change after review or carried a changes-requested review (%s).",
			caught, reviewedMerged, numberList(caughtNums, 5)),
	})
	add(Record{
		MetricID: "lagging.defects_escaped_to_production",
		Title:    "Defects escaping to production",
		Value:    float64(escaped),
		Unit:     UnitCount,
		Status:   StatusOK,
		Subjects: len(examinedIssues),
		Detail: fmt.Sprintf("%d issues opened in window carry a defect label (%s) out of %d issues examined.",
			escaped, strings.Join(cfg.DefectLabels, ", "), len(examinedIssues)),
	})
	if caught+escaped == 0 {
		add(Record{
			MetricID: "lagging.defect_containment_rate",
			Title:    "Share of defects caught before merge",
			Unit:     UnitRatio,
			Status:   StatusInsufficient,
			Subjects: 0,
			Detail:   "No defect was caught in review and none was reported as an issue in this window, so the containment ratio has no denominator. Zero known defects is not the same as a 100% containment rate and is not reported as one. " + DefectContainmentUnitCaveat,
		})
	} else {
		add(Record{
			MetricID: "lagging.defect_containment_rate",
			Title:    "Share of defects caught before merge",
			Value:    float64(caught) / float64(caught+escaped),
			Unit:     UnitRatio,
			Status:   StatusOK,
			Subjects: caught + escaped,
			Detail: fmt.Sprintf("%d caught in review, %d escaped as labelled issues, %d total. %s",
				caught, escaped, caught+escaped, DefectContainmentUnitCaveat),
		})
	}

	// --- review threads settled without a branch change -----------------------
	resolvedTotal, resolvedNoChange := 0, 0
	for _, pr := range examinedPRs {
		for _, th := range pr.Threads {
			if !th.Resolved {
				continue
			}
			resolvedTotal++
			if !changeAfter(pr, th.LastCommentAt()) {
				resolvedNoChange++
			}
		}
	}
	if resolvedTotal == 0 {
		add(Record{
			MetricID: "lagging.review_threads_settled_without_change_rate",
			Title:    "Review threads settled without a branch change",
			Unit:     UnitRatio,
			Status:   StatusInsufficient,
			Subjects: 0,
			Detail: fmt.Sprintf("None of the %d pull requests examined carries a RESOLVED review thread (%d threads in total), so there is nothing to take a share of. On a repository whose review happens as whole-review comments rather than per-line threads this metric will stay unmeasured; that is a property of the review style, not a score.",
				len(examinedPRs), reviewThreads),
		})
	} else {
		add(Record{
			MetricID: "lagging.review_threads_settled_without_change_rate",
			Title:    "Review threads settled without a branch change",
			Value:    float64(resolvedNoChange) / float64(resolvedTotal),
			Unit:     UnitRatio,
			Status:   StatusOK,
			Subjects: resolvedTotal,
			Detail: fmt.Sprintf("%d of %d resolved review threads had no commit or force push after their last comment.",
				resolvedNoChange, resolvedTotal),
		})
	}

	// --- repeat defect classes ------------------------------------------------
	classes := map[string][]int{}
	unclassified := 0
	for _, is := range escapedIssues {
		c := classOf(is.Labels, cfg.ClassLabelPrefixes)
		if c == "" {
			unclassified++
			continue
		}
		classes[c] = append(classes[c], is.Number)
	}
	repeat := 0
	var repeatNames []string
	for c, nums := range classes {
		if len(nums) >= 2 {
			repeat++
			repeatNames = append(repeatNames, fmt.Sprintf("%s×%d", c, len(nums)))
		}
	}
	sort.Strings(repeatNames)
	rdetail := fmt.Sprintf("%d defect classes have two or more labelled issues in window (%s), across %d classified defect issues.",
		repeat, orNone(strings.Join(repeatNames, ", ")), len(escapedIssues)-unclassified)
	if unclassified > 0 {
		rdetail += fmt.Sprintf(" %d defect issues carry no label matching %s and are excluded rather than bucketed together.",
			unclassified, strings.Join(cfg.ClassLabelPrefixes, "/"))
	}
	add(Record{
		MetricID: "lagging.repeat_defect_classes",
		Title:    "Repeat defect classes",
		Value:    float64(repeat),
		Unit:     UnitCount,
		Status:   StatusOK,
		Subjects: len(escapedIssues),
		Detail:   rdetail,
	})

	return rep, nil
}

// ---------------------------------------------------------------------------
// The definitions of the two load-bearing terms — "review event" and "rework
// cycle" — and of everything else, in one place.
// ---------------------------------------------------------------------------

// reworkCycles counts REVIEW -> CHANGE transitions on a pull request.
//
// THE OPERATIONAL DEFINITION, stated once:
//
//	Merge every review event (a submitted review, or a review-thread comment)
//	and every change event (a commit on the head branch, or a force push) into
//	one timeline ordered by timestamp, REVIEWS FIRST on a tie. Walk it. A
//	review arms the counter; the next change after an armed counter is ONE
//	rework cycle and disarms it. Changes before any review are the first
//	implementation pass and count for nothing.
//
//	    commit commit REVIEW commit REVIEW merge   -> 1 cycle
//	    commit REVIEW REVIEW commit commit merge   -> 1 cycle (one round trip)
//	    commit commit REVIEW merge                 -> 0 cycles, FIRST PASS
//	    commit commit merge                        -> unreviewed, EXCLUDED
//
// A pull request with zero review events is reported as unreviewed and is
// excluded from both the first-pass rate and the rework mean, never counted as
// a first pass. Merging with no review is not evidence of getting it right the
// first time; it is evidence of no review.
//
// KNOWN MEASUREMENT ERROR, stated rather than discovered later: a commit's
// timestamp is its committer date, not its push time. A commit authored before
// a review and pushed after it is dated before the review and will not register
// as rework. Force pushes are collected precisely because the common form of
// that case — amending in response to review — leaves no new commit node.
func reworkCycles(pr PullRequest, cfg Config) (cycles int, reviewed bool) {
	type ev struct {
		at     time.Time
		review bool
	}
	var evs []ev
	for _, r := range pr.Reviews {
		if !cfg.reviewEventCounts(pr, r.Author) {
			continue
		}
		evs = append(evs, ev{r.SubmittedAt, true})
	}
	for _, th := range pr.Threads {
		for _, c := range th.Comments {
			if !cfg.reviewEventCounts(pr, c.Author) {
				continue
			}
			evs = append(evs, ev{c.CreatedAt, true})
		}
	}
	reviewed = len(evs) > 0
	for _, c := range pr.Changes {
		evs = append(evs, ev{c.At, false})
	}
	sort.SliceStable(evs, func(i, j int) bool {
		if evs[i].at.Equal(evs[j].at) {
			// Reviews first on a tie: a change stamped at the same instant as a
			// review is counted as responding to it. The alternative silently
			// forgives same-second rework.
			return evs[i].review && !evs[j].review
		}
		return evs[i].at.Before(evs[j].at)
	})
	armed := false
	for _, e := range evs {
		if e.review {
			armed = true
			continue
		}
		if armed {
			cycles++
			armed = false
		}
	}
	return cycles, reviewed
}

// firstReviewAt is the earliest review event of any kind on the pull request.
//
// ON AUTHOR IDENTITY, and why the DEFAULT does not exclude self-review.
// The obvious definition is "the first review by somebody other than the
// author", and wherever reviewers are distinct humans it is the better one —
// set -review-excludes-author and you get it.
//
// It is the wrong DEFAULT because on a whole class of repository it reports
// zero rather than reporting a problem. On one project every pull request was
// opened by a GitHub App on behalf of an agent and reviewed by that same login;
// author identity could not separate self-review from peer review at all, so a
// non-author rule classified 100% of review activity as self-review and emitted
// an empty set for every review metric. A bot that opens and approves, or a
// solo maintainer, lands in the same place.
//
// So: default off, switch present, and totals.review_authors published in both
// modes so a reader can see whose review is being counted instead of assuming a
// human's.
func firstReviewAt(pr PullRequest, cfg Config) (time.Time, bool) {
	var first time.Time
	for _, r := range pr.Reviews {
		if !cfg.reviewEventCounts(pr, r.Author) {
			continue
		}
		if first.IsZero() || r.SubmittedAt.Before(first) {
			first = r.SubmittedAt
		}
	}
	for _, th := range pr.Threads {
		for _, c := range th.Comments {
			if !cfg.reviewEventCounts(pr, c.Author) {
				continue
			}
			if !c.CreatedAt.IsZero() && (first.IsZero() || c.CreatedAt.Before(first)) {
				first = c.CreatedAt
			}
		}
	}
	return first, !first.IsZero()
}

// awaitingReviewSince returns when the pull request started waiting, and
// whether it is waiting at all. It is waiting when its most recent branch
// movement (or its ready-for-review moment, if later) has no review after it.
func awaitingReviewSince(pr PullRequest, cfg Config) (time.Time, bool) {
	since := pr.ReviewClockStart()
	for _, c := range pr.Changes {
		if c.At.After(since) {
			since = c.At
		}
	}
	for _, r := range pr.Reviews {
		if cfg.reviewEventCounts(pr, r.Author) && r.SubmittedAt.After(since) {
			return time.Time{}, false
		}
	}
	for _, th := range pr.Threads {
		for _, c := range th.Comments {
			if cfg.reviewEventCounts(pr, c.Author) && c.CreatedAt.After(since) {
				return time.Time{}, false
			}
		}
	}
	return since, true
}

// hasChangesRequested reports whether any review asked for changes.
func hasChangesRequested(pr PullRequest, cfg Config) bool {
	for _, r := range pr.Reviews {
		if !cfg.reviewEventCounts(pr, r.Author) {
			continue
		}
		if strings.EqualFold(r.State, "CHANGES_REQUESTED") {
			return true
		}
	}
	return false
}

// changeAfter reports whether the branch moved strictly after t.
func changeAfter(pr PullRequest, t time.Time) bool {
	if t.IsZero() {
		return false
	}
	for _, c := range pr.Changes {
		if c.At.After(t) {
			return true
		}
	}
	return false
}

// firstPRAfter is the creation time of the earliest pull request associated
// with the issue and created at or after it. Pull requests that predate the
// issue are excluded: a pull request referenced by an issue filed afterwards
// did not answer it, and counting it produces a negative latency.
func firstPRAfter(is Issue, mentioners []PullRequest, byNumber map[int]PullRequest) (time.Time, bool) {
	var best time.Time
	consider := func(created time.Time) {
		if created.IsZero() || created.Before(is.CreatedAt) {
			return
		}
		if best.IsZero() || created.Before(best) {
			best = created
		}
	}
	for _, l := range is.LinkedPRs {
		created := l.CreatedAt
		if created.IsZero() {
			if pr, ok := byNumber[l.Number]; ok {
				created = pr.CreatedAt
			}
		}
		consider(created)
	}
	for _, pr := range mentioners {
		consider(pr.CreatedAt)
	}
	return best, !best.IsZero()
}

// surfacesOf maps file paths to the distinct surfaces they belong to.
func surfacesOf(files []string, depth2 []string) []string {
	roots := map[string]bool{}
	for _, r := range depth2 {
		roots[r] = true
	}
	seen := map[string]bool{}
	var out []string
	for _, f := range files {
		s := surfaceOf(f, roots)
		if s == "" || seen[s] {
			continue
		}
		seen[s] = true
		out = append(out, s)
	}
	sort.Strings(out)
	return out
}

// surfaceOf is the first path segment, or the first two when the first is one
// of the depth-2 roots (api/<service>, mobile/<shell>). A file at the
// repository root is its own surface, named "(root)", rather than being
// dropped: dropping it is how a change to the Makefile becomes invisible.
func surfaceOf(path string, depth2 map[string]bool) string {
	path = strings.TrimPrefix(strings.TrimSpace(path), "./")
	if path == "" {
		return ""
	}
	parts := strings.Split(path, "/")
	if len(parts) == 1 {
		return "(root)"
	}
	if depth2[parts[0]] && len(parts) >= 3 {
		return parts[0] + "/" + parts[1]
	}
	return parts[0]
}

// classOf is the defect class: the sorted set of the issue's labels that match
// one of the configured prefixes, joined with "+". Empty when none match.
func classOf(labels []string, prefixes []string) string {
	var hit []string
	for _, l := range labels {
		for _, p := range prefixes {
			if strings.HasPrefix(l, p) {
				hit = append(hit, l)
				break
			}
		}
	}
	if len(hit) == 0 {
		return ""
	}
	sort.Strings(hit)
	return strings.Join(hit, "+")
}

// ---------------------------------------------------------------------------
// Small shared builders. medianRecord and meanRecord exist so that the
// "a statistic over an empty set is insufficient_data, never 0" rule is written
// ONCE and cannot be forgotten at one of nine call sites.
// ---------------------------------------------------------------------------

func medianRecord(id, title string, unit Unit, xs []float64, ok func(float64, int) string, empty string) Record {
	if len(xs) == 0 {
		return Record{MetricID: id, Title: title, Unit: unit, Status: StatusInsufficient, Subjects: 0, Detail: empty}
	}
	v := median(xs)
	return Record{MetricID: id, Title: title, Value: v, Unit: unit, Status: StatusOK, Subjects: len(xs), Detail: ok(v, len(xs))}
}

func meanRecord(id, title string, unit Unit, xs []float64, ok func(float64, int) string, empty string) Record {
	if len(xs) == 0 {
		return Record{MetricID: id, Title: title, Unit: unit, Status: StatusInsufficient, Subjects: 0, Detail: empty}
	}
	var sum float64
	for _, x := range xs {
		sum += x
	}
	v := sum / float64(len(xs))
	return Record{MetricID: id, Title: title, Value: v, Unit: unit, Status: StatusOK, Subjects: len(xs), Detail: ok(v, len(xs))}
}

// median is the 50th percentile, averaging the two middle values on an even
// count. Panics on an empty slice by contract — every caller goes through
// medianRecord, which handles empty as insufficient_data.
func median(xs []float64) float64 {
	s := append([]float64(nil), xs...)
	sort.Float64s(s)
	n := len(s)
	if n%2 == 1 {
		return s[n/2]
	}
	return (s[n/2-1] + s[n/2]) / 2
}

func family(id string) string {
	if i := strings.Index(id, "."); i > 0 {
		return id[:i]
	}
	return "unknown"
}

func topSurfaces(m map[string]int, n int) string {
	if len(m) == 0 {
		return "none"
	}
	type kv struct {
		k string
		v int
	}
	var xs []kv
	for k, v := range m {
		xs = append(xs, kv{k, v})
	}
	sort.Slice(xs, func(i, j int) bool {
		if xs[i].v != xs[j].v {
			return xs[i].v > xs[j].v
		}
		return xs[i].k < xs[j].k
	})
	if len(xs) > n {
		xs = xs[:n]
	}
	parts := make([]string, 0, len(xs))
	for _, x := range xs {
		parts = append(parts, fmt.Sprintf("%s×%d", x.k, x.v))
	}
	return strings.Join(parts, ", ")
}

func numberList(nums []int, max int) string {
	if len(nums) == 0 {
		return "none"
	}
	s := append([]int(nil), nums...)
	sort.Ints(s)
	parts := make([]string, 0, max)
	for i, n := range s {
		if i == max {
			parts = append(parts, fmt.Sprintf("and %d more", len(s)-max))
			break
		}
		parts = append(parts, fmt.Sprintf("#%d", n))
	}
	return strings.Join(parts, " ")
}

func orNone(s string) string {
	if s == "" {
		return "none"
	}
	return s
}

// reviewAuthorRule renders, in one clause, which logins the run counted as
// reviewers. It goes into the DOCUMENT rather than only into SCHEMA.md, because
// the same metric id means two different things under the two settings of
// -review-excludes-author and a consumer plotting a history across a change of
// that flag would otherwise never know.
func reviewAuthorRule(cfg Config) string {
	if cfg.ReviewExcludesAuthor {
		return "from any login EXCEPT the pull request's own author (-review-excludes-author=true); an unattributed review is excluded too, since it cannot be shown to be a peer's"
	}
	return "from any login INCLUDING the pull request's author (-review-excludes-author=false, the default)"
}

// depth2Clause renders the surface rule's configured exception, or says plainly
// that there is none.
func depth2Clause(cfg Config) string {
	if len(cfg.Depth2Roots) == 0 {
		return ", with no depth-2 roots configured (-surface-depth2-roots is empty), so every surface is a top-level directory"
	}
	return ", or the first two under " + strings.Join(cfg.Depth2Roots, ", ") + " (-surface-depth2-roots)"
}

// definitions is the operational definition of every metric id, emitted into
// the document. SCHEMA.md carries the same text at length; this is the version
// a dashboard shows next to the number.
func definitions(cfg Config) map[string]string {
	return map[string]string{
		"flow.open_issues_without_pr":                        "Count of OPEN issues with no pull request in their GitHub timeline (CONNECTED_EVENT / CROSS_REFERENCED_EVENT), at measurement time. Not window-scoped: an issue open for six months is in flight today.",
		"flow.open_issues_without_pr_age_p50_days":           "Median age in days, at measurement time, of the issues counted by flow.open_issues_without_pr.",
		"flow.open_prs":                                      "Count of pull requests in state OPEN at measurement time. Not window-scoped.",
		"flow.open_pr_age_p50_hours":                         "Median hours since creation of the pull requests counted by flow.open_prs.",
		"flow.open_pr_awaiting_review_p50_hours":             "Median hours that open, non-draft pull requests have been waiting on review. A pull request is waiting when its most recent branch change (or its ready-for-review moment, whichever is later) has no review event after it; one whose latest change is already reviewed contributes nothing rather than a zero.",
		"flow.surfaces_in_flight":                            "Count of distinct surfaces touched by open pull requests. A surface is the first path segment of a changed file" + depth2Clause(cfg) + ".",
		"flow.surfaces_touched_in_window":                    "Count of distinct surfaces touched by every pull request examined in the window. Answers 'where is the work' when nothing happens to be open.",
		"leading.issue_to_pr_p50_hours":                      "Median hours from an issue being opened IN THE WINDOW to the creation of the earliest pull request associated with it and created at or after it. Association is the union of the issue timeline's linked pull requests and `#nnn` mentions in a pull request's title or body — a closing keyword alone is not enough, because not every project's convention produces one.",
		"leading.time_to_first_review_p50_hours":             "Median hours from a pull request becoming reviewable (ready-for-review, else creation) to its first review event, over pull requests OPENED in the window that received one. A review event is a submitted review or a review-thread comment, " + reviewAuthorRule(cfg) + " — see SCHEMA.md §7.1.",
		"leading.first_pass_merge_rate":                      "Share of pull requests MERGED in the window, and carrying at least one review event (" + reviewAuthorRule(cfg) + "), whose head branch took no commit or force push after the first review event. Pull requests merged with no review at all are EXCLUDED from both numerator and denominator, never counted as a first pass.",
		"lagging.rework_cycles_per_change_mean":              "Mean number of REVIEW-then-CHANGE transitions per reviewed pull request merged in the window. One cycle is one round trip: a review, then a branch change answering it.",
		"lagging.defects_caught_before_merge":                "Count of pull requests merged in the window that carried at least one rework cycle or at least one CHANGES_REQUESTED review — a defect found while the change was still a proposal.",
		"lagging.defects_escaped_to_production":              "Count of issues opened in the window carrying any of the defect labels " + strings.Join(cfg.DefectLabels, ", ") + ". Label-driven by necessity: nothing in GitHub metadata distinguishes a defect from a feature request without one.",
		"lagging.defect_containment_rate":                    "defects_caught_before_merge / (defects_caught_before_merge + defects_escaped_to_production). Insufficient_data when both are zero — zero known defects is not a 100% containment rate. " + DefectContainmentUnitCaveat,
		"lagging.review_threads_settled_without_change_rate": "Share of RESOLVED review threads on examined pull requests that had no commit or force push after the thread's last comment. Keyed on thread RESOLUTION rather than on review events, so -review-excludes-author does not change it. GitHub exposes no resolvedAt timestamp on a thread, so the last comment is the only available lower bound; the metric is stated in those terms rather than pretending to a precision it does not have.",
		"lagging.repeat_defect_classes":                      "Count of defect classes with two or more labelled defect issues opened in the window. A class is the sorted set of an issue's labels matching " + strings.Join(cfg.ClassLabelPrefixes, " / ") + "; an issue matching none is excluded, not bucketed with the other unlabelled ones.",
	}
}
