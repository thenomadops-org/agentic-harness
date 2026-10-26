# `sdlc-metrics` — the output contract

`schema_version: sdlc-metrics/v1`

This file is the interface. Whatever consumes `metrics.json` — a dashboard, a
spreadsheet importer, a push into a database — is a separate program written
against the JSON this tool emits, so a change here is a breaking change to a
consumer that is not in this repository and cannot be grepped for. **Design it
once; changing it later breaks them.**

It lives beside the code on purpose. `compute.go` emits the same operational
definitions *into* the document (`definitions`), so the code and this file
cannot drift apart without a test going red
(`TestEveryEmittedMetricHasADefinition`).

Origin: it was built for one repository whose owner asked for *"visibility on
what issues we are working on, where we may have problems and how we can
improve"*, and generalised on the way out. Where a rule below reads oddly
specific, that is why — the incident is kept because it names the failure, not
because it is a fact about your repository.

---

## 0. What you must configure before this is useful

**Nothing here is optional-but-nice. A repository that skips these gets numbers
that are wrong in a way that looks fine.**

| Setting | Where | If you skip it |
|---|---|---|
| **`GH_TOKEN`** (or `GITHUB_TOKEN`), read access to issues and pull requests | environment | The run **fails, exit 1**. It never reports an empty window in place of a missing token. |
| **`-defect-labels`** — the labels *your* tracker uses for "a defect reached main" | flag; default `bug, type:bug, incident, regression, defect` | Nothing matches, `defects_escaped_to_production` is a flattering **0**, and `defect_containment_rate` reads 100%. The tool cannot invent your taxonomy. |
| **`-class-label-prefixes`** — the prefixes that group defects into classes | flag; default `proj:, area:, type:` | Every defect is unclassified, `repeat_defect_classes` is 0, and the detail names how many were excluded. |
| **`-surface-depth2-roots`** — the top-level directories that are containers rather than surfaces | flag; **default EMPTY** | Correct for a single-service repository. A **monorepo** that skips it sees every service collapse into one surface (`api`), and the surface metrics stop distinguishing anything. See §7.3. |
| **`-review-excludes-author`** — whether a review by the pull request's own author counts | flag; **default `false`** | You get "how much review *activity* occurred", not "how much human scrutiny occurred". **A repository with real human reviewers should set it to `true`.** See §7.1 for why that is not the default. |
| **`-stale-issue-days`** | flag; default 14 | Only affects a `detail` string. Set it to your team's norm. |
| `NOTION_API_TOKEN` / `NOTION_DATABASE_ID` | environment; **optional** | The sink is announced as `not_configured`, the measurement still runs, and nothing is published. Never silence, never a crash. §6. |

Two of these are settings you have to **think about** rather than fill in:
`-surface-depth2-roots` (§7.3) and `-review-excludes-author` (§7.1). Both
defaults are deliberately the *conservative* answer rather than the *common*
one, and both say so where they are defined.

---

## 1. What it reads, and what it does not

Everything comes from **GitHub issue and pull-request metadata that already
exists** — one GraphQL query, no product instrumentation, no database, nothing
added to any service. If a metric cannot be derived from that, it is not here.

## 2. The document

```jsonc
{
  "schema_version": "sdlc-metrics/v1",
  "repo": "acme/widgets",
  "generated_at": "2026-09-03T01:57:24Z",
  "window": {
    "id": "2026-08-06..2026-09-03",     // primary key half; see §4
    "start": "2026-08-06T01:57:24Z",
    "end":   "2026-09-03T01:57:24Z",
    "days":  28
  },
  "collector": "tools/sdlc-metrics",
  "totals":  { /* §5, the census */ },
  "sinks":   [ /* §6, one per destination */ ],
  "metrics": [ /* §3, one record per metric */ ],
  "definitions": { "<metric_id>": "how it was computed" }
}
```

### 2.1 One record

```jsonc
{
  "metric_id":   "leading.first_pass_merge_rate",
  "title":       "Share merging on the first implementation pass",
  "family":      "leading",              // first segment of metric_id
  "value":       0.409,
  "unit":        "ratio",                // count | hours | days | ratio | cycles
  "status":      "ok",                   // ok | insufficient_data
  "subjects":    342,                    // how many things were examined
  "window":      { /* repeated, see §4 */ },
  "measured_at": "2026-09-03T01:57:24Z",
  "detail":      "140 of 342 reviewed pull requests merged in window took no branch change after review began; 109 merged with no review at all and are excluded."
}
```

`detail` is prose for humans. It is **not parsed by anything** and its wording
may change without a schema bump. Everything else is contract.

---

## 3. `status`, and the rule that makes zeroes trustworthy

This is the most important paragraph in the file, because it is the thing the
whole tool was built around.

| status | meaning |
|---|---|
| `ok` | The number was computed over a real subject set. `value` is a measurement. |
| `insufficient_data` | The metric is a **statistic over an empty set**. `value` is `0` and **carries no information**. |
| `not_configured` | *Sinks only.* No credential. Not a success, not an error, never silence. |
| `failed` | *Sinks only.* Configured, and the attempt failed. |

**A count over an enumerable population is `ok` even when it is 0.** "There are
zero open pull requests" is a real fact, and `totals` proves the query that
produced it examined something.

**A median or a ratio over an empty set is `insufficient_data`, always.** There
is no median of nothing. Emitting `0` there is exactly how a quiet week and a
broken query become indistinguishable.

A consumer **must read `status` before `value`.** A record with
`status != "ok"` and a non-zero `value` is malformed and the collector refuses
to write one (`Report.Validate`).

### 3.1 And the whole run can refuse

If the run examined **nothing at all** — zero pull requests open or in window,
or zero issues open or in window — it is an **error**, exit code **3**, and
**no document is written**. A `metrics.json` full of zeroes is never produced,
so a downstream push can never consume one.

Two fixtures pin this, because there are two ways to examine nothing and only
one of them looks empty:

- `testdata/empty.json` — the fetch returned nothing.
- `testdata/out-of-window.json` — the fetch **worked**, and the window selected
  nothing. This is the one that looks healthy: a wrong `-now`, a wrong
  `-window-days`, or a paginator that stopped early all produce it.

A third fixture, `testdata/peer-review.json`, is not about vacuity: it is a
repository with a mix of self-review and peer review, and it exists so
`-review-excludes-author` is proved to **move** the numbers rather than merely
to parse (§7.1).

---

## 4. Keys, stability, and versioning

- **`(metric_id, window.id)` is the row key.** Re-running the collector for the
  same window is an **upsert**, not a duplicate row. `window` is repeated on
  every record so a consumer that flattens `metrics` into one table row per
  record — which is what a Notion database is — needs nothing from the
  envelope.
- **A `metric_id` is never reused for a different meaning.** Retire it and add a
  new one. Reusing one silently changes what a chart was measuring halfway
  down its own history.
- **Bump `schema_version`** when a field is removed or renamed, or when an
  existing metric id changes meaning. **Adding** a new metric id, or a new
  optional field, is backward compatible and does not bump it — a consumer that
  iterates `metrics` and keys off `metric_id` keeps working.
- The document is **byte-stable** across runs over the same input (records
  sorted by `metric_id`), so a re-run that changed nothing produces an
  identical file.

---

## 5. `totals` — the census

```jsonc
"totals": {
  "pull_requests_examined": 470,
  "pull_requests_merged":   451,
  "pull_requests_open":     1,
  "issues_examined":        307,
  "issues_open":            72,
  "review_events":          820,
  "review_threads":         0,
  "review_authors": { "reviewer1": 783, "author1 (= pull request author)": 37 }
}
```

The census is the evidence the run examined something. Plot `subjects` beside a
value and a number computed over nothing becomes visible, which a bare value
cannot show.

`review_authors` is published in **both** settings of `-review-excludes-author`,
because whichever way that switch is set the reader needs to see whose review is
being counted rather than assume a human's — see §7.1. It is the **raw**
population and is never filtered by the switch: `review_events: 820` sitting
beside `insufficient_data` on every review metric is the finding that every
review came from the author.

---

## 6. `sinks` — publishing, and the credential that does not exist

The bundled sink is a Notion push whose integration token most repositories will
never create. **The whole of `sink.go` is optional** — delete it and the tool
still measures. What it must never become is a destination that records a
success it did not have. The rule, which came from a cache-purge integration in
the same position:

1. **An unconfigured sink does not crash the run.** The measurement is the
   deliverable and is still computed, written and printed.
2. **An unconfigured sink is never silent.** It is announced on stderr at
   start-up, recorded as `not_configured` — never `ok` — and printed in the
   summary.
3. **Refusing is not returning nil.** `DisabledSink.Publish` returns
   `ErrSinkNotConfigured`, so no caller can record a success it never had.

```jsonc
"sinks": [{
  "name": "notion",
  "status": "not_configured",
  "detail": "notion sink: NOT CONFIGURED (unset: NOTION_API_TOKEN, NOTION_DATABASE_ID). …"
}]
```

`detail` names the **missing environment variables**, never a secret's value.

**The live Notion client is deliberately not written.** An HTTP client against
an API with no credential to test it is code that looks like a capability and
has never once run. What ships is the contract, the announcement and the seam
(`NewNotionSink` in `sink.go`). With both settings present but no client, the
status is **still** `not_configured`, with a detail saying so: publishing
nothing must never be recorded as a publish.

**Writing your own sink** means implementing the four-method `Sink` interface in
`sink.go` and adding it to the slice in `main.go`. The one rule that is not
yours to change: a sink that did not publish returns an error, never `nil`.

---

## 7. The metrics, and their operational definitions

Three terms are defined first, because the metrics that follow depend on them
and two of them are configurable.

### 7.1 "Review event", and the `-review-excludes-author` switch

> A **review event** is a submitted pull-request review, or a comment in a
> review thread. Whose reviews count is set by **`-review-excludes-author`**:
>
> - **`false` (default)** — from **any** login, **including the pull request's
>   own author**.
> - **`true`** — from any login **except** the author. A review with **no
>   attributed author** is excluded too: it cannot be shown to be a peer's, and
>   counting it would let the excluded thing back in through a blank field.

**Set it to `true` if your repository has real human reviewers.** Excluding the
author is the better definition wherever the reviewer is a different person, and
it is the only one that measures scrutiny rather than activity.

#### Why the default is `false`, which is the *worse* definition

Because the two mistakes are not symmetrical.

With the switch **off** in a peer-reviewed repository, the review metrics
**overcount** — self-review is folded in — and the overcount is **visible**:
`totals.review_authors` marks every self-review `(= pull request author)`, so a
reader can see the size of the error and, if it matters, set the flag.

With the switch **on** in a repository where the author and the reviewer are the
same login, every review metric goes to **`insufficient_data`** — correctly, and
uselessly. That case is not exotic: an agent-run repository where a GitHub App
opens and reviews every pull request (the project this tool came from was
exactly that, and a non-author rule classified 100% of its review activity as
self-review), a bot that opens and approves, a solo maintainer.

The asymmetry decides it. A visible overcount is recoverable by the reader; a
silently empty metric set looks like a quiet fortnight. So the tool ships the
conservative default, makes the switch explicit, and states the choice **in the
document**: every affected `definitions` entry names which rule was applied, so
a consumer plotting a history across a change of the flag can see that the
metric changed meaning.

> [!note] This was deliberately *not* a flag in the source repository
> There, shipping it defaulted wrong was judged worse than not shipping it, and
> the breakdown in `totals.review_authors` carried the choice instead. A repo
> intended for **reuse** cannot make that call on a stranger's behalf, so the
> switch exists here and this section is the argument that comes with it.

**Read the review metrics as "how much review activity occurred", not "how much
human scrutiny occurred", unless you have set the flag.**

**What the switch does *not* touch:**
`lagging.review_threads_settled_without_change_rate` keys on thread
**resolution**, not on review events, so it is identical in both modes — and
`totals` is the raw census in both modes (§5).

### 7.2 "First implementation pass" and "rework cycle"

> Merge every **review event** and every **change event** (a commit on the head
> branch, or a force push) into one timeline ordered by timestamp, **reviews
> first on a tie**. Walk it. A review **arms** the counter; the next change
> after an armed counter is **one rework cycle**, and disarms it. Changes before
> any review are the first implementation pass and count for nothing.
>
> A pull request with **zero review events is `unreviewed`** and is excluded
> from both the first-pass rate and the rework mean. It is never counted as a
> first pass.

```
commit commit REVIEW commit REVIEW merge   -> 1 cycle
commit REVIEW REVIEW commit commit merge   -> 1 cycle   (one round trip)
commit commit REVIEW merge                 -> 0 cycles, FIRST PASS
commit commit merge                        -> unreviewed, EXCLUDED
```

Merging with no review is not evidence of getting it right the first time; it is
evidence of no review. Counting it as a first pass would make *skipping review*
the fastest way to improve the number, which is the failure mode of every
process metric that gets gamed.

**Known measurement error, stated rather than discovered later:** a commit's
timestamp is its **committer date**, not its push time. A commit authored before
a review and pushed after it is dated before the review and does not register as
rework. Force pushes are collected precisely because the common form of that
case — amending in response to review — leaves no new commit node.

### 7.3 "Surface"

> The **first path segment** of a changed file, or the **first two** when the
> first is listed in **`-surface-depth2-roots`**. A file at the repository root
> is `(root)`.

**`-surface-depth2-roots` defaults to EMPTY**, which is the right answer for a
single-service repository: every surface is then a top-level directory, and
`src/a/b.go` → `src`, `docs/x.md` → `docs`, `Makefile` → `(root)`.

**A monorepo must set it**, or every service collapses into one bucket. With
`-surface-depth2-roots api,mobile,tools,.github`:
`api/gateway/internal/policy/policy.go` → `api/gateway`;
`mobile/iosApp/A.swift` → `mobile/iosApp`; `scripts/x.sh` → `scripts` (not
listed, so depth 1); `Makefile` → `(root)`.

The default was flipped to empty when this tool was generalised: the previous
default named one particular repository's directories, which silently mis-bucket
every repository that does not share them. The emitted `definitions` entry for
the surface metrics states which rule was applied, so two repositories'
documents are never compared under different bucketings without saying so.
`TestTheDefaultSurfaceRootsAreEmptyAndCollapseAMonorepo` pins both readings of
the same fixture (7 surfaces with no roots, 11 with them).

### 7.4 The catalogue

#### Flow — what is in motion

| metric_id | unit | definition |
|---|---|---|
| `flow.open_issues_without_pr` | count | OPEN issues with no pull request in their GitHub timeline (`CONNECTED_EVENT` / `CROSS_REFERENCED_EVENT`), at the measurement instant. Not window-scoped: an issue open for six months is in flight today. `detail` names how many are at least `-stale-issue-days` old and the oldest one. |
| `flow.open_issues_without_pr_age_p50_days` | days | Median age of the above. |
| `flow.open_prs` | count | Pull requests in state OPEN at the measurement instant. Not window-scoped. |
| `flow.open_pr_age_p50_hours` | hours | Median hours since creation of the above. |
| `flow.open_pr_awaiting_review_p50_hours` | hours | Median hours open **non-draft** pull requests have been waiting. A pull request is *waiting* when its most recent branch change (or its ready-for-review moment, whichever is later) has **no review event after it**. One whose latest change is already reviewed contributes **nothing**, not a zero — averaging in zeroes hides the one that is actually stuck. |
| `flow.surfaces_in_flight` | count | Distinct surfaces touched by open pull requests. `detail` lists the busiest. |
| `flow.surfaces_touched_in_window` | count | Distinct surfaces touched by every pull request examined in the window. Answers "where is the work" when nothing happens to be open — which, in a repository that merges within minutes, is most of the time. |

#### Leading — the speed of the process

| metric_id | unit | definition |
|---|---|---|
| `leading.issue_to_pr_p50_hours` | hours | Median hours from an issue opened **in the window** to the creation of the earliest pull request associated with it **and created at or after it**. A pull request that predates the issue did not answer it and would give a negative latency. See §8 on association. |
| `leading.time_to_first_review_p50_hours` | hours | Median hours from a pull request becoming reviewable (ready-for-review, else creation) to its first **review event** (§7.1 — whose reviews count depends on `-review-excludes-author`), over pull requests **opened in the window** that received one. `detail` names how many received none. |
| `leading.first_pass_merge_rate` | ratio | Share of pull requests **merged in the window** and carrying at least one review event whose branch took **no change after the first review event**. Unreviewed merges are excluded from both numerator and denominator (§7.2). |

#### Lagging — quality and rework

| metric_id | unit | definition |
|---|---|---|
| `lagging.rework_cycles_per_change_mean` | cycles | Mean rework cycles (§7.2) per reviewed pull request merged in the window. |
| `lagging.defects_caught_before_merge` | count | Pull requests merged in the window with at least one rework cycle **or** at least one `CHANGES_REQUESTED` review — a defect found while the change was still a proposal. |
| `lagging.defects_escaped_to_production` | count | Issues opened in the window carrying any of `-defect-labels` (default `bug, type:bug, incident, regression, defect`). Label-driven by necessity: nothing in GitHub metadata distinguishes a defect from a feature request without one. |
| `lagging.defect_containment_rate` | ratio | `caught / (caught + escaped)`. **`insufficient_data` when both are zero** — zero known defects is not a 100% containment rate. **A KNOWN WART, and it is in the output, not just here:** the numerator counts *pull requests*, the denominator counts *issues*. They are different units, so this is a proportion of convenience — a trend against its own history, never an absolute. The caveat is appended to the metric's `detail` **and** carried in its `definitions` entry, on **both** branches, because a consumer reads `metrics.json` and never reads this file. `TestTheDefectContainmentUnitCaveatIsInTheEmittedDocument` asserts it survives the encode. |
| `lagging.review_threads_settled_without_change_rate` | ratio | Share of **resolved** review threads with no commit or force push after the thread's **last comment**. GitHub exposes **no `resolvedAt` timestamp** on a review thread, so the last comment is the only available lower bound; the metric is stated in those terms rather than pretending to a precision it does not have. |
| `lagging.repeat_defect_classes` | count | Defect classes with **two or more** labelled defect issues opened in the window. A **class** is the sorted set of an issue's labels matching `-class-label-prefixes` (default `proj:`, `area:`, `type:`), joined with `+`. An issue matching **none** is excluded and named in `detail`, never bucketed with the other unlabelled ones — that would manufacture a repeat out of a labelling gap. |

---

## 8. Issue ↔ pull-request association

Two independent sources, unioned, because neither alone is sufficient under
every project's conventions:

1. **The issue side** — each issue's own timeline (`CONNECTED_EVENT`,
   `CROSS_REFERENCED_EVENT`). Collected per issue rather than derived from the
   window's pull requests, so an open issue whose only pull request predates the
   window is still seen as having one. The alternative under-reports "no pull
   request" precisely on the *oldest* issues, which are the ones the metric
   exists to surface.
2. **The pull-request side** — `closingIssuesReferences`, **plus** `#nnn`
   mentions in the title or body that resolve to a **known issue number**.

The mention parsing is not belt-and-braces; it is load-bearing wherever the
contributing rules forbid a closing keyword bound in prose and ask for a bare
`#nnn` claim line instead. On one project that was the rule, so
`closingIssuesReferences` was **empty for most pull requests** and a collector
using it as the only linkage reported that almost no issue ever acquired one.
If your project requires `Closes #n`, the other half carries the load. Both are
collected, so neither convention loses the link.

Numbers that are not in the issue set are dropped, so a pull request citing a
sibling **pull request** never counts as issue linkage.

---

## 9. Running it

```bash
# the launcher: finds the tool, refuses loudly if the toolchain is missing,
# builds once and runs.
tools/sdlc-metrics/sdlc-metrics.sh --repo owner/name --window-days 28 --out metrics.json

# a repository with human reviewers and a monorepo layout
tools/sdlc-metrics/sdlc-metrics.sh --repo owner/name \
  --review-excludes-author \
  --surface-depth2-roots api,mobile \
  --defect-labels bug,incident

# offline, from a saved dataset — this is how a published number stays checkable
go run . -input dataset.json -now 2026-09-03T01:57:24Z -out -

# the tool's own suite (-count=1 is not optional: `ok (cached)` hides failures)
tools/sdlc-metrics/sdlc-metrics.sh --self-test
```

Needs `GH_TOKEN` or `GITHUB_TOKEN` with read access to issues and pull requests.
Without one it **fails** (exit 1) rather than reporting an empty window — a
missing token is not a degraded measurement, it is no measurement.

`-dump-dataset` writes the normalised input. That is not a debugging
convenience: a number in a pull-request body that cannot be recomputed from a
saved input is a number nobody can check a year later.

### Exit codes — the contract the workflow depends on

| code | meaning |
|---|---|
| 0 | measured; the document was written |
| 1 | run-time failure: fetch failed, document would not validate, or a **configured** sink failed |
| 2 | usage error |
| 3 | **refused** — the vacuity guard fired; nothing was examined and **no document was written** |

An unconfigured sink is **not** a failure and does not change the exit code.

---

## 10. Every repository-shaped knob, and the fact that each one is a flag

The collector reads GitHub metadata only, so it is portable as-is once these are
set. **This table is the complete list, and it is machine-checked.**
`TestEveryConfigKnobIsAFlag` walks `Config` by reflection against `configKnobs`
in `main.go` and against the registered flag set, so a new field cannot arrive
without a flag and a renamed flag cannot leave the table pointing at nothing. A
claim in a document that nothing verifies is a claim that quietly stops being
true.

| flag | default | why it is repo-shaped |
|---|---|---|
| `-repo` | *(required)* | `owner/name`. Or `-input` a saved dataset and measure offline. |
| `-window-days` | `28` | The reporting cadence you want. |
| `-now` | the clock | The measurement instant. Pin it and a run is reproducible. |
| `-defect-labels` | `bug, type:bug, incident, regression, defect` | A taxonomy the collector cannot invent. A repository with none gets `insufficient_data`, not a flattering zero. |
| `-class-label-prefixes` | `proj:, area:, type:` | Same — how *your* labels group a defect into a class. |
| `-surface-depth2-roots` | **empty** | Your directory layout. Empty is right for a single-service repository; a monorepo must set it or every service becomes one surface (§7.3). |
| `-stale-issue-days` | `14` | A team norm. |
| `-review-excludes-author` | `false` | Whether your reviewers are distinct people from your authors (§7.1). **Set it `true` if they are.** |

Flags that shape the *run* rather than the repository — `-input`,
`-dump-dataset`, `-out`, `-summary` — are in `-h` and are not listed above.

### What is still not configurable, and would need thought

- **Which metrics exist.** The catalogue in §7.4 is fixed. Adding one is a code
  change plus a `definitions` entry plus a hand-computed test — deliberately,
  because a metric nobody can reproduce is a number nobody can argue with.
- **The defect-containment unit mismatch** (§7.4). It is a wart, it is stated in
  the output, and fixing it properly means deciding what "a defect" is in units
  that match — which is a product decision, not a flag.
- **Where the numbers go.** One sink ships, unconfigured (§6).
