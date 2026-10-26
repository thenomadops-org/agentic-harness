package main

import (
	"fmt"
	"sort"
	"strings"
)

// Summary renders the plain-text report a human reads in CI output without
// opening anything.
//
// Its layout is load-bearing in one respect: the NOT MEASURED block is
// SEPARATE and comes before the measured numbers. A metric that could not be
// computed is the most interesting line in the whole document — it is either a
// genuine "this repository does not do that" or a broken query — and burying
// it in a column of zeroes is precisely how it goes unnoticed. Nothing with
// StatusInsufficient ever prints a number.
func Summary(rep Report) string {
	var b strings.Builder
	p := func(f string, a ...any) { fmt.Fprintf(&b, f+"\n", a...) }

	p("SDLC process metrics — %s", rep.Repo)
	p("window %s (%d days, %s .. %s)", rep.Window.ID, rep.Window.Days,
		rep.Window.Start.Format("2006-01-02T15:04Z"), rep.Window.End.Format("2006-01-02T15:04Z"))
	p("generated %s by %s, schema %s", rep.GeneratedAt.Format("2006-01-02T15:04:05Z"), rep.Collector, rep.SchemaVersion)
	p("")

	t := rep.Totals
	p("CENSUS — what this run actually examined")
	p("  pull requests examined %d   merged in window %d   open now %d", t.PullRequestsExamined, t.PullRequestsMerged, t.PullRequestsOpen)
	p("  issues examined        %d   open now %d", t.IssuesExamined, t.IssuesOpen)
	p("  review events          %d   review threads %d", t.ReviewEvents, t.ReviewThreads)
	if len(t.ReviewAuthors) > 0 {
		p("  review events by author: %s", byCount(t.ReviewAuthors, 6))
	}
	p("")

	var okRecs, insufficient []Record
	for _, m := range rep.Metrics {
		if m.Status == StatusOK {
			okRecs = append(okRecs, m)
		} else {
			insufficient = append(insufficient, m)
		}
	}
	sort.SliceStable(okRecs, func(i, j int) bool { return okRecs[i].MetricID < okRecs[j].MetricID })
	sort.SliceStable(insufficient, func(i, j int) bool { return insufficient[i].MetricID < insufficient[j].MetricID })

	if len(insufficient) > 0 {
		p("NOT MEASURED — %d of %d metrics had no subjects. Read these first.", len(insufficient), len(rep.Metrics))
		for _, m := range insufficient {
			p("  %-52s  insufficient_data", m.MetricID)
			p("      %s", m.Detail)
		}
		p("")
	}

	p("MEASURED — %d metrics", len(okRecs))
	lastFamily := ""
	for _, m := range okRecs {
		if m.Family != lastFamily {
			p("  [%s]", m.Family)
			lastFamily = m.Family
		}
		p("  %-52s  %s  (n=%d)", m.MetricID, formatValue(m.Value, m.Unit), m.Subjects)
		p("      %s", m.Detail)
	}
	p("")

	p("SINKS")
	for _, s := range rep.Sinks {
		p("  %-10s %s", s.Name, strings.ToUpper(string(s.Status)))
		p("      %s", s.Detail)
	}
	return b.String()
}

func formatValue(v float64, u Unit) string {
	switch u {
	case UnitCount:
		return fmt.Sprintf("%10.0f %-6s", v, string(u))
	case UnitRatio:
		return fmt.Sprintf("%9.1f%% %-6s", v*100, "")
	case UnitCycles:
		return fmt.Sprintf("%10.2f %-6s", v, string(u))
	default:
		return fmt.Sprintf("%10.2f %-6s", v, string(u))
	}
}

func byCount(m map[string]int, n int) string {
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
		parts = append(parts, fmt.Sprintf("%s=%d", x.k, x.v))
	}
	return strings.Join(parts, ", ")
}
