package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// The EXIT CODES are the contract any calling workflow depends on.
// A guard that reports its refusal on stdout and exits 0 is not a guard.
// ---------------------------------------------------------------------------

func runCLI(t *testing.T, args ...string) (code int, stdout, stderr string) {
	t.Helper()
	var o, e bytes.Buffer
	code = run(args, &o, &e)
	return code, o.String(), e.String()
}

func TestExitZeroAndAValidDocumentOnTheKnownAnswerFixture(t *testing.T) {
	dir := t.TempDir()
	out := filepath.Join(dir, "metrics.json")
	sum := filepath.Join(dir, "summary.txt")
	code, stdout, stderr := runCLI(t,
		"-input", "testdata/known-answer.json",
		"-repo", "fixture/repo",
		"-now", "2026-06-15T00:00:00Z",
		"-window-days", "14",
		"-out", out, "-summary", sum)
	if code != exitOK {
		t.Fatalf("exit = %d, want %d\nstderr:\n%s", code, exitOK, stderr)
	}
	raw, err := os.ReadFile(out)
	if err != nil {
		t.Fatalf("metrics.json was not written: %v", err)
	}
	var rep Report
	if err := json.Unmarshal(raw, &rep); err != nil {
		t.Fatalf("metrics.json does not decode: %v", err)
	}
	if err := rep.Validate(); err != nil {
		t.Fatalf("the written document fails the contract: %v", err)
	}
	if len(rep.Metrics) != 16 {
		t.Errorf("wrote %d metric records, want 16", len(rep.Metrics))
	}
	if _, err := os.Stat(sum); err != nil {
		t.Errorf("the plain-text summary was not written: %v", err)
	}
	if !strings.Contains(stdout, "CENSUS") {
		t.Error("the summary must go to stdout so it is readable in CI output without opening anything")
	}
	// The unconfigured sink is announced on stderr BEFORE anything else runs.
	if !strings.Contains(stderr, "NOT CONFIGURED") {
		t.Errorf("the unconfigured Notion sink must be announced at start-up, stderr was:\n%s", stderr)
	}
}

func TestExitThreeOnAnEmptyDataset(t *testing.T) {
	dir := t.TempDir()
	out := filepath.Join(dir, "metrics.json")
	code, _, stderr := runCLI(t,
		"-input", "testdata/empty.json",
		"-repo", "fixture/empty",
		"-now", "2026-06-15T00:00:00Z",
		"-window-days", "14",
		"-out", out)
	if code != exitRefused {
		t.Fatalf("exit = %d, want %d (refused)\nstderr:\n%s", code, exitRefused, stderr)
	}
	if _, err := os.Stat(out); err == nil {
		t.Error("a refused run must write NO document — a metrics.json full of zeroes is exactly what the guard exists to prevent, and a downstream push would happily consume it")
	}
	if !strings.Contains(stderr, "nothing to measure") {
		t.Errorf("the refusal must say why, stderr was:\n%s", stderr)
	}
}

func TestExitThreeWhenTheWindowSelectedNothing(t *testing.T) {
	code, _, stderr := runCLI(t,
		"-input", "testdata/out-of-window.json",
		"-repo", "fixture/out-of-window",
		"-now", "2026-06-15T00:00:00Z",
		"-window-days", "14",
		"-out", filepath.Join(t.TempDir(), "m.json"))
	if code != exitRefused {
		t.Fatalf("exit = %d, want %d; a non-empty fetch whose window matched nothing is the vacuity case that looks healthiest\nstderr:\n%s", code, exitRefused, stderr)
	}
}

func TestUsageErrors(t *testing.T) {
	cases := []struct {
		name string
		args []string
	}{
		{"no repo and no input", []string{}},
		{"a repo that is not owner/name", []string{"-repo", "widgets", "-out", "-"}},
		{"a -now that is not RFC3339", []string{"-input", "testdata/known-answer.json", "-now", "yesterday"}},
		{"a non-positive window", []string{"-input", "testdata/known-answer.json", "-window-days", "0"}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if code, _, _ := runCLI(t, c.args...); code != exitUsage {
				t.Errorf("exit = %d, want %d", code, exitUsage)
			}
		})
	}
}

func TestTheDocumentIsByteStableAcrossRuns(t *testing.T) {
	// The Notion push is an upsert keyed on (metric_id, window.id). If two runs
	// over the same input produce different bytes, every re-run looks like a
	// change and the dashboard's history becomes noise.
	dir := t.TempDir()
	a := filepath.Join(dir, "a.json")
	b := filepath.Join(dir, "b.json")
	for _, out := range []string{a, b} {
		if code, _, stderr := runCLI(t,
			"-input", "testdata/known-answer.json", "-repo", "fixture/repo",
			"-now", "2026-06-15T00:00:00Z", "-window-days", "14", "-out", out); code != exitOK {
			t.Fatalf("exit = %d\n%s", code, stderr)
		}
	}
	ra, _ := os.ReadFile(a)
	rb, _ := os.ReadFile(b)
	if !bytes.Equal(ra, rb) {
		t.Error("two runs over the same input produced different bytes")
	}
}

func TestDumpDatasetRoundTripsToTheSameNumbers(t *testing.T) {
	// A published baseline that cannot be recomputed from a saved input is a
	// number nobody can check later. --dump-dataset is what makes it checkable,
	// so the round trip is asserted rather than assumed.
	dir := t.TempDir()
	ds := loadDataset(t, "testdata/known-answer.json")
	saved := filepath.Join(dir, "dataset.json")
	raw, err := json.MarshalIndent(ds, "", " ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(saved, raw, 0o644); err != nil {
		t.Fatal(err)
	}
	out := filepath.Join(dir, "m.json")
	if code, _, stderr := runCLI(t,
		"-input", saved, "-repo", "fixture/repo",
		"-now", "2026-06-15T00:00:00Z", "-window-days", "14", "-out", out); code != exitOK {
		t.Fatalf("exit = %d\n%s", code, stderr)
	}
	var rep Report
	rawOut, _ := os.ReadFile(out)
	if err := json.Unmarshal(rawOut, &rep); err != nil {
		t.Fatal(err)
	}
	if got := recordByID(t, rep, "leading.first_pass_merge_rate"); got.Value != 0.25 {
		t.Errorf("first_pass_merge_rate through a dumped dataset = %v, want 0.25", got.Value)
	}
}
