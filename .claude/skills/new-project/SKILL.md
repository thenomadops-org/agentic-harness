---
name: new-project
description: Start a new repository with the day-10 engineering floor already in place — the story contract, the DoD gate, the prove-by-breaking discipline, a CI shape that pins its runners, and the deploy-and-prove pattern. Use when creating a new repo, when bootstrapping a project that has no CI yet, or when someone says "I'd be starting from ground zero". Interview first, install in dependency order, then prove the gates landed by breaking one.
---

# Start warm

A new repo does not start at zero. It starts with the floor that the last project
paid for in outages — but only if that floor is installed **before the first
feature PR**, and only if every gate is watched to fail once on the way in.

This skill installs `seed/tier0/` (the files next to this one) into a repository.

---

## The load-bearing distinction — read this before anything else

**A skill instructs. A gate executes.**

The instructions in this file live in `~/.claude/skills/`. A GitHub runner has no
home directory of yours in it, so nothing here can ever run in CI. The gates
therefore get **copied into the repo**, where CI executes them from
`scripts/`. That is not a style choice; it is checkable:

```
$ grep -ho 'scripts/[a-z0-9-]*\.sh' .github/workflows/*.yml | sort -u | wc -l   # one-project
21
$ grep -l '\.claude/skills' .github/workflows/*.yml || echo NONE
NONE
```

A guard living in a home directory runs only when an agent chooses to run it,
which makes it advice. `story-lease.sh` is documented as local and advisory and
explicitly never a CI merge gate for exactly this reason: a runner's empty `$HOME`
would make it pass vacuously, and a check that cannot fail is indistinguishable
from one that passed.

So never move a gate into a skill, and never turn an instruction into a script.

### The one instruction that still gets copied into the repo — and why

`merge-pr` is vendored into `.claude/skills/merge-pr/` of every repo this skill
seeds. It is an instruction, not a gate: CI never runs it, and nothing above
changes.

It is copied because of a ruling by Chris on **2026-08-13**. There were two
`merge-pr` skills — one repo-local, one vault-global — and within hours of both
existing they had drifted, with a defect fixed in each copy separately. The
ruling was **one skill, kept in the repo**, "in case we have to get a new local
system": a repo-local skill travels with the checkout and takes precedence over a
global one, so merge discipline can never be missing from a machine that has the
code.

The consequence Chris accepted is that a repo-local skill **does not reach a new
repo** — which is precisely the ground-zero problem this seed exists to solve. So
this install is the thing that closes it. That is also why the file goes in
`.factory/MANIFEST`: `factory-provenance-check.sh` then fails on the next PR if
somebody deletes it, which makes the mitigation enforced rather than remembered.

The copy in a seeded repo is a fork the moment it lands. Improving a
repo-agnostic mechanism in one repo's copy without improving
`seed/tier0/.claude/skills/merge-pr/SKILL.md` recreates exactly the divergence
that got the duplicate deleted. Both files say so in their own headers.

---

## Step 1 — interview, then install. Not the other way round.

A scaffolder that guesses these produces a repo full of gates nobody believes,
and a gate nobody believes is deleted the first week it is inconvenient. Ask:

1. **Ticket prefix(es).** The uppercase tracker keys that authorise work here
   (`ACME`, `OPS`). Goes to `.factory/ticket-prefixes`.
2. **Runner label sets.** Which machines CI may schedule on — the exact, *pinned*
   sets. `ubuntu-24.04`, not `ubuntu-latest`. Goes to `.factory/allowed-runners`.
3. **Language and test command**, including its cache-defeating flag. Every
   language has a stale-result trap; find this one's now, while somebody is
   thinking about it. **The answer also prunes `.factory/test-vocabulary.conf`**
   — delete the languages this repo does not use. A pattern for a language
   nobody writes here is not harmless: it is a line a future reader will believe
   was measured.
4. **Deploy target.** None / a PaaS / Kubernetes. Decides whether Tier 2 applies.
5. **Will more than one agent ever work this repo at once?** Decides Tier 3.

If the answer to 4 or 5 is "not yet", **install Tier 0 only and say so.**
Installing a restore drill in a repo with no database teaches the team that seed
files are ignorable, and that lesson generalises to the files that matter.

### Never invent a threshold

Coverage floors, latency budgets, size limits: ship them **unpinned** and let the
first real measurement pin them. A number nobody measured tells you nothing about
a number that was, and it gets waived within a week either way — after which the
gate is decoration that still shows up green.

---

## Step 2 — install, in dependency order

**The order is the point.** The contract and its checker land *before* the first
feature PR. A contract retrofitted onto a repo with history gets negotiated with
("we'll adopt it going forward"); a contract installed on an empty repo is simply
how things are done here. Every extra day you wait costs you that.

```bash
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
SEED="$HOME/.claude/skills/new-project/seed/tier0"

# The stamp. Vendoring is a fork the moment it lands, so record what came from
# where. The vault commit is the seed's revision until factory is its own repo.
SEED_SHA="$(git -C "$HOME/Code/Obsidian" rev-parse --short HEAD)"

mkdir -p "$REPO/scripts" "$REPO/docs/intent/triage" "$REPO/.github/workflows" \
         "$REPO/.factory" "$REPO/.claude/skills/merge-pr" "$REPO/.claude/hooks" \
         "$REPO/.claude/rules" "$REPO/evals/tasks/core" "$REPO/evals/tasks/local"

cp "$SEED"/scripts/*.sh                         "$REPO/scripts/"
cp "$SEED"/docs/*.md                            "$REPO/docs/"
cp "$SEED"/docs/intent/*.md                     "$REPO/docs/intent/"
cp "$SEED"/docs/intent/triage/*.md              "$REPO/docs/intent/triage/"
cp "$SEED"/.github/pull_request_template.md     "$REPO/.github/"
cp "$SEED"/.github/workflows/*.yml              "$REPO/.github/workflows/"
cp "$SEED"/.factory/README.md                   "$REPO/.factory/"
cp "$SEED"/.factory/test-vocabulary.conf        "$REPO/.factory/"   # the ONE copied config; step 1.3 prunes it
cp "$SEED"/.claude/skills/merge-pr/SKILL.md     "$REPO/.claude/skills/merge-pr/"
cp "$SEED"/.claude/rules/*.md                   "$REPO/.claude/rules/"
cp "$SEED"/.claude/hooks/*                      "$REPO/.claude/hooks/"
cp "$SEED"/.claude/settings.json                "$REPO/.claude/"
cp "$SEED"/.claude/settings.README.md           "$REPO/.claude/"
cp "$SEED"/evals/run.sh "$SEED"/evals/lib.sh "$SEED"/evals/README.md "$REPO/evals/"
cp "$SEED"/evals/tasks/core/*.eval.sh           "$REPO/evals/tasks/core/"
cp "$SEED"/evals/tasks/local/README.md          "$REPO/evals/tasks/local/"

# The agent config itself. It is a .template in the seed so that it cannot load
# with its placeholders still in it — an unfilled CLAUDE.md is worse than none,
# because an agent reads `<the test command>` as an instruction and improvises.
cp "$SEED"/CLAUDE.md.template                   "$REPO/CLAUDE.md"

chmod +x "$REPO"/scripts/*.sh "$REPO"/evals/run.sh "$REPO"/.claude/hooks/*.sh

# Stamp provenance and the runner placeholder. Both are checked; see step 4.
#
# `1,5s` is a RANGE, not a whole-file substitution, and it is load-bearing. A
# provenance header is near the top by contract; the same placeholder string also
# appears deeper inside a regression suite, as the fixture for "the install
# forgot to stamp". A whole-file sed rewrites that fixture, and the case goes on
# passing while testing nothing. That happened on the first real install of this
# seed — green in the seed directory, wrong in the repo.
cd "$REPO"
grep -rl 'factory-seed@UNSTAMPED' scripts docs .github .factory .claude \
  | xargs sed -i "1,5s/factory-seed@UNSTAMPED/factory-seed@$SEED_SHA/g"
grep -rl '__RUNNER__' .github/workflows \
  | xargs sed -i 's/__RUNNER__/<the runner set from the interview>/g'

# Record what was vendored.
#
# NOTE the omissions, both deliberate. `.factory/test-vocabulary.conf` is config
# and is meant to be pruned per repo, so it is not stamped and not manifested —
# but its absence is not silent either: the hook that reads it BLOCKS when it is
# missing. And `CLAUDE.md` is manifested but will be rewritten immediately; the
# manifest entry is there so its DELETION is loud, not to freeze its content.
{
  for f in scripts/*.sh docs/*.md docs/intent/*.md docs/intent/triage/*.md \
           .github/pull_request_template.md .github/workflows/*.yml \
           .factory/README.md .claude/skills/merge-pr/SKILL.md \
           .claude/rules/*.md .claude/settings.README.md \
           .claude/hooks/*.sh .claude/hooks/*.py .claude/hooks/README.md \
           evals/run.sh evals/lib.sh evals/README.md \
           evals/tasks/core/*.eval.sh evals/tasks/local/README.md \
           CLAUDE.md; do
    printf '%s  %s\n' "$SEED_SHA" "$f"
  done
} > .factory/MANIFEST

# Config, from the interview answers. NEVER copied from another repo.
printf 'ACME\n'        > .factory/ticket-prefixes    # step 1.1
printf 'ubuntu-24.04\n' > .factory/allowed-runners   # step 1.2
```

`__RUNNER__` in the two workflow files must be replaced with the real runs-on
value — a scalar (`ubuntu-24.04`) or an inline sequence (`[self-hosted, Linux,
X64]`). **If you forget, both the workflow fails to schedule and
`runner-pinning-check` goes red**, because `__RUNNER__` is not in
`.factory/allowed-runners`. That is deliberate: an install step that can be
skipped silently will be skipped.

### Then wire branch protection — the install does nothing until you do

Two required status checks on `main`, and only two:

- **`summary`** — the aggregate in `ci-summary.yml`. Every gating job goes in its
  `needs:` list. A job missing from `needs:` is a job whose failure does not
  block a merge.
- **`dod`** — the PR-body contract. It cannot be folded into `summary` because it
  must fire on `pull_request: types: [edited]`, and re-running every gate each
  time somebody fixes a typo in a description is how a check gets asked for and
  then removed.

Branch protection is not in the diff, so **it is the wiring line of your own
install PR.** Say so there.

---

## Step 3 — say out loud what is enforced and what is not

`docs/AGENT-GUARDRAILS.md` ships with a table splitting machine-enforced rules
from written-down ones. Fill it in honestly for this repo and keep it current.

The row that will be wrong first is the one Tier 0 cannot cover:

> **Every workflow that should have run, ran** — *nothing yet. Written down only.*

`needs:` sees only jobs in its own file. A workflow whose trigger was deleted,
whose `paths:` filter was typo'd, or which does not parse at all is in **no**
graph — GitHub answers an unparseable workflow by failing the run instantly with
zero jobs, no log, and the workflow's registered name replaced by its own file
path. On one project that meant a service published nothing for a day and the stale
image would have been applied by the next deploy as current. Absence reads as
fine to every dashboard there is. Closing it needs the expectation half of
`ci-gate.sh` — Tier 1, not yet extracted. Until then, do not let anyone believe
`summary` answers that question.

---

## Step 4 — prove the seed landed, by the seed's own discipline

A gate installed but never fired is decoration. Do all four, in order:

**a. Everything is green on the empty repo.**

```bash
bash scripts/gate-test-lib.test.sh
bash scripts/dod-check.test.sh
bash scripts/runner-pinning-check.test.sh
bash scripts/factory-provenance-check.test.sh
bash scripts/runner-pinning-check.sh
bash scripts/factory-provenance-check.sh
bash .claude/hooks/test-all.sh          # every hook suite; ZERO suites is an error
bash evals/run.sh                       # the config evals, live phase AND break phase
```

Record the exit codes. A pipe reports the last stage, so check `$?` per command.

`evals/run.sh` is the one to read the output of rather than just the code. It
prints a subject count per task, and **every one of them must be non-zero** — the
runner errors on a zero, but reading the numbers is how you notice that a check
found one subject where you expected twenty.

**b. Break each one and watch it go red.**

**Commit the install first.** On a fresh repo the seed files are untracked, so
`git checkout -- <file>` restores nothing — it fails, or with a stray `|| true`
does nothing at all, and your "green" run is measuring the still-broken file. I
hit this on the first real install of this seed. `git add -A && git commit` first,
then break.

```bash
git add -A && git commit -q -m "install seed tier0"

# 1. runner pinning
sed -i 's/^\(\s*runs-on:\).*/\1 self-hosted/' .github/workflows/ci-summary.yml
grep -n 'runs-on' .github/workflows/ci-summary.yml    # CONFIRM THE EDIT LANDED
bash scripts/runner-pinning-check.sh; echo "EXIT=$?"  # want RUNNER-PINNING, EXIT=1
git checkout -- .github/workflows/ci-summary.yml
bash scripts/runner-pinning-check.sh; echo "EXIT=$?"  # want PASSED, EXIT=0

# 2. provenance — a deleted gate is the loudest drift and the quietest failure
rm scripts/dod-check.sh
bash scripts/factory-provenance-check.sh; echo "EXIT=$?"   # want MISSING, EXIT=1
git checkout -- scripts/dod-check.sh

# 2b. the same, for the vendored merge-pr skill. Do this one explicitly: it is the
#     only manifest entry that is an instruction rather than a gate, and the whole
#     reason it is in the manifest is so its deletion cannot be silent.
rm .claude/skills/merge-pr/SKILL.md
bash scripts/factory-provenance-check.sh; echo "EXIT=$?"   # want MISSING, EXIT=1
git checkout -- .claude/skills/merge-pr/SKILL.md

# 3. the contract checker — hollow out its wiring rule
sed -i "s|^if section_is_empty 'wiring'; then|if false; then|" scripts/dod-check.sh
grep -n '^if false; then' scripts/dod-check.sh        # CONFIRM THE EDIT LANDED
bash scripts/dod-check.test.sh; echo "EXIT=$?"        # want 2 FAIL lines, EXIT=1
git checkout -- scripts/dod-check.sh

# 4. the pre-action hook — make a missing config fail OPEN instead of blocking.
#    This is the shape that matters: a guard that cannot examine its subject and
#    waves the call through anyway is indistinguishable from one that looked.
python3 - <<'EOF'
import pathlib
p = pathlib.Path(".claude/hooks/block-test-weakening.sh"); s = p.read_text()
old = '\t[ -f "$cfg" ] || config_missing "the test vocabulary this hook reads is not there."'
assert old in s, "mutation target not found — the hook changed; re-derive it"
p.write_text(s.replace(old, '\t[ -f "$cfg" ] || hook_allow'))
print("MUTATION APPLIED")
EOF
grep -n '\[ -f "$cfg" \]' .claude/hooks/block-test-weakening.sh   # CONFIRM IT LANDED
bash .claude/hooks/block-test-weakening.test.sh; echo "EXIT=$?"   # want 4 FAIL lines, EXIT=1
git checkout -- .claude/hooks/block-test-weakening.sh
bash .claude/hooks/block-test-weakening.test.sh; echo "EXIT=$?"   # want 0 failed, EXIT=0

# 5. the evals — the runner's own vacuity guard. Defeat the discovery refusal and
#    watch a suite that examined zero tasks stop being an error.
sed -i 's/^if \[ "${#TASKS\[@\]}" -eq 0 \]; then$/if false; then/' evals/run.sh
grep -n 'if false; then' evals/run.sh                 # CONFIRM THE EDIT LANDED
bash evals/run.sh; echo "EXIT=$?"                     # want FAIL runner-refuses-an-empty-task-set, EXIT=1
git checkout -- evals/run.sh
bash evals/run.sh; echo "EXIT=$?"                     # want RESULT: PASS, EXIT=0
```

The `grep` lines are not optional. **A break-test whose edit did not apply is
indistinguishable from a guard that does not work**, and it looks exactly like
success. Verify the mutation landed before trusting red *or* green.

**c. Break the harness, and understand what you are looking at.** This is the
most important one, and the reason `gate-test-lib.test.sh` is the FIRST step in
`ci-summary.yml`:

```bash
sed -i 's/^  \[ "$GATE_FAIL" -eq 0 \]$/  true/' scripts/gate-test-lib.sh
bash scripts/gate-test-lib.test.sh; echo "EXIT=$?"    # want 4 FAIL lines, EXIT=1

# now break dod-check TOO, with the harness still neutered:
sed -i "s|^if section_is_empty 'wiring'; then|if false; then|" scripts/dod-check.sh
bash scripts/dod-check.test.sh; echo "EXIT=$?"        # EXIT=0 — GREEN, AND WRONG
git checkout -- scripts/gate-test-lib.sh scripts/dod-check.sh
```

That last run is the whole argument. With the scoreboard unable to report a
failure, a genuinely broken `dod-check.sh` reports **exit 0**. Every suite in the
repo goes green together, and nothing anywhere points at it.
`gate-test-lib.test.sh` is deliberately written *without* the harness — it counts
by hand — because a suite testing the harness with the harness would be green for
the same reason. Do not "tidy" it.

**d. Open the install PR with a body that omits the wiring section** and watch
the `dod` check go red in CI; then write the section and watch it go green. This
is the one gate whose subject is the PR itself, so its prove-by-breaking *is* the
PR.

**e. Paste every red/green pair into the install PR body**, under `## Prove it by
breaking`. The PR that installs the contract is the first PR that has to satisfy
it. If that feels circular, it is — and it is the cheapest possible end-to-end
test of the whole install.

---

## Step 5 — the first feature story

Write it to `docs/STORY-CONTRACT.md` before writing any code, including the
`Wiring required` and `Prove it by breaking` sections. If the first story skips
them, the contract is already advisory and no amount of CI will bring it back.

---

## What you have NOT installed, and must not imply you have

Tier 0 only. Say this plainly in the install PR:

- **no coverage floor** — nothing measures test coverage yet;
- **no skip detection** — a test that silently skips still reads as a pass. The
  hook refuses a change that *introduces* a skip marker; it says nothing about
  one that was already there;
- **no verification check** — `.claude/hooks/transcript-evidence.py` ships with
  its suite and **nothing calling it**, because the regex it needs is this repo's
  test command. Wiring it is a deliberate act;
- **no lease** — if more than one agent will work this repo, Tier 3 is where the
  interlock lives, and until then two agents editing the same file is a silent
  merge, not a conflict;
- **no expectation check** — a workflow that stops being triggered is invisible;
- **no deploy verification** — nothing checks that a rollout actually moved the
  running image (see the `deploy-and-prove` skill; the gate half is Tier 2);
- **no recovery evidence** — nothing has restored a backup (see `prove-recovery`).

A confident false success is the most dangerous thing an install can produce. The
whole value of the table in `AGENT-GUARDRAILS.md` is that it makes this list
impossible to forget.

---

## Companion skills

- **`write-a-gate`** — before adding gate number six. It is the standard the seed
  was held to.
- **`merge-pr`** — verify against the API, not against what the PR claims. Unlike
  the others this is **not** a global skill to reach for; step 2 installs a copy
  into the repo, and that copy is the one that loads.
- **`deploy-and-prove`** — the first time this repo ships anywhere.
- **`prove-recovery`** — the first time this repo holds data somebody would miss.
