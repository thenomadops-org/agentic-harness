<!-- from factory-seed@UNSTAMPED -->

# `.claude/hooks/` — the pre-action control layer

Everything else in this seed is post-hoc: scripts and workflows that run **after**
an agent has already acted. That is the right shape for most things. It is the
wrong shape for one failure in particular, because by the time CI sees it the
damage is invisible: a deleted assertion looks exactly like a test that always
had one fewer.

These hooks run **before** the tool call.

| Hook | Refuses | Because |
|---|---|---|
| `block-test-weakening.sh` | removing assertions from, or disabling, a test file that already exists | the test that existed before the fix, and could not be rewritten, is the proof the bug is gone |

| Helper | What it answers |
|---|---|
| `payload.py` | the PreToolUse JSON on stdin, exploded into one flat file per field |
| `lib.sh` | the shared block/allow/note plumbing every hook reports through |
| `transcript-evidence.py` | **did this session actually RUN the thing the report claims it ran?** |

---

## Installing — and the thing that makes this seed different

**This is already wired.** `.claude/settings.json` ships with the `hooks` key
present and pointing at this directory. There is nothing to paste.

That sounds like a detail and it is the most valuable structural decision in this
directory, so it is worth the paragraph. `.claude/settings.json` carries
`Edit(**/.claude/settings.json)` in `permissions.deny`, and that deny rule is
**correct**: settings.json is gate config, and an agent that can edit it can
disable every control in the repo including the one denying the edit. The
consequence is that **a hooks layer cannot install itself.** On the project this
came from, three finished, tested, correct hooks sat inert in the tree waiting on
an owner to paste eight lines, and every tool call in the meantime went
unchecked.

A seeded repo must never reach that state. So the key is present from the first
commit and adding a hook later is a change to a file the owner already owns,
rather than a permission problem discovered at the worst moment.

**If you add a hook to this directory, its command must be added to
`.claude/settings.json` by a human.** That is the deny rule working, not a bug.
Say so in your PR's wiring section — `scripts/dod-check.sh` will ask.

## The four invariants every hook here obeys

A hook that fails open is a guard that examined nothing, which is the signature
defect this whole seed is built against. So:

- **Blocking is exit 2**, and nothing else blocks. stderr is what the model is
  shown. Every other exit code lets the call through — including `127`, which is
  what a typo'd command name produces, which is why a hook must never be able to
  fail before it has parsed its input.
- **Cannot-check REFUSES.** An unparseable payload, a missing `python3`, a
  config file that will not source: all block, loudly, with a reason. **"Could
  not look" must never print the same as "looked and found nothing."**
- **Not-configured ALLOWS** — and must never print the same as broken. A repo
  whose files match no test pattern simply does not have that control, and every
  write passes silently. This is the opposite outcome from *broken*, on purpose.
  The two are distinguished per hook and the distinction is written down in the
  hook's own header, because it is the one judgment a reader cannot re-derive.
- **Every block states a route to approval**, not just a refusal. A refusal with
  no next step gets the hook deleted, and a deleted hook is a control you now
  believe you have.

## What is configured, and where

`block-test-weakening.sh` reads its entire vocabulary — what counts as a test
file, what counts as an assertion, what counts as disabling a test, and which
ticket keys open the bypass — from **`.factory/test-vocabulary.conf`**.

**Prune that file at install** to the languages this repo actually uses. It ships
covering Go, Kotlin/JVM, Swift, JS/TS, Python and shell, because a vocabulary
shipped empty makes the hook match nothing and a hook that matches nothing prints
the same reassuring answer as one that looked. A pattern for a language nobody
writes here is not harmless: it is a line a future reader will believe was
measured.

It is gate config, so it is on the read-only list in
[`../../docs/AGENT-GUARDRAILS.md`](../../docs/AGENT-GUARDRAILS.md). Widening the
test-path patterns or narrowing the assertion vocabulary makes the hook quieter
without anybody deciding to make it quieter.

## The escape, and why it is not a hole

| Variable | Opens | Must name |
|---|---|---|
| `ALLOW_TEST_WEAKENING` | removing or disabling a test that is genuinely obsolete | a ticket key matching `TICKET_RE` in the config — anything else is not a bypass |

It is deliberately *accountable* rather than silent: the hook allows the call and
tells the model, in the same breath, what it now owes the PR body. A bypass
nobody has to account for is just a disabled hook.

## The helper with no caller

`transcript-evidence.py` ships with **nothing in this seed calling it**, and that
is deliberate rather than an oversight.

It answers the question that separates a verified report from a confident one:
*a PR body says the suite ran — did it?* The implementation people reach for
first is `grep 'go test' transcript.jsonl`, and that is **vacuous in the exact
shape it exists to catch**: the PR body is composed inside the session, so the
body is IN the transcript, so the grep finds the claim and reports it as the
evidence for itself. It would pass 100% of the time. The `CARRIER` exclusion in
that file — dropping `gh pr`, `git commit`, and the heredoc writers before
matching — is the whole thing. Keep it, and keep the comment explaining it.

What the seed cannot supply is the regex: it is *this repo's* test command, which
the interview asks about and the seed does not know. So it ships as a tool with
its own suite, and wiring it into a hook is a deliberate act with a real
question behind it. See `transcript-evidence.test.sh` for how to call it and what
the three exit codes mean.

> One pattern, two engines. If you wire it beside a `grep -E` using the same
> string, keep the pattern **POSIX ERE**. Python's `re` reads `[[:space:]]` as a
> nested set and matches something else entirely; `posix_to_python()` translates
> it and **raises** on a class it does not know, rather than passing a pattern
> through that would quietly match the wrong thing.

## Testing

```bash
.claude/hooks/test-all.sh            # every suite; zero suites is an ERROR
.claude/hooks/block-test-weakening.test.sh
.claude/hooks/transcript-evidence.test.sh
```

Every suite is built around MUST-BLOCK cases: for every shape a hook must refuse
there is an assertion that it exits 2, and for every shape it must leave alone
there is an assertion that it exits 0. A change that makes a hook permissive
turns the first group red; one that makes it over-broad turns the second red.
Neither can pass by accident.

**Wire these into CI.** `.github/workflows/ci-summary.yml` runs `test-all.sh` as
part of the `gates` job. A self-test nobody runs is a self-test that has been
green since the day somebody broke it.

## No `printf … | grep -q` in here

Piping a writer into `grep -q` / `head -N` under `pipefail` is a race: the
writer's SIGPIPE on the consumer's early exit can flip the pipeline's status even
when the pattern **is** present. These hooks run `set -uo pipefail` and turn
every such test into an allow/deny decision, so that race would be a hook failing
open **nondeterministically** — the exact defect they exist to prevent. Everything
here uses a herestring (`grep -qE pat <<<"$var"`). Keep new ones out.

## What they deliberately do not catch

Each hook's header lists its own blind spots in full. The short version for
`block-test-weakening.sh`:

- An assertion rewritten to be trivially true while the count stays the same.
- Weakening the code under test rather than the test.
- Any file outside the configured test vocabulary.
- A Bash path relative to a `cd`-ed directory (`cd sub && rm pkg/x_test.go`).
  Stated rather than papered over: parsing `cd` out of an arbitrary compound
  command is a rabbit hole, and a hook that guessed would be worse than one that
  says where it stops.
- Whether the tests **passed**. It checks that they were not removed. Nothing
  more.
