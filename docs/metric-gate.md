# Coverage metric gate

`metric-gate` compares executable Python line coverage for `tools/` and
`plugin/`, plus Go statement coverage for `tools/sdlc-metrics`. It is
coverage-only; it does not run mutation tests. The committed
`metrics/coverage-history.json` is the source of truth and retains the default
10 most recent merged snapshots. Change `window` in that file to tune the
window (maximum 50).

For the first metric-gate PR, main has no history yet. CI checks out the PR
base commit, installs this PR's measurement harness and tests into a temporary
worktree, and measures that main tree. The history file must mark this as a
`bootstrap` baseline and include the source workflow run and main commit. The
gate compares the PR baseline and first candidate against those CI reports;
there is no empty-history pass. Later PRs read the history from the base commit
and require the PR copy to preserve its baseline, window, and prior rows.

Before opening or updating a PR after bootstrap, run the measurement suite and
record the candidate in the same PR:

```sh
python3 tools/metric_gate.py measure --out /tmp/coverage.json
python3 tools/metric_gate.py record --history metrics/coverage-history.json \
  --metrics /tmp/coverage.json --pr 123 --ref "$(git rev-parse --short HEAD)"
```

Replace `123` with the PR number and rerun `measure` after changing code. CI
re-measures the pull request and requires the committed candidate row to match
its percentages and coverage counts. It also compares the history against the
base commit's copy, allowing only one appended or replaced candidate row. On
the resulting `main` push, CI confirms that the latest recorded row matches
the merged tree. Thus the history advances in the PR commit and survives
runner restarts.

Each metric is compared with the preceding main snapshot using relative
percentage change; the net is the sum of those relative changes. A decline
over 10% fails even if another metric improves. A decline with a negative net
fails. A decline of 5% or more also needs a PR-body line such as
`Metric slip: python_tools 80.00 to 76.00, offset by python_plugin 80.00 to 85.00.`
The line must name the slipping metric, its old and new values, and an
improving offset. Any slip fails if the preceding history window trends down.
Missing history, an empty metric set, and incomplete metric sets fail closed.

This gate does not change theside's independent coverage floors or slack band.
Making the check required in branch protection is tracked separately by
OPS-339.
