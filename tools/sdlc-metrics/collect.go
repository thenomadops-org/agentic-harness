package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// THE FETCH — the boring half.
//
// GitHub GraphQL v4, because the alternative is five REST calls per pull
// request, and a busy repository can merge several hundred in a 28-day window
// (the project this tool came from merged ~470). One query returns a pull
// request with its reviews, its review threads, its commits, its force pushes,
// its files and its linked issues.
//
// Everything here is I/O and shape-translation. Nothing here decides a number.
// If you are looking for why a metric says what it says, it is compute.go.
//
// TWO GOTCHAS, both found by probing the live API and both easy to get silently
// wrong:
//
//  1. `timelineItems(first:N, itemTypes:[...]).totalCount` IGNORES itemTypes —
//     it returns the count of ALL timeline items. Reading it as "how many force
//     pushes" gives 4..20 on pull requests that had none. Nothing in this file
//     uses a filtered totalCount; the nodes are counted instead.
//
//  2. `closingIssuesReferences` can be EMPTY for most of a repository's pull
//     requests. On one project it was, because the contributing rules forbade
//     a closing keyword bound in prose and required a bare `#nnn` claim line
//     instead; a collector using it as the only issue linkage reported that
//     almost no issue ever gets a pull request. Body/title `#nnn` mentions are
//     collected alongside it, and the issue side is collected independently
//     from each issue's own timeline, so neither convention loses the link.
// ---------------------------------------------------------------------------

const graphQLEndpoint = "https://api.github.com/graphql"

// Collector fetches a Dataset from GitHub.
type GitHubCollector struct {
	Owner string
	Name  string
	Token string
	// Endpoint is overridable in tests; empty means graphQLEndpoint.
	Endpoint string
	Client   *http.Client
	// Window bounds the historical fetch. Open pull requests and open issues
	// are always fetched in full regardless of it.
	Window Window
	// Log receives progress lines. Nil means silent.
	Log func(string, ...any)
}

func (c *GitHubCollector) logf(f string, a ...any) {
	if c.Log != nil {
		c.Log(f, a...)
	}
}

func (c *GitHubCollector) endpoint() string {
	if c.Endpoint != "" {
		return c.Endpoint
	}
	return graphQLEndpoint
}

func (c *GitHubCollector) httpClient() *http.Client {
	if c.Client != nil {
		return c.Client
	}
	return &http.Client{Timeout: 60 * time.Second}
}

type graphQLError struct {
	Message string `json:"message"`
	Type    string `json:"type"`
}

// query executes one GraphQL request and unmarshals `data` into out.
//
// A transport error, a non-2xx status, or a non-empty `errors` array is an
// ERROR. It is never treated as an empty page: a partial fetch silently read as
// "there were no more pull requests" is exactly how a metrics run reports a
// flattering number over half the data.
func (c *GitHubCollector) query(ctx context.Context, q string, vars map[string]any, out any) error {
	body, err := json.Marshal(map[string]any{"query": q, "variables": vars})
	if err != nil {
		return fmt.Errorf("encode graphql request: %w", err)
	}
	var lastErr error
	for attempt := 0; attempt < 4; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(time.Duration(attempt*attempt) * 2 * time.Second):
			}
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint(), bytes.NewReader(body))
		if err != nil {
			return fmt.Errorf("build graphql request: %w", err)
		}
		req.Header.Set("Authorization", "Bearer "+c.Token)
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("User-Agent", "sdlc-metrics")

		resp, err := c.httpClient().Do(req)
		if err != nil {
			lastErr = fmt.Errorf("graphql request: %w", err)
			continue
		}
		raw, readErr := io.ReadAll(io.LimitReader(resp.Body, 32<<20))
		resp.Body.Close()
		if readErr != nil {
			lastErr = fmt.Errorf("read graphql response: %w", readErr)
			continue
		}
		// 502 and 403 are GitHub's answers to a query that timed out or hit a
		// secondary rate limit; both are retryable. Anything else is not, and
		// is reported rather than retried into a timeout.
		if resp.StatusCode == http.StatusBadGateway || resp.StatusCode == http.StatusForbidden || resp.StatusCode == http.StatusTooManyRequests {
			lastErr = fmt.Errorf("graphql returned %d: %s", resp.StatusCode, truncate(string(raw), 400))
			continue
		}
		if resp.StatusCode < 200 || resp.StatusCode > 299 {
			return fmt.Errorf("graphql returned %d: %s", resp.StatusCode, truncate(string(raw), 800))
		}
		var env struct {
			Data   json.RawMessage `json:"data"`
			Errors []graphQLError  `json:"errors"`
		}
		if err := json.Unmarshal(raw, &env); err != nil {
			return fmt.Errorf("decode graphql envelope: %w", err)
		}
		if len(env.Errors) > 0 {
			msgs := make([]string, 0, len(env.Errors))
			for _, e := range env.Errors {
				msgs = append(msgs, e.Type+": "+e.Message)
			}
			return fmt.Errorf("graphql errors: %s", strings.Join(msgs, "; "))
		}
		if len(env.Data) == 0 {
			return fmt.Errorf("graphql returned no data and no errors — refusing to read that as an empty result set")
		}
		return json.Unmarshal(env.Data, out)
	}
	return lastErr
}

const prQuery = `
query($owner:String!,$name:String!,$cursor:String,$states:[PullRequestState!]){
  repository(owner:$owner,name:$name){
    pullRequests(first:15, after:$cursor, states:$states, orderBy:{field:CREATED_AT,direction:DESC}){
      pageInfo{hasNextPage endCursor}
      nodes{
        number title body isDraft state createdAt mergedAt closedAt
        author{login}
        labels(first:20){nodes{name}}
        files(first:100){totalCount nodes{path}}
        reviews(first:50){nodes{author{login} state submittedAt}}
        reviewThreads(first:50){nodes{id isResolved resolvedBy{login} comments(first:20){nodes{author{login} createdAt}}}}
        closingIssuesReferences(first:10){nodes{number}}
        timelineItems(first:100, itemTypes:[PULL_REQUEST_COMMIT, HEAD_REF_FORCE_PUSHED_EVENT, READY_FOR_REVIEW_EVENT]){
          nodes{
            __typename
            ... on PullRequestCommit{commit{oid committedDate author{user{login}}}}
            ... on HeadRefForcePushedEvent{createdAt actor{login}}
            ... on ReadyForReviewEvent{createdAt}
          }
        }
      }
    }
  }
}`

type gqlActor struct {
	Login string `json:"login"`
}

type gqlPR struct {
	Number    int        `json:"number"`
	Title     string     `json:"title"`
	Body      string     `json:"body"`
	IsDraft   bool       `json:"isDraft"`
	State     string     `json:"state"`
	CreatedAt time.Time  `json:"createdAt"`
	MergedAt  *time.Time `json:"mergedAt"`
	ClosedAt  *time.Time `json:"closedAt"`
	Author    *gqlActor  `json:"author"`
	Labels    struct {
		Nodes []struct {
			Name string `json:"name"`
		} `json:"nodes"`
	} `json:"labels"`
	Files struct {
		TotalCount int `json:"totalCount"`
		Nodes      []struct {
			Path string `json:"path"`
		} `json:"nodes"`
	} `json:"files"`
	Reviews struct {
		Nodes []struct {
			Author      *gqlActor `json:"author"`
			State       string    `json:"state"`
			SubmittedAt time.Time `json:"submittedAt"`
		} `json:"nodes"`
	} `json:"reviews"`
	ReviewThreads struct {
		Nodes []struct {
			ID         string    `json:"id"`
			IsResolved bool      `json:"isResolved"`
			ResolvedBy *gqlActor `json:"resolvedBy"`
			Comments   struct {
				Nodes []struct {
					Author    *gqlActor `json:"author"`
					CreatedAt time.Time `json:"createdAt"`
				} `json:"nodes"`
			} `json:"comments"`
		} `json:"nodes"`
	} `json:"reviewThreads"`
	ClosingIssuesReferences struct {
		Nodes []struct {
			Number int `json:"number"`
		} `json:"nodes"`
	} `json:"closingIssuesReferences"`
	TimelineItems struct {
		Nodes []struct {
			Typename string `json:"__typename"`
			Commit   *struct {
				OID           string    `json:"oid"`
				CommittedDate time.Time `json:"committedDate"`
				Author        *struct {
					User *gqlActor `json:"user"`
				} `json:"author"`
			} `json:"commit"`
			CreatedAt *time.Time `json:"createdAt"`
			Actor     *gqlActor  `json:"actor"`
		} `json:"nodes"`
	} `json:"timelineItems"`
}

const issueQuery = `
query($owner:String!,$name:String!,$cursor:String,$states:[IssueState!]){
  repository(owner:$owner,name:$name){
    issues(first:25, after:$cursor, states:$states, orderBy:{field:CREATED_AT,direction:DESC}){
      pageInfo{hasNextPage endCursor}
      nodes{
        number title state createdAt closedAt
        author{login}
        labels(first:20){nodes{name}}
        timelineItems(first:50, itemTypes:[CROSS_REFERENCED_EVENT, CONNECTED_EVENT]){
          nodes{
            __typename
            ... on CrossReferencedEvent{createdAt source{... on PullRequest{number state createdAt}}}
            ... on ConnectedEvent{createdAt subject{... on PullRequest{number state createdAt}}}
          }
        }
      }
    }
  }
}`

type gqlLinkedPR struct {
	Number    int        `json:"number"`
	State     string     `json:"state"`
	CreatedAt *time.Time `json:"createdAt"`
}

type gqlIssue struct {
	Number    int        `json:"number"`
	Title     string     `json:"title"`
	State     string     `json:"state"`
	CreatedAt time.Time  `json:"createdAt"`
	ClosedAt  *time.Time `json:"closedAt"`
	Author    *gqlActor  `json:"author"`
	Labels    struct {
		Nodes []struct {
			Name string `json:"name"`
		} `json:"nodes"`
	} `json:"labels"`
	TimelineItems struct {
		Nodes []struct {
			Typename  string       `json:"__typename"`
			CreatedAt *time.Time   `json:"createdAt"`
			Source    *gqlLinkedPR `json:"source"`
			Subject   *gqlLinkedPR `json:"subject"`
		} `json:"nodes"`
	} `json:"timelineItems"`
}

// Collect fetches the whole Dataset.
func (c *GitHubCollector) Collect(ctx context.Context) (Dataset, error) {
	ds := Dataset{
		Repo:        c.Owner + "/" + c.Name,
		CollectedAt: time.Now().UTC(),
	}

	prs := map[int]PullRequest{}
	// Pass 1: everything still OPEN, regardless of age. An open pull request
	// older than the window is still in flight and must be counted; a
	// window-only fetch would silently under-report exactly the stalest work.
	if err := c.collectPRs(ctx, []string{"OPEN"}, false, prs); err != nil {
		return ds, fmt.Errorf("collect open pull requests: %w", err)
	}
	// Pass 2: everything created back to the window start, any state.
	if err := c.collectPRs(ctx, nil, true, prs); err != nil {
		return ds, fmt.Errorf("collect window pull requests: %w", err)
	}
	for _, pr := range prs {
		ds.PullRequests = append(ds.PullRequests, pr)
	}
	sort.Slice(ds.PullRequests, func(i, j int) bool { return ds.PullRequests[i].Number < ds.PullRequests[j].Number })

	issues := map[int]Issue{}
	if err := c.collectIssues(ctx, []string{"OPEN"}, false, issues); err != nil {
		return ds, fmt.Errorf("collect open issues: %w", err)
	}
	if err := c.collectIssues(ctx, nil, true, issues); err != nil {
		return ds, fmt.Errorf("collect window issues: %w", err)
	}
	for _, is := range issues {
		ds.Issues = append(ds.Issues, is)
	}
	sort.Slice(ds.Issues, func(i, j int) bool { return ds.Issues[i].Number < ds.Issues[j].Number })

	// `#nnn` mentions are resolved against the issue set only, so a pull
	// request referencing another pull request never counts as issue linkage.
	issueNumbers := map[int]bool{}
	for _, is := range ds.Issues {
		issueNumbers[is.Number] = true
	}
	for i := range ds.PullRequests {
		ds.PullRequests[i].MentionedIssues = mentionedIssues(ds.PullRequests[i].Title, ds.PullRequests[i].Body, issueNumbers)
		// The body is kept out of the dumped dataset: it is large, it is not
		// read by anything after this point, and a metrics artefact has no
		// business carrying the full text of every pull request.
		ds.PullRequests[i].Body = ""
	}

	if len(ds.PullRequests) == 0 {
		return ds, fmt.Errorf("the pull-request fetch returned nothing at all for %s — that is a broken query or a wrong repository, not an empty repository", ds.Repo)
	}
	if len(ds.Issues) == 0 {
		return ds, fmt.Errorf("the issue fetch returned nothing at all for %s — see above", ds.Repo)
	}
	return ds, nil
}

func (c *GitHubCollector) collectPRs(ctx context.Context, states []string, stopAtWindow bool, into map[int]PullRequest) error {
	var cursor *string
	pages := 0
	for {
		var out struct {
			Repository struct {
				PullRequests struct {
					PageInfo struct {
						HasNextPage bool   `json:"hasNextPage"`
						EndCursor   string `json:"endCursor"`
					} `json:"pageInfo"`
					Nodes []gqlPR `json:"nodes"`
				} `json:"pullRequests"`
			} `json:"repository"`
		}
		vars := map[string]any{"owner": c.Owner, "name": c.Name, "cursor": cursor}
		if states != nil {
			vars["states"] = states
		} else {
			vars["states"] = nil
		}
		if err := c.query(ctx, prQuery, vars, &out); err != nil {
			return err
		}
		page := out.Repository.PullRequests
		pages++
		c.logf("  pull requests: page %d, %d nodes, %d collected", pages, len(page.Nodes), len(into))
		reachedWindow := false
		for _, n := range page.Nodes {
			if stopAtWindow && n.CreatedAt.Before(c.Window.Start) {
				reachedWindow = true
				continue
			}
			into[n.Number] = convertPR(n)
		}
		if reachedWindow || !page.PageInfo.HasNextPage || page.PageInfo.EndCursor == "" {
			return nil
		}
		cur := page.PageInfo.EndCursor
		cursor = &cur
	}
}

func (c *GitHubCollector) collectIssues(ctx context.Context, states []string, stopAtWindow bool, into map[int]Issue) error {
	var cursor *string
	pages := 0
	for {
		var out struct {
			Repository struct {
				Issues struct {
					PageInfo struct {
						HasNextPage bool   `json:"hasNextPage"`
						EndCursor   string `json:"endCursor"`
					} `json:"pageInfo"`
					Nodes []gqlIssue `json:"nodes"`
				} `json:"issues"`
			} `json:"repository"`
		}
		vars := map[string]any{"owner": c.Owner, "name": c.Name, "cursor": cursor}
		if states != nil {
			vars["states"] = states
		} else {
			vars["states"] = nil
		}
		if err := c.query(ctx, issueQuery, vars, &out); err != nil {
			return err
		}
		page := out.Repository.Issues
		pages++
		c.logf("  issues: page %d, %d nodes, %d collected", pages, len(page.Nodes), len(into))
		reachedWindow := false
		for _, n := range page.Nodes {
			if stopAtWindow && n.CreatedAt.Before(c.Window.Start) {
				reachedWindow = true
				continue
			}
			into[n.Number] = convertIssue(n)
		}
		if reachedWindow || !page.PageInfo.HasNextPage || page.PageInfo.EndCursor == "" {
			return nil
		}
		cur := page.PageInfo.EndCursor
		cursor = &cur
	}
}

func convertPR(n gqlPR) PullRequest {
	pr := PullRequest{
		Number:    n.Number,
		Title:     n.Title,
		Body:      n.Body,
		Author:    login(n.Author),
		State:     PRState(n.State),
		Draft:     n.IsDraft,
		CreatedAt: n.CreatedAt.UTC(),
		MergedAt:  deref(n.MergedAt),
		ClosedAt:  deref(n.ClosedAt),
	}
	for _, l := range n.Labels.Nodes {
		pr.Labels = append(pr.Labels, l.Name)
	}
	for _, f := range n.Files.Nodes {
		pr.Files = append(pr.Files, f.Path)
	}
	pr.FilesTruncated = n.Files.TotalCount > len(n.Files.Nodes)
	for _, r := range n.Reviews.Nodes {
		pr.Reviews = append(pr.Reviews, Review{Author: login(r.Author), State: r.State, SubmittedAt: r.SubmittedAt.UTC()})
	}
	for _, t := range n.ReviewThreads.Nodes {
		th := ReviewThread{ID: t.ID, Resolved: t.IsResolved, ResolvedBy: login(t.ResolvedBy)}
		for _, cm := range t.Comments.Nodes {
			th.Comments = append(th.Comments, ThreadComment{Author: login(cm.Author), CreatedAt: cm.CreatedAt.UTC()})
		}
		pr.Threads = append(pr.Threads, th)
	}
	for _, ci := range n.ClosingIssuesReferences.Nodes {
		pr.ClosingIssues = append(pr.ClosingIssues, ci.Number)
	}
	for _, it := range n.TimelineItems.Nodes {
		switch it.Typename {
		case "PullRequestCommit":
			if it.Commit == nil {
				continue
			}
			actor := ""
			if it.Commit.Author != nil && it.Commit.Author.User != nil {
				actor = it.Commit.Author.User.Login
			}
			pr.Changes = append(pr.Changes, ChangeEvent{Kind: ChangeCommit, At: it.Commit.CommittedDate.UTC(), Actor: actor, SHA: it.Commit.OID})
		case "HeadRefForcePushedEvent":
			if it.CreatedAt == nil {
				continue
			}
			pr.Changes = append(pr.Changes, ChangeEvent{Kind: ChangeForcePush, At: it.CreatedAt.UTC(), Actor: login(it.Actor)})
		case "ReadyForReviewEvent":
			if it.CreatedAt == nil {
				continue
			}
			// The FIRST ready-for-review is the one that starts the review
			// clock. A pull request converted back to draft and ready again
			// keeps the earliest, which under-reports rather than flatters.
			t := it.CreatedAt.UTC()
			if pr.ReadyForReviewAt.IsZero() || t.Before(pr.ReadyForReviewAt) {
				pr.ReadyForReviewAt = t
			}
		}
	}
	sort.Slice(pr.Changes, func(i, j int) bool { return pr.Changes[i].At.Before(pr.Changes[j].At) })
	return pr
}

func convertIssue(n gqlIssue) Issue {
	is := Issue{
		Number:    n.Number,
		Title:     n.Title,
		Author:    login(n.Author),
		State:     n.State,
		CreatedAt: n.CreatedAt.UTC(),
		ClosedAt:  deref(n.ClosedAt),
	}
	for _, l := range n.Labels.Nodes {
		is.Labels = append(is.Labels, l.Name)
	}
	seen := map[int]bool{}
	for _, it := range n.TimelineItems.Nodes {
		ref := it.Source
		if ref == nil {
			ref = it.Subject
		}
		// A CrossReferencedEvent whose source is an ISSUE (not a pull request)
		// unmarshals with Number 0, because the inline fragment only matches
		// PullRequest. Dropping those is the point: an issue mentioning another
		// issue is not a pull request.
		if ref == nil || ref.Number == 0 || seen[ref.Number] {
			continue
		}
		seen[ref.Number] = true
		l := LinkedPR{Number: ref.Number, State: PRState(ref.State)}
		if it.CreatedAt != nil {
			l.At = it.CreatedAt.UTC()
		}
		if ref.CreatedAt != nil {
			l.CreatedAt = ref.CreatedAt.UTC()
		}
		is.LinkedPRs = append(is.LinkedPRs, l)
	}
	sort.Slice(is.LinkedPRs, func(i, j int) bool { return is.LinkedPRs[i].Number < is.LinkedPRs[j].Number })
	return is
}

// issueRefRe matches a `#nnn` reference that is not part of a longer token.
// `(?m)` is not needed; the boundary handling is explicit because Go's RE2 has
// no lookbehind: the capture is preceded by start-of-string or a non-word
// character, which is checked by the surrounding group.
var issueRefRe = regexp.MustCompile(`(^|[^A-Za-z0-9_/#])#(\d{1,7})\b`)

// mentionedIssues extracts `#nnn` references from a pull request's title and
// body, keeping only numbers that are known issues.
//
// The `/#` exclusion in the pattern drops a full URL form
// (`.../issues/#123` is not a thing, but `.../pull/840#issuecomment-1` is) and
// the known-issue filter drops every reference to another pull request, which
// in a repository that cites sibling pull requests constantly is most of them.
func mentionedIssues(title, body string, issueNumbers map[int]bool) []int {
	seen := map[int]bool{}
	var out []int
	for _, text := range []string{title, body} {
		for _, m := range issueRefRe.FindAllStringSubmatch(text, -1) {
			n, err := strconv.Atoi(m[2])
			if err != nil || !issueNumbers[n] || seen[n] {
				continue
			}
			seen[n] = true
			out = append(out, n)
		}
	}
	sort.Ints(out)
	return out
}

func login(a *gqlActor) string {
	if a == nil {
		return ""
	}
	return a.Login
}

func deref(t *time.Time) time.Time {
	if t == nil {
		return time.Time{}
	}
	return t.UTC()
}

func truncate(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
