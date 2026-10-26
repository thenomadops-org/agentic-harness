---
name: merge-pr
description: Verify with the GitHub API that a PR contains the commit you reviewed and is genuinely green, then merge it. Use whenever merging any PR to main in this repo, and whenever opening one. Deliberately repo-local — there is no global copy; new-project vendors it into new repos.
---

# Identify the commit, judge the latest checks, then merge

> **This skill is deliberately repo-local, and there is no global copy. That is
> the design, not a broken install.** The owner ruled on **2026-08-13**: one
> `merge-pr`, kept in the repo, "in case we have to get a new local system" — a
> repo-local skill travels with the checkout and takes precedence over a global
> one, so each repo always carries its own merge discipline. A vault-global
> duplicate existed for part of that day, drifted from this file within hours,
> and was deleted.
>
> The accepted consequence is that a repo-local skill does not reach a **new**
> repo. What closes that is the **`new-project`** skill: it vendors a
> repo-agnostic copy of this file into `.claude/skills/merge-pr/` of every
> repository it seeds, and records it in that repo's `.factory/MANIFEST`. If you
> improve a mechanism here that is not specific to any one project, improve the seed copy
> at `~/.claude/skills/new-project/seed/tier0/.claude/skills/merge-pr/SKILL.md`
> too — otherwise the next repo starts from the older text.
>
> **Confirm which copy you are actually running before trusting any of it.** A
> session started before this file landed can still serve the *deleted* vault-global
> text from its own context, headed with a path that no longer exists on disk —
> observed 2026-08-13 during review. The disk is the authority:
>
> ```bash
> ls -la ~/.claude/skills/ | grep merge-pr || echo "no global copy — correct"
> git -C "$(git rev-parse --show-toplevel)" log -1 --format=%h -- .claude/skills/merge-pr/SKILL.md
> ```
>
> If a skill quotes you a path, `stat` it. A body of text is not evidence that its
> source still exists.

Merging is autonomous (tier 1 — reversible via `git revert`). The mandate is **verify first**,
against the API rather than against what a branch name, a PR body, or a returned URL claims.

Three questions, in this order. Skipping the first is how this repo shipped work nobody read.

1. **Is the code in this PR the code I reviewed?** (head SHA identity)
2. **Are its checks green *now*?** (latest run per name — not the raw list)
3. **Was it built against the tree it is landing into?** (base currency)

Every gate below names the incident that justifies it. A gate with no incident behind it
should be deleted, not kept for tidiness.

## The failure modes this exists to stop

- **A branch name is not an identity.** 2026-08-13, PR #179: a killed agent had already
  pushed `PROJ-196-cd-that single-node cluster` and opened PR #179. The replacement commit was written locally
  on a branch of the **same name**, was never pushed, and `gh pr create` returned the
  **existing** PR instead of creating one. `gh pr merge 179` then merged the abandoned work.
  The reviewed evidence described a file that never reached `main`; it took PR #180
  (-1940 lines) to undo. Nothing in the old check list would have caught it, because the
  old list never asked *which commit* it was clearing.
- **A commit's check-run list is HISTORICAL, not current.** The same day, a re-run `dod`
  was read as red at a SHA where it was green. `[.check_runs[] | select(.conclusion !=
  "success")]` returns every run that ever failed at that SHA, including ones a later run
  has already superseded. Judge the **latest run per name** or you will refuse a green PR —
  and, worse, learn to wave the filter through when it "always shows that". A mandate the
  tool does not implement is a mandate the human improvises, and an operator trained to
  override the filter by eye will eventually override a genuine failure by the same reflex.
- **Branch protection requires only `dod` and `lint`.** A PR with a red *service test* still
  reports `mergeable_state: clean`. Never conclude green from `mergeable_state` alone.
- **`strict` is false.** GitHub will merge a branch cut before `main` moved. That is how
  PR #144 merged green and left `main` red for a day: its CI never compiled its own changes
  against the tree it was landing into. Per-PR CI is structurally blind to this.

---

## Gate 1 — the PR head SHA must EQUAL the commit you reviewed

**Write the SHA down when you review, and compare it at merge time.** Not the branch name,
not the PR number, not "the latest commit on my branch" — the 40-character SHA you actually
read a diff of. Put it in the review comment or the tracker comment so the comparison is
auditable by someone who was not there.

```bash
REPO=your-org/your-repo
N=<pr-number>
REVIEWED=<the-40-char-sha-you-reviewed>

HEAD_SHA=$(gh api repos/$REPO/pulls/$N --jq .head.sha)
[ "$HEAD_SHA" = "$REVIEWED" ] \
  && echo "SHA-MATCH $HEAD_SHA" \
  || { echo "REFUSE: PR head $HEAD_SHA != reviewed $REVIEWED"; }
```

If they differ, **stop and re-review the head SHA.** Do not reason about why they differ —
a rebase, a fixup, a force-push and somebody else's abandoned branch all look identical here,
and only one of them is benign.

**If you authored the change, also prove your local work is what's in the PR.** Incident 1
was a local commit that never left the machine:

```bash
git rev-parse HEAD                 # what you built and tested
git rev-parse @{u}                 # what you actually pushed
gh api repos/$REPO/pulls/$N --jq .head.sha
```

All three must be the same string. `git status` saying "up to date" is not proof — it
reports the tracking ref's *last known* position, and a branch that was never pushed has no
tracking ref to be wrong about.

## Gate 2 — judge the LATEST run per NAME

Never filter the raw list. Group by name, take the newest run of each, judge only those:

```bash
gh api "repos/$REPO/commits/$HEAD_SHA/check-runs?per_page=100" --paginate --slurp \
 | jq -r '[.[].check_runs[]] | group_by(.name) | map(sort_by(.started_at) | last)
          | map(select(.conclusion != "success" and .conclusion != "skipped"
                       and .conclusion != "neutral"))
          | map("\(.name)=\(.conclusion // .status)") | join(", ")'
```

Merge only when this prints **nothing**. Measured on this repo, 2026-08-13 — both PRs
merged green, and the raw-list form calls both of them red:

```
=== PR #181  merged=true ===
  raw-list filter (broken):   dod=failure
  latest-per-name (correct):
=== PR #173  merged=true ===
  raw-list filter (broken):   dod=cancelled
  latest-per-name (correct):
```

Notes that are not optional:

- `--slurp` (not `--jq`) because `--paginate --jq` applies the filter **per page** and
  concatenates — `group_by` across a page boundary would silently regroup nothing. gh
  refuses `--slurp` together with `--jq`, so pipe to `jq`. Under 100 checks it makes no
  difference; the day it does, it fails quietly.
- `sort_by(.started_at) | last`, never `.[0]`. The array order is not chronological.
- **An empty list of checks is not green.** If the PR reports zero checks at all, refuse —
  a check that never ran is indistinguishable from one that passed, and that is this repo's
  signature defect. Confirm with `gh api .../check-runs --jq .total_count`.
- **`ci-gate` must be present and green.** It is the only check that knows which workflows
  *should* have run; path filters mean a service's tests can be **absent** rather than red,
  and absent reads as fine.
- A `CANCELLED` run at the same SHA is normal when the body was edited (`dod-check` runs on
  `edited`). Superseded by a later run of the same name, it is not a failure. Edit a PR body
  **at most once** so the rollup stays legible and so repeated edits do not start runs that
  cancel each other.

To see the full roster before deciding — read it, do not just trust the empty filter:

```bash
gh api "repos/$REPO/commits/$HEAD_SHA/check-runs?per_page=100" --paginate --slurp \
 | jq -r '[.[].check_runs[]] | group_by(.name) | map(sort_by(.started_at) | last)
          | .[] | "\(.conclusion // .status)\t\(.name)"'
```

## Gate 3 — base currency

```bash
git fetch -q origin
git merge-base --is-ancestor origin/main "$HEAD_SHA" && echo BASE-CURRENT
```

If it fails: `gh pr update-branch $N`, wait for checks, then re-verify. Updating the branch
changes the head SHA, so everything you concluded about the old head is void.

**But do not literally "start again at Gate 1" — as written, Gate 1 cannot pass here.** It
compares `head.sha` to `REVIEWED`, and `update-branch` has just guaranteed they differ. Taken
at face value it says REFUSE on every updated PR; the agent under time pressure then sets
`REVIEWED=<new head>` and calls it verified, which is the exact laundering this skill exists
to stop. Re-reading the full diff is the other trap: after the merge the diff also contains
main's changes, so "re-review" balloons and gets skimmed.

**Instead, prove the update was ONLY a merge.** Two assertions. Each ends in a comparison
that prints its own verdict — if you are reading git's raw output and deciding for yourself,
you are running an older draft of this section, and that draft had a hole in it.

```bash
git fetch -q origin
REVIEWED=$(git rev-parse "$REVIEWED")          # normalise; abbreviations DO resolve
NEW=$(gh api repos/$REPO/pulls/$N --jq .head.sha)

# 1. NEW is a merge of exactly {the head you reviewed, a commit already in main}
P1=$(git rev-parse "$NEW^1" 2>/dev/null); P2=$(git rev-parse "$NEW^2" 2>/dev/null)
if [ "$P1" = "$REVIEWED" ] && [ -n "$P2" ] && git merge-base --is-ancestor "$P2" origin/main
then echo "PARENTS-OK"
else echo "REFUSE: $NEW is not your reviewed head merged with the base"; fi

# 2. every file the REVIEW covered is byte-identical at both heads.
#    The set is derived from BOTH sides on purpose — see the warning below.
MB=$(git merge-base "$REVIEWED" "$P2")
SET=$(mktemp)
{ git diff --name-only "$MB" "$REVIEWED"                             # what you reviewed
  gh api repos/$REPO/pulls/$N/files --paginate --jq '.[].filename'   # what the PR shows now
} | sort -u > "$SET"

n=0
while IFS= read -r f; do
  a=$(git rev-parse "$REVIEWED:$f" 2>/dev/null); b=$(git rev-parse "$NEW:$f" 2>/dev/null)
  [ "$a" = "$b" ] || { echo "CHANGED: $f"; n=$((n + 1)); }
done < "$SET"

if [ "$n" -eq 0 ] && [ -s "$SET" ]
then echo "FILES-IDENTICAL ($(wc -l < "$SET") compared)"
else echo "REFUSE: $n file(s) differ, or the compared set was empty"; fi
```

> ⚠️ **Never narrow set 2 to the PR's file list alone.** That list is `diff(base..head)`,
> computed from the **new** side only, so it sees content arriving and is blind to your work
> **departing**. If the merge reverts a file back to base — which is what "take main's side",
> the commonest bad resolution of a real conflict, does — the file no longer differs from base,
> **drops out of the list, and is never compared.** Both assertions pass, and the skill then
> tells you your review carries over. It does not.
>
> Reproduced 2026-08-13: a reviewed `auth: allow_all = false` reverted to `true` by the merge.
> PR file list `[README.md]`, `policy.conf` absent from it, `PARENTS-OK`, zero `CHANGED` lines.
> On this repo the contended file is `api/gateway/internal/policy/policy.go`, written by
> stories in 8 of 10 domain plans — so the blast radius of this hole is **authz**. Unioning in
> the reviewed side's own change set (`git diff $MB $REVIEWED`) closes it: the same run then
> correctly prints `CHANGED: policy.conf`. Content *injected* by a merge was always caught;
> only removal was invisible.
>
> The `-s "$SET"` guard is not decoration. A comparison that examined nothing has not passed.

Measured, gh 2.97.0 / git 2.43.0, 2026-08-13. Replaying PR #186's real `update-branch`:
`PARENTS-OK`, then `FILES-IDENTICAL (1 compared)` — the benign case is **not** false-positived
by the wider set. Against the reverted-authz repro: `PARENTS-OK`, then `CHANGED: policy.conf`
and `REFUSE`. Note `git rev-parse <sha>:<path>` **echoes its own argument on stdout and exits
128** when the path does not exist at that commit, so a file the PR *adds* compares unequal and
reports `CHANGED`. That is the safe direction; do not "fix" it into silence.

An abbreviated `REVIEWED` resolves fine in assertion 2 — measured, `18d8aca8`, `18d8aca84a1a`
and the full SHA all return the same blob — but assertion 1 is a string comparison, so
`git rev-parse` it first, which the block above does. An earlier draft of this file claimed an
abbreviation "will never match"; that was false, and it was reached by reading a negative
control that had actually used a **wrong** SHA. Two different reasons to fail look identical
in a control that only records *that* it failed.

Both hold ⇒ the merge introduced nothing of its own **and removed nothing of yours**, your
review carries over, and you may set `REVIEWED=$NEW` **because you proved it**. Either fails ⇒
real content arrived or departed. Re-review the head properly before going on.

## Gate 4 — the rest

```bash
gh api repos/$REPO/pulls/$N --jq '"\(.mergeable) \(.mergeable_state) \(.draft) \(.base.ref)"'
gh api repos/$REPO/pulls/$N --jq .body | grep -nE 'MERGE-ORDER-HOLD|DO NOT MERGE'
```

- `mergeable=true`, `mergeable_state=clean`, `draft=false`, base is `main`.
- No `MERGE-ORDER-HOLD` / `DO NOT MERGE` in the body. Several stories must land in a fixed
  order and nothing else enforces it.
- **It has actually been reviewed by a human or an agent that read the diff.** Green means
  the machine is happy, not that the change is correct — every review round on this repo has
  found at least one blocker.

## Gate 5 — does another open PR CONTAIN this one? (choose the merge strategy first)

Two different questions, and asking only the first is how PR #210 ended up in conflict on
2026-08-14:

| question | what it reads | what it tells you |
|---|---|---|
| is another PR **based on** my branch? | GitHub's `base` field — metadata someone set | `--delete-branch` will silently **close** it |
| does another PR **contain** my commits? | the git graph — true whether or not anyone declared it | a **squash** will put it into **conflict** |

**Ask both. Neither implies the other.**

```bash
# A. based-on — which PRs --delete-branch would close
gh pr list --repo $REPO --state open --base "$(gh api repos/$REPO/pulls/$N --jq .head.ref)"

# B. containment — which PRs a squash would break
git fetch -q origin "+refs/pull/*/head:refs/remotes/pr/*"      # fetch ALL heads first
HEAD_SHA=$(gh api repos/$REPO/pulls/$N --jq .head.sha)
git cat-file -e "$HEAD_SHA^{commit}" 2>/dev/null \
  || { echo "REFUSE: $HEAD_SHA is not in this repo — cannot test containment"; }

# Ask about the commits this PR INTRODUCES, never about its tip. See the warning
# below: one `gh pr update-branch` makes the tip an ancestor of nothing while
# every commit under it is still duplicated in the child.
MB=$(git merge-base origin/main "$HEAD_SHA")
MINE=$(mktemp); git rev-list --no-merges "$MB..$HEAD_SHA" > "$MINE"
MINE_N=$(grep -c . "$MINE")
[ "$MINE_N" -gt 0 ] \
  || { echo "REFUSE: PR #$N introduces no non-merge commits — this check has nothing to test and its silence means nothing"; }

contained=0
for other in $(gh pr list --repo $REPO --state open --json number --jq '.[].number'); do
  [ "$other" = "$N" ] && continue
  oh=$(gh api repos/$REPO/pulls/$other --jq .head.sha)
  if ! git cat-file -e "$oh^{commit}" 2>/dev/null; then
    echo "REFUSE: PR #$other head $oh not fetched — this check CANNOT answer, do not read its silence as 'clear'"
    contained=1; continue
  fi
  # `while read`, not `for c in $MINE`. Under zsh — which is the login shell here —
  # an unquoted parameter expansion is NOT word-split, so `for c in $MINE` iterates
  # ONCE over a single newline-joined string, every --is-ancestor fails on a bogus
  # object name, and this prints NO-CONTAINERS for every PR in the repo. Measured
  # 2026-08-14 while writing this very fix. It is the same vacuity as the cat-file
  # hole, reintroduced by the repair for it.
  hits=0
  while IFS= read -r c; do
    [ -n "$c" ] || continue
    git merge-base --is-ancestor "$c" "$oh" && hits=$((hits + 1))
  done < "$MINE"
  if [ "$hits" -gt 0 ]; then
    echo "CONTAINED-BY #$other — $hits of my $MINE_N commit(s) are already in it; a squash will put #$other into conflict"
    contained=1
  fi
done
[ "$contained" -eq 0 ] && echo "NO-CONTAINERS ($MINE_N commit(s) tested) — squash is safe"
```

> ⚠️ **Do not put `$HEAD_SHA` back into that `--is-ancestor` call.** The first
> version of this gate tested the tip, and on its first real use it was wrong.
> Measured 2026-08-14, PR #209 against PR #210:
>
> ```
> tip test:  is-ancestor 7ac4c290 822ac8a5   -> false   "NO-CONTAINERS — squash is safe"
> per-commit: merge-base(main,#209) = c29295df
>             introduced --no-merges = a577668, bff3898
>             ancestors of #210 head = 2 of 2         "CONTAINED-BY #210"
> ```
>
> **Overlap is symmetric, and so is the damage — this is not a bug in the check.**
> Run on #210 the same day, the query answers `CONTAINED-BY #209 — 2 of my 10`.
> I predicted `NO-CONTAINERS` there on the old parent/child intuition and was
> wrong: whichever member of an overlapping pair you squash first, the *other* one
> has to rebase and drop the commits whose content now sits in `main` under a
> different hash. "Which is the child" is a fact about how the branches were cut;
> "these two PRs share commits" is the fact that decides the merge strategy.
>
> #209 had been through `gh pr update-branch`, so its tip was a merge commit
> created *after* #210 branched. The tip is genuinely not an ancestor of #210 —
> and the entire content of #209 is still sitting inside #210, so a squash
> duplicates it and #210 conflicts anyway. **The tip is a pointer; the commits are
> the thing that gets duplicated.** A gate that answers about the pointer and is
> read as answering about the content is the same vacuity as the `cat-file -e`
> hole above, one level up.

> ⚠️ **The `cat-file -e` guards are the point, not decoration.** `git merge-base
> --is-ancestor` against a SHA the local repo does not have exits non-zero — which is
> **indistinguishable from "not contained"**. On a fresh checkout none of the PR heads are
> present, so without the guard this check reports `NO-CONTAINERS` for every PR in the repo
> and is perfectly vacuous. A guard that answers "clear" when it could not look is worse
> than no guard, because it is believed.

**If anything is `CONTAINED-BY`, choose deliberately — do not default:**

- **Merge commit** (`--merge`) preserves ancestry, so the child stays mergeable and
  `update-branch` resolves it cleanly.
- **Squash** is still fine *if you say so out loud*: tell the child's author before you do
  it, because they must rebase and drop the commits whose content is now duplicated in
  `main`. Landing it silently means they discover it as a conflict they did not cause.

Measured, 2026-08-14 — the case that produced this gate. #200 head `414cb977`, #210 head
`822ac8a5`, `--is-ancestor` **true**, and #210's base was `main`, so query A returned `[]`
and query B would have printed `CONTAINED-BY #210`. I squashed on A's silence; #210 went
`BLOCKED` → `DIRTY` with a real conflict in `View.kt`.

**#209 came through the same squash clean** (`FILES-IDENTICAL (21 compared)`) purely because
it shared no *files* with #200 — only commits. Do not let that near-miss read as evidence
the strategy is safe: it is the case where the bug could not bite, not the case where it
did not exist.

Then, and only then:

```bash
gh pr merge $N --repo $REPO --squash --delete-branch      # or --merge, per Gate 5
```

**Merges are serial.** Every merge moves `main`, which makes every other open PR fail
Gate 3. Merge one, re-verify the next from Gate 1. Never batch-verify then batch-merge.

---

## Opening a PR: a URL is not proof a PR was created

When an open PR already exists for the head branch, `gh pr create` creates nothing. Measured
on gh 2.97.0, 2026-08-13, against a branch that already had PR #186:

```
stdout = (empty)
stderr = a pull request for branch "PROJ-196-merge-discipline" into branch "main" already exists:
         https://github.com/your-org/your-repo/pull/186
exit   = 1
```

So it does warn — **and the warning is destroyed by the two shapes agents actually write**:

```bash
gh pr create ... 2>&1 | tail -1     # prints the URL; pipeline exit=0. The failure is gone.
URL=$(gh pr create ... 2>&1)        # URL is the OTHER PR's; rc is discarded by the assignment.
```

A pipe reports its last stage, so `| tail -1` turns exit 1 into exit 0 and hands you a URL
that looks exactly like success. That is incident 1: branch names on this board are derived
from ticket keys, so two agents on one ticket collide by construction, and the collision
arrives disguised as a created PR.

Do not parse `gh pr create`'s output at all. Check its exit code un-piped, then find the PR
by **head branch** and compare head SHAs — an assertion that holds whatever gh printed:

```bash
BRANCH=$(git branch --show-current)
git push -u origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)

gh pr create --repo $REPO --base main --title "..." --body-file /tmp/body.md
rc=$?; [ "$rc" -eq 0 ] || echo "gh pr create exit=$rc — READ THE MESSAGE, a PR may already exist"

N=$(gh pr list --repo $REPO --state open --head "$BRANCH" --json number --jq '.[].number')
PR_HEAD=$(gh api repos/$REPO/pulls/$N --jq .head.sha)
[ "$PR_HEAD" = "$LOCAL" ] \
  && echo "PR #$N head == local $LOCAL" \
  || { echo "REFUSE: PR #$N head is $PR_HEAD, my commit is $LOCAL — this is somebody else's PR"; }
```

On mismatch: **do not push over it and do not merge it.** Someone else's work is on that
branch. Cut a new branch name (`<KEY>-<what>-2`), push, and open a fresh PR — then say in
the body which PR it supersedes so the abandoned one gets closed rather than merged later.

Before pushing, `bash scripts/dod-check.sh <your-body-file>` must exit 0. `dod` is a required
status; finding out from CI costs a round trip and an extra run in the rollup.

## Files you must not merge past without the owner

A PR that **modifies** one of these changes what a gate means. Creating one for the first
time is fine; widening a live one is not, and "my PR went red so I widened the allowlist" is
the failure these exist to stop.

**Read the list, do not remember it.** The authority is the read-only table in
[`docs/AGENT-GUARDRAILS.md`](../../../docs/AGENT-GUARDRAILS.md); a copy of it here would go
stale the first time a gate is added, and a stale allowlist is confidently wrong rather than
merely absent.

```bash
# This repo's read-only table — the SECTION, not a grep for table rows: that doc holds a
# second table (the settings.json deny list) that a row-shaped grep also catches, and the
# two answer different questions.
#
# The bounds check is the point. A bare `sed -n '/a/,/b/p'` exits 0 whether it printed the
# table, printed nothing because a heading was renamed, or ran away to EOF because the end
# anchor moved. "No files are protected" then reads exactly like success.
#
# Assert that BOTH anchors matched, and that a table is present. No row or line counts:
# a threshold nobody measured is exactly what this skill refuses elsewhere, and an earlier
# draft of this block invented `>= 5 rows` in the file that argues against invented numbers.
# The start anchor matching makes the block non-empty; the end anchor matching makes the
# block's LAST line the terminator — a runaway to EOF ends on the file's last line instead.
T=$(sed -n '/^\*\*Treat these files as read-only/,/^\*\*Why each/p' docs/AGENT-GUARDRAILS.md)
if [ -n "$T" ] \
   && printf '%s\n' "$T" | tail -1 | grep -q '^\*\*Why each' \
   && printf '%s\n' "$T" | grep -q '^| `'
then printf '%s\n' "$T"
else echo "REFUSE: the read-only table's anchors no longer match — the doc moved; go read it"; fi

gh api repos/$REPO/pulls/$N/files --jq '.[].filename'   # what this PR touches
```

As of 2026-08-13 that table names, among others,
`api/gateway/internal/policy/policy.go` (authz — adding a row is an authz decision, and it is
lease-controlled) · `.claude/settings.json` (the file that governs what an agent may do
unattended) · `coverage-floors.txt` · `skip-allowlist.txt` · the route/client exemption and
`intentionally-unset` lists · `scripts/mutants/kill-list.tsv` (deleting a mutant deletes the
finding). **Treat that sentence as a hint about the shape, never as the list** — anything that
configures a gate qualifies whether or not it is written above.

Escalate those to your team channel with the ticket key rather than merging.

## After merging

Record the SHA that actually landed, not the one you meant to land:

```bash
gh api repos/$REPO/pulls/$N --jq '"head=\(.head.sha) merge_commit=\(.merge_commit_sha) merged=\(.merged)"'
```

Apply your tracker's close-out flow: comment what shipped (PR number, **head SHA**, merge commit, what was
proven, and explicitly what was **not** proven), then transition to Done. **"Merged" is not
"done."** This board has already closed a story against code that could never have worked,
and closed three more against a report of five merges that was true of four.

Release the story lease: `scripts/story-lease.sh release <SS-xxx>`.
