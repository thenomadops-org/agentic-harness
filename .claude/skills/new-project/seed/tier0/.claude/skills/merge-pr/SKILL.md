---
name: merge-pr
description: Verify with the GitHub API that a PR contains the commit you reviewed and is genuinely green, then merge it. Use whenever merging any PR to a protected branch, and whenever opening one. Repo-agnostic — reads the repo from git, and reads gate-config paths from .factory/.
---
<!-- from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
     This marker must stay within the first 5 lines: the install stamps it with
     `sed '1,5s/...'`. Do not add frontmatter fields above it. If it does slip out
     of range the stamp silently does nothing — and factory-provenance-check then
     goes red on UNSTAMPED, which is the safe direction, not a reason to relax. -->

# Identify the commit, judge the latest checks, then merge

> **This skill is deliberately repo-local, and there is no global copy. That is
> the design, not a broken install.** Chris ruled on **2026-08-13**: one
> `merge-pr`, kept in the repo, "in case we have to get a new local system" — a
> repo-local skill travels with the checkout and takes precedence over a global
> one, so a repository always carries its own merge discipline. A vault-global
> duplicate existed for part of that day, drifted from the repo copy within
> hours, and was deleted.
>
> The accepted consequence is that a repo-local skill does not reach a **new**
> repo. What closes that is the **`new-project`** skill, which vendored this file
> here and recorded it in `.factory/MANIFEST`. It is therefore covered by
> `factory-provenance-check.sh`: delete it and the next PR goes red.
>
> **This copy is a fork the moment it lands.** Improve a mechanism that is not
> specific to this repo and you must improve the seed at
> `~/.claude/skills/new-project/seed/tier0/.claude/skills/merge-pr/SKILL.md` too,
> or the next repo starts from the older text — which is exactly the divergence
> that made the duplicate worth deleting.
>
> **Confirm which copy you are actually running before trusting any of it.** A
> session started before this file landed can still serve a *deleted* copy's text
> from its own context, headed with a path that no longer exists on disk — observed
> 2026-08-13. The disk is the authority:
>
> ```bash
> ls -la ~/.claude/skills/ | grep merge-pr || echo "no global copy — correct"
> git -C "$(git rev-parse --show-toplevel)" log -1 --format=%h -- .claude/skills/merge-pr/SKILL.md
> ```
>
> If a skill quotes you a path, `stat` it. A body of text is not evidence that its
> source still exists.

The mandate is **verify first**, against the API rather than against what a branch
name, a PR body, or a returned URL claims.

Three questions, in this order. Skipping the first is how a repo ships work
nobody read.

1. **Is the code in this PR the code I reviewed?** (head SHA identity)
2. **Are its checks green *now*?** (latest run per name — not the raw list)
3. **Was it built against the tree it is landing into?** (base currency)

Every gate below names the incident that justifies it. A gate with no incident
behind it should be deleted, not kept for tidiness.

```bash
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
N=<pr-number>
```

## The failure modes this exists to stop

- **A branch name is not an identity.** one-project, 2026-08-13, PR #179: a killed
  agent had already pushed a branch and opened the PR. The replacement commit was
  written locally on a branch of the **same name**, was never pushed, and
  `gh pr create` returned the **existing** PR instead of creating one.
  `gh pr merge 179` then merged the abandoned work. The reviewed evidence
  described a file that never reached `main`; it took a -1940-line PR to undo.
  Nothing in the old check list would have caught it, because the old list never
  asked *which commit* it was clearing.
- **A commit's check-run list is HISTORICAL, not current.** The same day, a re-run
  `dod` was read as red at a SHA where it was green. Judge the **latest run per
  name** or you will refuse a green PR — and, worse, learn to wave the filter
  through when it "always shows that". A mandate the tool does not implement is a
  mandate the human improvises, and an operator trained to override the filter by
  eye will eventually override a genuine failure by the same reflex.
- **Branch protection usually requires only a subset of checks.** A PR with a red
  *service test* can still report `mergeable_state: clean`. Never conclude green
  from `mergeable_state` alone.
- **`strict` is usually false.** GitHub will merge a branch cut before the base
  moved. That is how that project's PR #144 merged green and left `main` red for a day:
  its CI never compiled its own changes against the tree it was landing into.
  Per-PR CI is structurally blind to this.

---

## Gate 1 — the PR head SHA must EQUAL the commit you reviewed

**Write the SHA down when you review, and compare it at merge time.** Not the
branch name, not the PR number, not "the latest commit on my branch" — the
40-character SHA you actually read a diff of. Put it in the review comment or the
ticket so the comparison is auditable by someone who was not there.

```bash
REVIEWED=<the-40-char-sha-you-reviewed>
HEAD_SHA=$(gh api repos/$REPO/pulls/$N --jq .head.sha)
[ "$HEAD_SHA" = "$REVIEWED" ] \
  && echo "SHA-MATCH $HEAD_SHA" \
  || echo "REFUSE: PR head $HEAD_SHA != reviewed $REVIEWED"
```

If they differ, **stop and re-review the head SHA.** Do not reason about why they
differ — a rebase, a fixup, a force-push and somebody else's abandoned branch all
look identical here, and only one of them is benign.

**If you authored the change, also prove your local work is what is in the PR.**

```bash
git rev-parse HEAD    # what you built and tested
git rev-parse @{u}    # what you actually pushed
gh api repos/$REPO/pulls/$N --jq .head.sha
```

All three must be the same string. `git status` saying "up to date" is not proof —
it reports the tracking ref's *last known* position, and a branch that was never
pushed has no tracking ref to be wrong about.

## Gate 2 — judge the LATEST run per NAME

Never filter the raw list. Group by name, take the newest run of each, judge only
those:

```bash
gh api "repos/$REPO/commits/$HEAD_SHA/check-runs?per_page=100" --paginate --slurp \
 | jq -r '[.[].check_runs[]] | group_by(.name) | map(sort_by(.started_at) | last)
          | map(select(.conclusion != "success" and .conclusion != "skipped"
                       and .conclusion != "neutral"))
          | map("\(.name)=\(.conclusion // .status)") | join(", ")'
```

Merge only when this prints **nothing**. Measured on one project, 2026-08-13 — both
PRs merged green, and the raw-list form calls both of them red:

```
=== PR #181  merged=true ===
  raw-list filter (broken):   dod=failure
  latest-per-name (correct):
=== PR #173  merged=true ===
  raw-list filter (broken):   dod=cancelled
  latest-per-name (correct):
```

Notes that are not optional:

- **`--slurp`, not `--jq`.** `--paginate --jq` applies the filter **per page** and
  concatenates, so `group_by` across a page boundary silently regroups nothing.
  gh refuses `--slurp` together with `--jq`, so pipe to `jq`. Under 100 checks it
  makes no difference; the day it does, it fails quietly.
- **`sort_by(.started_at) | last`, never `.[0]`.** The array order is not
  chronological.
- **An empty list of checks is not green.** If the PR reports zero checks at all,
  refuse — a check that never ran is indistinguishable from one that passed.
  Confirm with `gh api .../check-runs --jq .total_count`.
- **The aggregate check must be PRESENT and green**, not merely not-red. Path
  filters make a service's tests **absent** rather than red, and absent reads as
  fine to every dashboard there is.
- A `CANCELLED` run at the same SHA is normal when the body was edited (the
  DoD check fires on `edited`). Superseded by a later run of the same name, it is
  not a failure. Edit a PR body **at most once** so the rollup stays legible and
  so repeated edits do not start runs that cancel each other.

Read the full roster before deciding — do not just trust the empty filter:

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

If it fails: `gh pr update-branch $N`, wait for checks, then re-verify — updating
the branch changes the head SHA, so everything you concluded about the old head is
void.

**But do not literally "start again at Gate 1" — as written, Gate 1 cannot pass
here.** It compares `head.sha` to `REVIEWED`, and `update-branch` has just
guaranteed they differ. Taken at face value it says REFUSE on every updated PR; the
agent under time pressure then sets `REVIEWED=<new head>` and calls it verified,
which is the exact laundering this skill exists to stop. Re-reading the full diff is
the other trap: after the merge the diff also contains the base branch's changes, so
"re-review" balloons and gets skimmed.

**Instead, prove the update was ONLY a merge.** Two assertions. Each ends in a
comparison that prints its own verdict — if you are reading git's raw output and
deciding for yourself, you are running an older draft, and that draft had a hole.

```bash
git fetch -q origin
REVIEWED=$(git rev-parse "$REVIEWED")          # normalise; abbreviations DO resolve
NEW=$(gh api repos/$REPO/pulls/$N --jq .head.sha)

# 1. NEW is a merge of exactly {the head you reviewed, a commit already in the base}
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

> ⚠️ **Never narrow set 2 to the PR's file list alone.** That list is
> `diff(base..head)`, computed from the **new** side only, so it sees content
> arriving and is blind to your work **departing**. If the merge reverts a file back
> to base — which is what "take the base's side", the commonest bad resolution of a
> real conflict, does — the file no longer differs from base, **drops out of the
> list, and is never compared.** Both assertions pass and the skill tells you your
> review carries over. It does not.
>
> Reproduced on one project, 2026-08-13: a reviewed `auth: allow_all = false` reverted to
> `true` by the merge. PR file list `[README.md]`, the policy file absent from it,
> `PARENTS-OK`, zero `CHANGED` lines. The file this bites is whichever one several
> concurrent stories all edit — on one project that is the gateway authz policy table,
> touched by 8 of 10 domain plans. Unioning in the reviewed side's own change set
> (`git diff $MB $REVIEWED`) closes it. Content *injected* by a merge was always
> caught; only removal was invisible.
>
> The `-s "$SET"` guard is not decoration. A comparison that examined nothing has not
> passed.

Both hold ⇒ the merge introduced nothing of its own **and removed nothing of yours**,
your review carries over, and you may set `REVIEWED=$NEW` **because you proved it**.
Either fails ⇒ real content arrived or departed with the update. Re-review the head
properly before going on.

Measured, gh 2.97.0 / git 2.43.0, 2026-08-13. Replaying that project's PR #186's real
`update-branch`: `PARENTS-OK`, then `FILES-IDENTICAL (1 compared)` — the benign case
is **not** false-positived by the wider set. Against the reverted-authz repro:
`PARENTS-OK`, then `CHANGED` and `REFUSE`. Note `git rev-parse <sha>:<path>` **echoes
its own argument on stdout and exits 128** when the path does not exist at that
commit — so a file the PR adds compares unequal and reports `CHANGED`. That is the
safe direction; do not "fix" it into silence.

An abbreviated `REVIEWED` resolves fine in assertion 2 — measured, an 8-, a 12- and a
40-character form all returned the same blob — but assertion 1 is a string comparison,
so `git rev-parse` it first, which the block above does. An earlier draft claimed an
abbreviation "will never match"; that was false, and it came from reading a negative
control that had used a **wrong** SHA. Two different reasons to fail look identical in
a control that records only *that* it failed.

## Gate 4 — the rest

```bash
gh api repos/$REPO/pulls/$N --jq '"\(.mergeable) \(.mergeable_state) \(.draft) \(.base.ref)"'
gh api repos/$REPO/pulls/$N --jq .body | grep -nE 'MERGE-ORDER-HOLD|DO NOT MERGE'
```

- `mergeable=true`, `mergeable_state=clean`, `draft=false`, base is the protected
  branch.
- No `MERGE-ORDER-HOLD` / `DO NOT MERGE` in the body. Stories that must land in a
  fixed order have nothing else enforcing it.
- **It has actually been reviewed by a human or an agent that read the diff.**
  Green means the machine is happy, not that the change is correct.

## Gate 5 — does another open PR CONTAIN this one? (choose the merge strategy first)

Two different questions. Asking only the first is how a child PR ends up in conflict:

| question | what it reads | what it tells you |
|---|---|---|
| is another PR **based on** my branch? | GitHub's `base` field — metadata someone set | `--delete-branch` will silently **close** it |
| does another PR **contain** my commits? | the git graph — true whether or not anyone declared it | a **squash** will put it into **conflict** |

**Ask both. Neither implies the other.** Branches cut from each other while all pointing
at the default branch share commits and are invisible to a `--base` query.

```bash
# A. based-on — which PRs --delete-branch would close
gh pr list --repo $REPO --state open --base "$(gh api repos/$REPO/pulls/$N --jq .head.ref)"

# B. containment — which PRs a squash would break
git fetch -q origin "+refs/pull/*/head:refs/remotes/pr/*"      # fetch ALL heads first
HEAD_SHA=$(gh api repos/$REPO/pulls/$N --jq .head.sha)

contained=0
for other in $(gh pr list --repo $REPO --state open --json number --jq '.[].number'); do
  [ "$other" = "$N" ] && continue
  oh=$(gh api repos/$REPO/pulls/$other --jq .head.sha)
  if ! git cat-file -e "$oh^{commit}" 2>/dev/null; then
    echo "REFUSE: PR #$other head $oh not fetched — this check CANNOT answer, do not read its silence as 'clear'"
    contained=1; continue
  fi
  if git merge-base --is-ancestor "$HEAD_SHA" "$oh"; then
    echo "CONTAINED-BY #$other — a squash here will put #$other into conflict"
    contained=1
  fi
done
[ "$contained" -eq 0 ] && echo "NO-CONTAINERS — squash is safe"
```

> ⚠️ **The `cat-file -e` guard is the point, not decoration.** `git merge-base
> --is-ancestor` against a SHA the local repo does not have exits non-zero — which is
> **indistinguishable from "not contained"**. On a fresh checkout none of the PR heads are
> present, so without the guard this check prints `NO-CONTAINERS` for every PR in the repo
> and is perfectly vacuous. Measured in an empty repo: without the guard, "squash is safe";
> with it, `REFUSE`. A guard that answers "clear" when it could not look is worse than no
> guard, because it is believed.

**If anything is `CONTAINED-BY`, choose deliberately — do not default:**

- **Merge commit** (`--merge`) preserves ancestry, so the child stays mergeable.
- **Squash** is still fine *if you say so out loud*: tell the child's author first, because
  they must rebase and drop the commits whose content is now duplicated in the base branch.
  Landing it silently means they meet it as a conflict they did not cause.

Then, and only then:

```bash
gh pr merge $N --repo $REPO --squash --delete-branch      # or --merge, per Gate 5
```

**Merges are serial.** Every merge moves the base, which makes every other open PR
fail Gate 3. Merge one, re-verify the next from Gate 1. Never batch-verify then
batch-merge.

---

## Opening a PR: a URL is not proof a PR was created

When an open PR already exists for the head branch, `gh pr create` creates
nothing. Measured on gh 2.97.0, 2026-08-13:

```
stdout = (empty)
stderr = a pull request for branch "..." into branch "main" already exists: <url>
exit   = 1
```

So it does warn — **and the warning is destroyed by the two shapes agents actually
write**:

```bash
gh pr create ... 2>&1 | tail -1   # prints the URL; pipeline exit=0. The failure is gone.
URL=$(gh pr create ... 2>&1)      # URL is the OTHER PR's; rc discarded by the assignment.
```

A pipe reports its last stage, so `| tail -1` turns exit 1 into exit 0 and hands
you a URL that looks exactly like success. Where branch names are derived from
ticket keys, two agents on one ticket collide by construction, and the collision
arrives disguised as a created PR.

Do not parse `gh pr create`'s output at all. Check its exit code un-piped, then
find the PR by **head branch** and compare head SHAs — an assertion that holds
whatever gh printed:

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
  || echo "REFUSE: PR #$N head is $PR_HEAD, my commit is $LOCAL — this is somebody else's PR"
```

On mismatch: **do not push over it and do not merge it.** Someone else's work is
on that branch. Cut a new branch name (`<KEY>-<what>-2`), push, and open a fresh
PR — then say in the body which PR it supersedes, so the abandoned one gets closed
rather than merged later.

Before pushing, `bash scripts/dod-check.sh <your-body-file>` must exit 0. The DoD
check is a required status; finding out from CI costs a round trip and an extra
run in the rollup.

## Files you must not merge past without the owner

A PR that **modifies** one of these changes what a gate means. Creating one for
the first time is fine; widening a live one is not, and "my PR went red so I
widened the allowlist" is the failure these exist to stop.

**The list is per-repo, so read it rather than remembering it.** It is the
read-only table in `docs/AGENT-GUARDRAILS.md`, and the config it names lives in
`.factory/`:

```bash
ls .factory/                                             # this repo's gate config
gh api repos/$REPO/pulls/$N/files --jq '.[].filename'     # what this PR touches
```

Anything in `.factory/`, any coverage-floor, allowlist, exemption or
intentionally-unset file, the authz policy table, and the agent permission config
all qualify. Escalate with the ticket key rather than merging.

## After merging

Record the SHA that actually landed, not the one you meant to land:

```bash
gh api repos/$REPO/pulls/$N --jq '"head=\(.head.sha) merge_commit=\(.merge_commit_sha) merged=\(.merged)"'
```

Then comment on the ticket what shipped — PR number, **head SHA**, merge commit,
what was proven, and explicitly what was **not** proven — before transitioning it.
**"Merged" is not "done."** A board has already closed a story against code that
could never have worked, and closed three more against a report of five merges
that was true of four.
