package main

import (
	"errors"
	"fmt"
	"sort"
	"strings"
)

// ---------------------------------------------------------------------------
// SINKS — where a computed Report is published, and what happens when the
// credential for a destination does not exist.
//
// This is the unconfigured-rail pattern, applied without modification. It was
// learned on a cache-purge integration whose credential did not exist yet, and
// it generalises to every optional destination:
//
//	1. AN UNCONFIGURED SINK DOES NOT CRASH THE RUN. The measurement is the
//	   deliverable; it must still be computed, written and printed on a machine
//	   where the Notion token has never been created. The push is a separate
//	   concern from the measurement, with a credential that may never be set.
//	2. AN UNCONFIGURED SINK IS NEVER SILENT. It says so at start-up, it is
//	   recorded in the document as StatusNotConfigured — never StatusOK — and
//	   the plain-text summary prints it. A metrics job that quietly does nothing
//	   because a token is missing is indistinguishable from one that published,
//	   which is the same silent false success that costs an outage to learn.
//	3. REFUSING IS NOT RETURNING NIL. DisabledSink.Publish returns
//	   ErrSinkNotConfigured rather than nil, exactly as DisabledPurger does, so
//	   no caller can record a success it never had.
//
// The live Notion push itself is deliberately NOT implemented here. Writing an
// unexercisable HTTP client against an API nobody has a credential for would be
// code that looks like a capability and has never once run. What ships is the
// contract, the announcement, and the seam: NewNotionSink returns a live sink
// the moment the settings appear, and the one place to add it is marked.
//
// This whole file is OPTIONAL to a new repository. Delete it and the tool still
// measures; what it must not become is a sink that reports success it never
// had.
// ---------------------------------------------------------------------------

// ErrSinkNotConfigured is returned by a disabled sink. It is a distinct error
// rather than a nil return so "there is no sink" cannot be mistaken for "the
// publish succeeded".
var ErrSinkNotConfigured = errors.New("sink is not configured")

// Sink is a destination for a computed Report.
type Sink interface {
	// Name is the sink's stable id, as it appears in Report.Sinks.
	Name() string
	// Configured reports whether a real destination is wired.
	Configured() bool
	// Describe is the one-line start-up statement: what is, or is not,
	// configured. It NEVER contains a secret's value — only whether it is set.
	Describe() string
	// Publish sends the report. It returns ErrSinkNotConfigured when there is
	// no destination, and a descriptive error when the attempt failed.
	Publish(Report) error
}

// NotionConfig is the Notion destination's settings.
type NotionConfig struct {
	// Token is the Notion integration token (NOTION_API_TOKEN). Owner action:
	// it does not exist yet. Never logged.
	Token string
	// DatabaseID is the Notion database that holds one row per
	// (metric_id, window.id) (NOTION_DATABASE_ID).
	DatabaseID string
}

// LoadNotionConfig reads the Notion settings from getenv. It NEVER fails: an
// unconfigured sink is a documented, announced state, not an error.
func LoadNotionConfig(getenv func(string) string) NotionConfig {
	return NotionConfig{
		Token:      strings.TrimSpace(getenv("NOTION_API_TOKEN")),
		DatabaseID: strings.TrimSpace(getenv("NOTION_DATABASE_ID")),
	}
}

// Complete reports whether every setting a real publish needs is present.
func (c NotionConfig) Complete() bool { return c.Token != "" && c.DatabaseID != "" }

// Missing names the absent settings by ENV VAR NAME, for the announcement. The
// token's value is never included — only whether it is set.
func (c NotionConfig) Missing() []string {
	var out []string
	if c.Token == "" {
		out = append(out, "NOTION_API_TOKEN")
	}
	if c.DatabaseID == "" {
		out = append(out, "NOTION_DATABASE_ID")
	}
	return out
}

// DisabledSink is the sink used when a destination is not configured. It
// refuses loudly instead of returning nil.
type DisabledSink struct {
	SinkName string
	Reason   string
}

func (s DisabledSink) Name() string     { return s.SinkName }
func (s DisabledSink) Configured() bool { return false }
func (s DisabledSink) Publish(Report) error {
	return fmt.Errorf("%w: %s", ErrSinkNotConfigured, s.Reason)
}
func (s DisabledSink) Describe() string {
	return s.SinkName + " sink: NOT CONFIGURED (" + s.Reason + "). " +
		"metrics.json and the plain-text summary are still produced and are the deliverable; " +
		"nothing is published anywhere until the settings above exist."
}

// NewNotionSink returns the sink for the Notion destination: a live one when
// the settings are complete, and an announced DisabledSink otherwise.
//
// THE SEAM. When the owner creates the integration token, the live client goes
// exactly here, behind Complete(), and nothing else in this program changes —
// Publish is called the same way, its outcome is recorded the same way, and a
// failure is StatusFailed rather than a swallowed error. Until then the branch
// returns a sink that refuses, which is why "we forgot to write the push" can
// never read as "the push worked".
func NewNotionSink(cfg NotionConfig) Sink {
	if !cfg.Complete() {
		return DisabledSink{
			SinkName: "notion",
			Reason:   "unset: " + strings.Join(cfg.Missing(), ", "),
		}
	}
	return DisabledSink{
		SinkName: "notion",
		Reason: "NOTION_API_TOKEN and NOTION_DATABASE_ID are both set, but the live Notion client is not implemented — this tool ships collection only. " +
			"This is deliberately reported as not_configured rather than ok: publishing nothing must never be recorded as a publish",
	}
}

// PublishAll runs every sink and returns one SinkStatus per sink. It NEVER
// returns an error: a sink outcome is data in the document, not a reason to
// lose the measurement. The caller decides what a failed sink means for the
// process exit code.
func PublishAll(rep Report, sinks []Sink) []SinkStatus {
	out := make([]SinkStatus, 0, len(sinks))
	for _, s := range sinks {
		if !s.Configured() {
			out = append(out, SinkStatus{Name: s.Name(), Status: StatusNotConfigured, Detail: s.Describe()})
			continue
		}
		if err := s.Publish(rep); err != nil {
			status := StatusFailed
			if errors.Is(err, ErrSinkNotConfigured) {
				// A sink that claims Configured() and then refuses as
				// unconfigured is a bug in that sink, but the honest record is
				// still not_configured — never ok.
				status = StatusNotConfigured
			}
			out = append(out, SinkStatus{Name: s.Name(), Status: status, Detail: err.Error()})
			continue
		}
		out = append(out, SinkStatus{Name: s.Name(), Status: StatusOK, Detail: s.Describe()})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}
