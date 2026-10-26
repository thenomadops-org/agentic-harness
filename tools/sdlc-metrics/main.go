package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// sdlc-metrics — process metrics for one GitHub repository, from GitHub
// metadata alone.
//
// It adds NO instrumentation to the product. Every number comes from issue and
// pull-request metadata that already exists.
//
//   sdlc-metrics -repo owner/name -window-days 28 -out metrics.json
//   sdlc-metrics -input dataset.json -now 2026-09-02T12:00:00Z   # offline
//   sdlc-metrics -repo owner/name -dump-dataset dataset.json     # save input
//
// Exit codes, and they are the contract the workflow depends on:
//
//   0  measured; the document was written
//   1  a run-time failure: the fetch failed, the document would not validate,
//      or a CONFIGURED sink failed to publish
//   2  usage error
//   3  REFUSED — the vacuity guard fired. Nothing was examined, so nothing is
//      reported. A row of zeroes is not an acceptable substitute and this is
//      the exit code that says so.
//
// An unconfigured sink is NOT a failure and does not change the exit code. It
// is announced on stderr, recorded in the document as not_configured, and
// printed in the summary. See sink.go.
// ---------------------------------------------------------------------------

const (
	exitOK      = 0
	exitFailure = 1
	exitUsage   = 2
	exitRefused = 3
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

// configKnobs names, for every repository-shaped field of Config, the flag that
// sets it. It is the machine-checkable half of SCHEMA.md §10's claim that every
// repo-shaped knob is a flag: TestEveryConfigKnobIsAFlag walks Config by
// reflection against this table and against the registered flag set, so a new
// Config field cannot arrive without a flag, and a renamed flag cannot leave
// the table pointing at nothing.
//
// A claim in a document that nothing checks is a claim that quietly stops being
// true. This one is checked.
var configKnobs = map[string]string{
	"Repo":                 "repo",
	"Window":               "window-days",
	"Now":                  "now",
	"DefectLabels":         "defect-labels",
	"ClassLabelPrefixes":   "class-label-prefixes",
	"Depth2Roots":          "surface-depth2-roots",
	"StaleIssueDays":       "stale-issue-days",
	"ReviewExcludesAuthor": "review-excludes-author",
}

// opts is the parsed command line.
type opts struct {
	repo        *string
	windowDays  *int
	nowStr      *string
	input       *string
	dumpDataset *string
	out         *string
	summaryPath *string
	defects     *string
	classPrefix *string
	depth2      *string
	staleDays   *int
	excludeAuth *bool
}

// registerFlags is separate from run so a test can inspect the flag set
// without executing anything.
func registerFlags(fs *flag.FlagSet) *opts {
	d := DefaultConfig()
	return &opts{
		repo:        fs.String("repo", "", "owner/name to measure (required unless -input is given)"),
		windowDays:  fs.Int("window-days", 28, "measurement window length in days, ending at -now"),
		nowStr:      fs.String("now", "", "measurement instant, RFC3339 (default: now, UTC)"),
		input:       fs.String("input", "", "read a saved dataset JSON instead of fetching from GitHub"),
		dumpDataset: fs.String("dump-dataset", "", "write the fetched dataset JSON here, so this run's numbers stay reproducible"),
		out:         fs.String("out", "metrics.json", "write the metrics document here ('-' for stdout)"),
		summaryPath: fs.String("summary", "", "also write the plain-text summary here (it always goes to stdout)"),
		defects:     fs.String("defect-labels", strings.Join(d.DefectLabels, ","), "issue labels that mean 'a defect reached main' — a taxonomy this tool cannot invent; a repository with none gets insufficient_data, never a flattering zero"),
		classPrefix: fs.String("class-label-prefixes", strings.Join(d.ClassLabelPrefixes, ","), "label prefixes that group defects into classes"),
		depth2:      fs.String("surface-depth2-roots", strings.Join(d.Depth2Roots, ","), "top-level directories under which the SECOND path segment is the surface (default empty: a single-service repo wants none; a monorepo sets e.g. api,mobile)"),
		staleDays:   fs.Int("stale-issue-days", d.StaleIssueDays, "age at which an open issue with no pull request is called aged"),
		excludeAuth: fs.Bool("review-excludes-author", d.ReviewExcludesAuthor, "do NOT count a review by the pull request's own author as a review event. Default false. Set it TRUE in a repository with real human reviewers; leave it false where the author and the reviewer are the same login (an agent or bot that opens and approves, a solo maintainer), because there it reports a flat zero instead of a finding. totals.review_authors shows which case you are in either way"),
	}
}

func run(args []string, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("sdlc-metrics", flag.ContinueOnError)
	fs.SetOutput(stderr)
	o := registerFlags(fs)
	if err := fs.Parse(args); err != nil {
		return exitUsage
	}
	repo, windowDays, nowStr := o.repo, o.windowDays, o.nowStr
	input, dumpDataset, out, summaryPath := o.input, o.dumpDataset, o.out, o.summaryPath
	defects, classPrefix, depth2, staleDays := o.defects, o.classPrefix, o.depth2, o.staleDays
	if *repo == "" && *input == "" {
		fmt.Fprintln(stderr, "sdlc-metrics: -repo owner/name is required (or -input to read a saved dataset)")
		return exitUsage
	}

	now := time.Now().UTC()
	if *nowStr != "" {
		t, err := time.Parse(time.RFC3339, *nowStr)
		if err != nil {
			fmt.Fprintf(stderr, "sdlc-metrics: -now %q is not RFC3339: %v\n", *nowStr, err)
			return exitUsage
		}
		now = t.UTC()
	}
	if *windowDays <= 0 {
		fmt.Fprintf(stderr, "sdlc-metrics: -window-days must be positive, got %d\n", *windowDays)
		return exitUsage
	}
	window := NewWindow(now, *windowDays)

	cfg := DefaultConfig()
	cfg.Repo = *repo
	cfg.Window = window
	cfg.Now = now
	cfg.DefectLabels = splitCSV(*defects)
	cfg.ClassLabelPrefixes = splitCSV(*classPrefix)
	cfg.Depth2Roots = splitCSV(*depth2)
	cfg.StaleIssueDays = *staleDays
	cfg.ReviewExcludesAuthor = *o.excludeAuth

	// --- the sinks, announced before anything else happens ------------------
	// The unconfigured-rail rule: the statement is made at start-up, not only
	// in the document, so a person watching the log knows immediately that
	// nothing will be published.
	sinks := []Sink{NewNotionSink(LoadNotionConfig(os.Getenv))}
	for _, s := range sinks {
		fmt.Fprintln(stderr, "sdlc-metrics: "+s.Describe())
	}

	// --- the data -----------------------------------------------------------
	var ds Dataset
	if *input != "" {
		raw, err := os.ReadFile(*input)
		if err != nil {
			fmt.Fprintf(stderr, "sdlc-metrics: read -input: %v\n", err)
			return exitFailure
		}
		if err := json.Unmarshal(raw, &ds); err != nil {
			fmt.Fprintf(stderr, "sdlc-metrics: decode -input %s: %v\n", *input, err)
			return exitFailure
		}
		if cfg.Repo == "" {
			cfg.Repo = ds.Repo
		}
	} else {
		owner, name, ok := strings.Cut(*repo, "/")
		if !ok || owner == "" || name == "" {
			fmt.Fprintf(stderr, "sdlc-metrics: -repo %q is not owner/name\n", *repo)
			return exitUsage
		}
		token := firstNonEmpty(os.Getenv("GH_TOKEN"), os.Getenv("GITHUB_TOKEN"))
		if token == "" {
			// NOT a sink: without a token there is no measurement at all, so
			// this is a hard failure rather than an announced degradation.
			fmt.Fprintln(stderr, "sdlc-metrics: neither GH_TOKEN nor GITHUB_TOKEN is set, so there is no way to read the repository's metadata. Refusing rather than reporting an empty window.")
			return exitFailure
		}
		c := &GitHubCollector{
			Owner:  owner,
			Name:   name,
			Token:  token,
			Window: window,
			Log:    func(f string, a ...any) { fmt.Fprintf(stderr, f+"\n", a...) },
		}
		fmt.Fprintf(stderr, "sdlc-metrics: fetching %s over window %s\n", *repo, window.ID)
		var err error
		ds, err = c.Collect(context.Background())
		if err != nil {
			fmt.Fprintf(stderr, "sdlc-metrics: %v\n", err)
			return exitFailure
		}
	}
	if *dumpDataset != "" {
		raw, err := json.MarshalIndent(ds, "", " ")
		if err == nil {
			err = os.WriteFile(*dumpDataset, append(raw, '\n'), 0o644)
		}
		if err != nil {
			fmt.Fprintf(stderr, "sdlc-metrics: write -dump-dataset: %v\n", err)
			return exitFailure
		}
		fmt.Fprintf(stderr, "sdlc-metrics: dataset written to %s (%d pull requests, %d issues)\n", *dumpDataset, len(ds.PullRequests), len(ds.Issues))
	}

	// --- the computation, and the vacuity guard ------------------------------
	rep, err := Compute(ds, cfg)
	if err != nil {
		fmt.Fprintf(stderr, "sdlc-metrics: %v\n", err)
		if errors.Is(err, ErrNoSubjects) {
			return exitRefused
		}
		return exitFailure
	}

	// --- the sinks, attempted, and recorded either way -----------------------
	rep.Sinks = PublishAll(rep, sinks)
	failedSink := false
	for _, s := range rep.Sinks {
		if s.Status == StatusFailed {
			failedSink = true
		}
	}

	if err := rep.Validate(); err != nil {
		fmt.Fprintf(stderr, "sdlc-metrics: the report failed its own contract and was not written: %v\n", err)
		return exitFailure
	}

	doc, err := rep.Encode()
	if err != nil {
		fmt.Fprintf(stderr, "sdlc-metrics: encode report: %v\n", err)
		return exitFailure
	}
	if *out == "-" {
		stdout.Write(doc)
	} else if err := os.WriteFile(*out, doc, 0o644); err != nil {
		fmt.Fprintf(stderr, "sdlc-metrics: write %s: %v\n", *out, err)
		return exitFailure
	}

	summary := Summary(rep)
	fmt.Fprint(stdout, summary)
	if *summaryPath != "" {
		if err := os.WriteFile(*summaryPath, []byte(summary), 0o644); err != nil {
			fmt.Fprintf(stderr, "sdlc-metrics: write %s: %v\n", *summaryPath, err)
			return exitFailure
		}
	}

	if failedSink {
		return exitFailure
	}
	return exitOK
}

func splitCSV(s string) []string {
	var out []string
	for _, p := range strings.Split(s, ",") {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

func firstNonEmpty(xs ...string) string {
	for _, x := range xs {
		if x != "" {
			return x
		}
	}
	return ""
}
