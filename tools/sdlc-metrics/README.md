# `sdlc-metrics`

Process metrics for one GitHub repository, computed from **issue and
pull-request metadata that already exists**. No instrumentation is added to
anything: one GraphQL query in, one `metrics.json` out.

It answers *where is the work, where is it stuck, and is any of it getting
better* — and it **refuses to answer** rather than answering with zeroes when it
examined nothing.

```bash
export GH_TOKEN=…                       # read access to issues + pull requests
./sdlc-metrics.sh --repo owner/name --window-days 28 --out metrics.json
./sdlc-metrics.sh --self-test           # gofmt + vet + go test -count=1
```

`SCHEMA.md` is the contract and the reasoning: every metric's operational
definition, the `status` vocabulary, and why a median over an empty set is
`insufficient_data` and never `0`.

---

## Configure these before the numbers mean anything

**This is the part that does not travel.** The tool is portable; its defaults
describe *a* repository, not *yours*. `SCHEMA.md §0` is the same table with the
consequences spelled out.

| What | How | Skipping it costs you |
|---|---|---|
| **`GH_TOKEN`** (or `GITHUB_TOKEN`) | environment | Nothing runs — **exit 1**, deliberately, rather than an empty window that reads as a quiet fortnight. |
| **Defect label taxonomy** | `-defect-labels` (default `bug, type:bug, incident, regression, defect`) | Nothing matches your labels, `defects_escaped_to_production` is a flattering **0**, and containment reads 100%. |
| **Class label prefixes** | `-class-label-prefixes` (default `proj:, area:, type:`) | Every defect is unclassified and `repeat_defect_classes` is 0. |
| **Surface roots** | `-surface-depth2-roots` (**default empty**) | Empty is correct for a single-service repo. A **monorepo** that skips it collapses every service into one surface. |
| **The self-review switch** | `-review-excludes-author` (**default `false`**) | You measure review *activity*, not human *scrutiny*. **Set it `true` if real people review here.** |
| Stale-issue threshold | `-stale-issue-days` (default 14) | Only a `detail` string. Set it to your norm. |
| Publishing (optional) | `NOTION_API_TOKEN`, `NOTION_DATABASE_ID` | Announced as `not_configured`, never silent, never a crash. The measurement still runs. |

Two of those need a decision rather than a value, and both defaults are the
*conservative* answer rather than the *common* one:

- **`-review-excludes-author`** — excluding the author is the better definition
  wherever reviewers are distinct humans, and it reports a flat zero wherever
  the author and the reviewer are the same login (an agent or bot that opens and
  approves, a solo maintainer). A visible overcount is recoverable by the reader;
  a silently empty metric set is not. `SCHEMA.md §7.1` is the full argument.
- **`-surface-depth2-roots`** — a default naming particular directories is a
  claim about somebody else's layout. `SCHEMA.md §7.3`.

Both settings are stated **in the emitted document**, in each affected metric's
`definitions` entry, so a consumer comparing two repositories — or one
repository across a change of flag — can see the metric changed meaning.

---

## The three rules worth carrying into whatever consumes this

1. **A count over an enumerable population is `ok` at zero. A median or ratio
   over an empty set is `insufficient_data`, always.** Emitting `0` there is how
   a quiet week and a broken query become indistinguishable. Read `status`
   before `value`.
2. **A run that examined nothing exits 3 and writes no document.** There is no
   `metrics.json` full of zeroes for anything downstream to consume.
3. **An unconfigured sink is announced, recorded as `not_configured`, and never
   silent.** Publishing nothing must never be recorded as a publish.

## Known wart, on purpose in the open

`lagging.defect_containment_rate` divides a count of **pull requests** by a
count of pull requests plus **issues**. Different units. It is useful as a trend
against its own history and worthless as an absolute, and that sentence is
appended to the metric's `detail` and its `definitions` entry — not just written
here — because a consumer reads `metrics.json` and never reads a design
document. A test asserts it survives the encode.

## Layout

```
main.go        flags, exit codes, the run
collect.go     the GitHub GraphQL fetch      (I/O only; decides no number)
dataset.go     the normalised input          (--dump-dataset writes it)
compute.go     Dataset -> Report, pure       (every number is decided here)
schema.go      the output contract + Validate
summary.go     the plain-text report
sink.go        publishing; optional, deletable
SCHEMA.md      the contract, in prose
testdata/      known-answer, empty, out-of-window, peer-review
```

Tests are hand-computed against the fixtures, never recorded from a run: a
golden file taken from the implementation asserts only that the code has not
changed, which is worth nothing if it was wrong the day the golden was taken.
