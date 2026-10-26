package main

import "time"

// ---------------------------------------------------------------------------
// THE NORMALISED INPUT.
//
// Everything downstream of this file is pure: Compute takes a Dataset and
// returns a Report, with no clock, no network and no environment. That split is
// deliberate and it is the reason the tests are worth anything — the fetch is
// the boring half and the computation is where a wrong number comes from, so
// the computation is what the fixtures exercise.
//
// Dataset also has a stable JSON encoding, and `--dump-dataset` writes it. That
// is not a debugging convenience: it is how a published baseline stays
// reproducible. A number in a pull-request body that cannot be recomputed from
// a saved input is a number nobody can check a year later.
// ---------------------------------------------------------------------------

// Dataset is one repository's GitHub metadata, already reduced to the fields
// the metrics need. It carries NO product data and nothing that is not already
// public in the repository's issue and pull-request metadata.
type Dataset struct {
	Repo         string        `json:"repo"`
	CollectedAt  time.Time     `json:"collected_at"`
	PullRequests []PullRequest `json:"pull_requests"`
	Issues       []Issue       `json:"issues"`
}

// PRState mirrors GitHub's pull-request state.
type PRState string

const (
	PROpen   PRState = "OPEN"
	PRMerged PRState = "MERGED"
	PRClosed PRState = "CLOSED"
)

// PullRequest is one pull request and the events on it that bear on process.
type PullRequest struct {
	Number    int       `json:"number"`
	Title     string    `json:"title"`
	Body      string    `json:"body,omitempty"`
	Author    string    `json:"author"`
	State     PRState   `json:"state"`
	Draft     bool      `json:"draft"`
	CreatedAt time.Time `json:"created_at"`
	// ReadyForReviewAt is when a draft became reviewable. Zero when the pull
	// request was never a draft, in which case CreatedAt is the start of the
	// review clock. Measuring time-to-first-review from CreatedAt on a pull
	// request that sat in draft for two days measures the author's writing
	// time, not the reviewer's latency.
	ReadyForReviewAt time.Time `json:"ready_for_review_at,omitempty"`
	MergedAt         time.Time `json:"merged_at,omitempty"`
	ClosedAt         time.Time `json:"closed_at,omitempty"`
	Labels           []string  `json:"labels,omitempty"`
	// Files are the paths this pull request touches. Truncated by the
	// collector at a page boundary; FilesTruncated says so, because a surface
	// histogram built on a silently truncated file list under-reports exactly
	// the biggest changes.
	Files          []string `json:"files,omitempty"`
	FilesTruncated bool     `json:"files_truncated,omitempty"`
	// Changes are every event that altered the branch: a commit, or a force
	// push. Sorted ascending by the collector; Compute sorts again rather than
	// trusting it.
	Changes []ChangeEvent `json:"changes,omitempty"`
	// Reviews are submitted pull-request reviews.
	Reviews []Review `json:"reviews,omitempty"`
	// Threads are review conversation threads.
	Threads []ReviewThread `json:"threads,omitempty"`
	// ClosingIssues are issues GitHub itself links as closed by this pull
	// request (the `closingIssuesReferences` connection). On a project whose
	// contributing rules forbid a closing keyword bound in prose, this set is
	// mostly empty and MentionedIssues below carries nearly all the linkage;
	// on a project that requires "Closes #n" it is the other way round. Both
	// are collected, because neither alone is enough for both conventions.
	ClosingIssues []int `json:"closing_issues,omitempty"`
	// MentionedIssues are `#nnn` references in the title or body that resolve
	// to an issue number present in Dataset.Issues.
	MentionedIssues []int `json:"mentioned_issues,omitempty"`
}

// ChangeKind distinguishes the two ways a branch moves.
type ChangeKind string

const (
	// ChangeCommit is a commit present on the head branch. Its timestamp is
	// the commit's committer date, which is NOT the push time: a commit
	// authored before a review and pushed after it is dated before the
	// review and will not register as rework. Stated here because it is the
	// known measurement error in the rework metric, not a bug to be found
	// later. ChangeForcePush below is the signal that catches the common case.
	ChangeCommit ChangeKind = "commit"
	// ChangeForcePush is a HeadRefForcePushedEvent: the branch was rewritten.
	// An amended commit leaves no new commit node, so without this event a
	// rewrite-based rework cycle is invisible.
	ChangeForcePush ChangeKind = "force_push"
)

// ChangeEvent is one movement of the head branch.
type ChangeEvent struct {
	Kind ChangeKind `json:"kind"`
	At   time.Time  `json:"at"`
	// Actor is the login that produced it where GitHub reports one. A commit
	// with no linked GitHub user leaves this empty; nothing keys off it.
	Actor string `json:"actor,omitempty"`
	SHA   string `json:"sha,omitempty"`
}

// Review is a submitted pull-request review.
type Review struct {
	Author string `json:"author"`
	// State is APPROVED / CHANGES_REQUESTED / COMMENTED / DISMISSED.
	State       string    `json:"state"`
	SubmittedAt time.Time `json:"submitted_at"`
}

// ReviewThread is one conversation on a diff.
type ReviewThread struct {
	ID       string `json:"id"`
	Resolved bool   `json:"resolved"`
	// ResolvedBy is the login that resolved it, empty when unresolved.
	ResolvedBy string `json:"resolved_by,omitempty"`
	// Comments are the thread's comments in order. GitHub's API exposes NO
	// resolvedAt timestamp on a review thread, so the last comment's time is
	// the only available lower bound on when the thread was settled. Every
	// metric that uses it says so.
	Comments []ThreadComment `json:"comments,omitempty"`
}

// ThreadComment is one comment inside a review thread.
type ThreadComment struct {
	Author    string    `json:"author"`
	CreatedAt time.Time `json:"created_at"`
}

// FirstCommentAt is the thread's opening comment time, zero when it has none.
func (t ReviewThread) FirstCommentAt() time.Time {
	if len(t.Comments) == 0 {
		return time.Time{}
	}
	first := t.Comments[0].CreatedAt
	for _, c := range t.Comments[1:] {
		if c.CreatedAt.Before(first) {
			first = c.CreatedAt
		}
	}
	return first
}

// LastCommentAt is the thread's most recent comment time, zero when it has none.
func (t ReviewThread) LastCommentAt() time.Time {
	var last time.Time
	for _, c := range t.Comments {
		if c.CreatedAt.After(last) {
			last = c.CreatedAt
		}
	}
	return last
}

// Issue is one issue (never a pull request — GitHub's REST API conflates them,
// the collector does not).
type Issue struct {
	Number    int       `json:"number"`
	Title     string    `json:"title"`
	Author    string    `json:"author"`
	State     string    `json:"state"` // OPEN | CLOSED
	CreatedAt time.Time `json:"created_at"`
	ClosedAt  time.Time `json:"closed_at,omitempty"`
	Labels    []string  `json:"labels,omitempty"`
	// LinkedPRs are pull requests GitHub's own timeline connects to this issue
	// (CONNECTED_EVENT / CROSS_REFERENCED_EVENT). Collected per issue rather
	// than derived from the pull-request window, so an open issue whose only
	// pull request predates the window is still seen as having one — the
	// alternative under-reports "no pull request" precisely on the oldest
	// issues, which are the ones the metric exists to surface.
	LinkedPRs []LinkedPR `json:"linked_prs,omitempty"`
}

// LinkedPR is a pull request referenced from an issue's timeline.
type LinkedPR struct {
	Number int       `json:"number"`
	State  PRState   `json:"state"`
	At     time.Time `json:"at"`
	// CreatedAt is the pull request's own creation time, which is what the
	// issue-to-pull-request latency measures. At above is when the reference
	// appeared, which can be later.
	CreatedAt time.Time `json:"created_at"`
}

// ReviewClockStart is when this pull request became reviewable: the
// ready-for-review moment for a draft, otherwise creation.
func (p PullRequest) ReviewClockStart() time.Time {
	if !p.ReadyForReviewAt.IsZero() {
		return p.ReadyForReviewAt
	}
	return p.CreatedAt
}

// EndedAt is when the pull request left the board: merge time, else close
// time, else zero for one still open.
func (p PullRequest) EndedAt() time.Time {
	if !p.MergedAt.IsZero() {
		return p.MergedAt
	}
	return p.ClosedAt
}

// HasLabel reports a case-insensitive-free exact label match.
func hasAny(labels []string, want map[string]bool) bool {
	for _, l := range labels {
		if want[l] {
			return true
		}
	}
	return false
}
