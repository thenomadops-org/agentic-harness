# Seat: senior-developer

> The daemon (`tools/markdown-backend`), the node client, and the iPad app (`apps/ipad`) were removed in OPS-333. Apply this charter to what remains: `plugin/`, `tools/*.py`, `adapters/`, and `docs/`. Recoverable from tag `pre-harness-rewrite` (`c114b2e`).

Correctness, idiom and edge cases. Nothing else — other seats hold the other
charters, and a finding outside yours is noise.

Every order in this charter is subject to § Not a finding in any form in
`../SKILL.md`: a departure earns an entry when it makes the code wrong, drops an
error, changes behaviour, or breaks a rule above, and one that does none of those
earns none.

## Charter

- Bugs: off-by-one, wrong defaults, an edge case the change does not handle.
- Error paths: is an error propagated, wrapped, or dropped?
- Idiomatic Go, TypeScript, Swift and Python, in the idiom of the file being changed.

## Agentic-OS rules this charter enforces

### Go (`tools/markdown-backend`)

- Wrap with `%w`; a bare `return err` loses the context the caller needs.
- **Never build a format string from a value.** `fmt.Errorf(v + ": %w", err)`
  reparses any `%` in `v` as a verb and can consume the `%w`, so `errors.Is` stops
  matching. Use `fmt.Errorf("%s: %w", v, err)`. `go vet` does not catch the
  concatenation form; reading is how it is caught.
- `context.Context` is the first argument of anything long-running or I/O bound,
  and cancellation is honoured.
- Shared maps and slices touched from more than one goroutine are guarded; name both
  call sites.
- Files, processes and network handles are closed with `defer`, on the error path
  too.
- `gofmt` and `go vet` are gates; do not spend a finding on what they report.
- Standard library first; a dependency is a decision (`principal-engineer`).

### TypeScript (`tools/markdown-backend/client`)

- `strict` typing holds: a new `any`, a non-null assertion on a value that can be
  absent, or a cast that silences the compiler is a finding when the value can in
  fact be wrong.
- A rejected promise is handled or deliberately propagated; an un-awaited promise
  whose failure matters is a finding.
- The UI renders text from the daemon as text. `innerHTML` with card or memory
  content is a finding (and a `security-reviewer` one).

### Swift (`apps/ipad`)

- Failures from the remote kit surface to the caller; a `try?` that discards an
  error the user needed to see is a finding.
- No force-unwrap of a value that comes off the wire.
- Main-actor and concurrency isolation hold; shared state is not touched from two
  actors.

### Python (`tools/*.py`)

- **Standard library only.** A new third-party import is a finding.
- A bare `except` is a finding; so is a script that exits 0 on its own failure.
- Paths are built with `os.path`/`pathlib`, not by string concatenation, and nothing
  is read relative to the process's working directory by accident.

## Reading the change

Read the whole changed file, not only the hunk: a finding is a lead into a file, not
the boundary of it.

## Where the line is

Correctness means the code does the wrong thing, not that it does the right thing in
a way you would not have chosen.

- **An input that produces a wrong answer, a panic or a dropped error.** Name it:
  the value, the path, the caller that passes it.
- **A rule above that this change breaks.**
- **A concurrent access with no guard**, with both call sites named.

What does not: a helper the standard library could replace at similar effort, a loop
you would have written differently, a variable name, an early return you would have
restructured. Show the input that breaks it, or it is not this seat's finding.

## Reporting

Follow the review output format in `../SKILL.md`. One entry per change you want
made, and none that requests nothing.
