package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func mustTime(s string) time.Time {
	t, err := time.Parse(time.RFC3339, s)
	if err != nil {
		panic(err)
	}
	return t
}

// ---------------------------------------------------------------------------
// The fetch is the boring half, but three of its failure modes are silent and
// each one produces a plausible, wrong document. Those three are what is tested
// here; the rest is shape translation the computation tests already cover.
// ---------------------------------------------------------------------------

func newCollector(t *testing.T, handler http.HandlerFunc) (*GitHubCollector, *httptest.Server) {
	t.Helper()
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	return &GitHubCollector{
		Owner: "o", Name: "r", Token: "t",
		Endpoint: srv.URL,
		Client:   srv.Client(),
		Window:   NewWindow(mustTime("2026-06-15T00:00:00Z"), 14),
	}, srv
}

func TestAGraphQLErrorIsAnErrorAndNotAnEmptyResultSet(t *testing.T) {
	c, _ := newCollector(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		// GitHub answers 200 with an `errors` array for a rejected query. A
		// collector that only reads the status code records this as "the
		// repository has no pull requests".
		w.Write([]byte(`{"data":null,"errors":[{"type":"NOT_FOUND","message":"Could not resolve to a Repository"}]}`))
	})
	_, err := c.Collect(context.Background())
	if err == nil {
		t.Fatal("a GraphQL errors array returned with HTTP 200 must be an error, not an empty dataset")
	}
	if !strings.Contains(err.Error(), "NOT_FOUND") {
		t.Errorf("the GraphQL error must survive into the message, got: %v", err)
	}
}

func TestAnEmptyRepositoryIsRefusedByTheCollector(t *testing.T) {
	c, _ := newCollector(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"data":{"repository":{"pullRequests":{"pageInfo":{"hasNextPage":false,"endCursor":""},"nodes":[]},"issues":{"pageInfo":{"hasNextPage":false,"endCursor":""},"nodes":[]}}}}`))
	})
	_, err := c.Collect(context.Background())
	if err == nil {
		t.Fatal("a fetch that returned nothing at all must be refused at the collector, before anything downstream sees an empty dataset")
	}
}

func TestAnHTTPFailureIsNotReadAsTheEndOfPagination(t *testing.T) {
	calls := 0
	c, _ := newCollector(t, func(w http.ResponseWriter, r *http.Request) {
		calls++
		http.Error(w, "boom", http.StatusInternalServerError)
	})
	if _, err := c.Collect(context.Background()); err == nil {
		t.Fatal("a 500 must be an error; treating it as the last page silently halves the dataset")
	}
	if calls == 0 {
		t.Fatal("the collector never called the endpoint")
	}
}

// The two live-API gotchas that were found by probing and are easy to
// reintroduce, pinned as fixtures rather than as comments.
func TestConvertPRReadsTheTimelineNodesAndNotAFilteredTotalCount(t *testing.T) {
	// `timelineItems(first:N, itemTypes:[...]).totalCount` IGNORES itemTypes and
	// returns the count of ALL timeline items. The payload below has a
	// totalCount of 9 and exactly two change events; anything reading the count
	// would report nine.
	raw := `{
	  "number": 1, "title": "t", "body": "", "isDraft": false, "state": "MERGED",
	  "createdAt": "2026-06-02T00:00:00Z", "mergedAt": "2026-06-02T06:00:00Z", "closedAt": "2026-06-02T06:00:00Z",
	  "author": {"login": "app"},
	  "labels": {"nodes": []},
	  "files": {"totalCount": 3, "nodes": [{"path": "api/gateway/a.go"}]},
	  "reviews": {"nodes": [{"author": {"login": "app"}, "state": "COMMENTED", "submittedAt": "2026-06-02T02:00:00Z"}]},
	  "reviewThreads": {"nodes": []},
	  "closingIssuesReferences": {"nodes": []},
	  "timelineItems": {"totalCount": 9, "nodes": [
	    {"__typename": "PullRequestCommit", "commit": {"oid": "a1", "committedDate": "2026-06-02T00:00:00Z", "author": {"user": {"login": "dev1"}}}},
	    {"__typename": "MentionedEvent"},
	    {"__typename": "HeadRefForcePushedEvent", "createdAt": "2026-06-02T03:00:00Z", "actor": {"login": "dev1"}},
	    {"__typename": "ReadyForReviewEvent", "createdAt": "2026-06-02T01:00:00Z"}
	  ]}
	}`
	var n gqlPR
	if err := json.Unmarshal([]byte(raw), &n); err != nil {
		t.Fatalf("decode: %v", err)
	}
	pr := convertPR(n)
	if len(pr.Changes) != 2 {
		t.Fatalf("changes = %d, want 2 (one commit, one force push) — a filtered totalCount would say 9", len(pr.Changes))
	}
	if pr.Changes[0].Kind != ChangeCommit || pr.Changes[1].Kind != ChangeForcePush {
		t.Errorf("changes = %+v, want a commit then a force push in time order", pr.Changes)
	}
	if !pr.ReadyForReviewAt.Equal(mustTime("2026-06-02T01:00:00Z")) {
		t.Errorf("ready_for_review_at = %v, want the ReadyForReviewEvent time", pr.ReadyForReviewAt)
	}
	// files(first:100) with totalCount 3 and 1 node is a TRUNCATED list, and
	// the surface histogram must be able to say so.
	if !pr.FilesTruncated {
		t.Error("a file list shorter than totalCount must be marked truncated, or the surface histogram silently under-reports the biggest changes")
	}
	// A MentionedEvent must not become a phantom change event.
	for _, c := range pr.Changes {
		if c.At.IsZero() {
			t.Error("a timeline item this collector does not model became a zero-timed change event")
		}
	}
}

func TestConvertIssueDropsACrossReferenceThatIsNotAPullRequest(t *testing.T) {
	// A CrossReferencedEvent whose source is an ISSUE unmarshals with Number 0,
	// because the inline fragment only matches PullRequest. Counting it would
	// report that an issue mentioned by another issue already has a pull
	// request — which is exactly the wrong direction for
	// flow.open_issues_without_pr, the metric that exists to surface unstarted
	// work.
	raw := `{
	  "number": 101, "title": "t", "state": "OPEN",
	  "createdAt": "2026-06-01T00:00:00Z", "closedAt": null,
	  "author": {"login": "app"},
	  "labels": {"nodes": [{"name": "bug"}]},
	  "timelineItems": {"nodes": [
	    {"__typename": "CrossReferencedEvent", "createdAt": "2026-06-02T00:00:00Z", "source": {}},
	    {"__typename": "ConnectedEvent", "createdAt": "2026-06-03T00:00:00Z", "subject": {"number": 7, "state": "MERGED", "createdAt": "2026-06-02T12:00:00Z"}}
	  ]}
	}`
	var n gqlIssue
	if err := json.Unmarshal([]byte(raw), &n); err != nil {
		t.Fatalf("decode: %v", err)
	}
	is := convertIssue(n)
	if len(is.LinkedPRs) != 1 {
		t.Fatalf("linked_prs = %+v, want exactly the one that IS a pull request", is.LinkedPRs)
	}
	if is.LinkedPRs[0].Number != 7 {
		t.Errorf("linked pull request = #%d, want #7", is.LinkedPRs[0].Number)
	}
	if !is.LinkedPRs[0].CreatedAt.Equal(mustTime("2026-06-02T12:00:00Z")) {
		t.Errorf("the linked pull request's own creation time must be carried, got %v — the issue-to-pull-request latency is measured from it", is.LinkedPRs[0].CreatedAt)
	}
}
