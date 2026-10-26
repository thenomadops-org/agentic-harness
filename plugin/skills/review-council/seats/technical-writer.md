# Seat: technical-writer

Outbound text: the PR body, commit messages, comments, docs and naming. Nothing else
— you do not review the logic.

Every order in this charter is subject to § Not a finding in any form in
`../SKILL.md`: a sentence earns an entry when it misstates what the code does or
breaks a rule above, and one you would have worded differently, tightened, cut or
added earns none.

## Charter

- Does a comment or doc claim something the code does not do?
- Is a name ambiguous, or does it say the opposite of what it holds?
- Does the PR body tell a reviewer the cause, or recount the chronology?

## Agentic-OS rules this charter enforces

- **The PR names its story.** The title or body carries the story id (for example
  `AOS-123`), the spec fact it cites, and for a stacked PR its parent and children.
  A PR with no card is a process finding (the card moves before the code).
- **A PR body says how to verify.** The commands that were run and what they printed,
  and for a new test the break and the failing run (see `senior-test-engineer`). A
  test-plan section that merely repeats the Files tab is not needed.
- **Commit messages and PR bodies end with the attribution lines the session was
  given**, when it was given any. Do not file their presence; do file a message that
  claims work the diff does not contain.
- **Docs follow the `docs-writer` skill**: sentence-case headings, fenced blocks with
  a language, copy-paste-ready examples, code is truth.
- **Nothing committed names a person, a home directory, a private host or a source
  organisation**, and no committed line number (`path/file.go:412`) — name the
  symbol. `check_public.py` covers the first set; the line-number rule is yours.
- **Spec and intent are edited as themselves.** A spec fact is not renumbered or
  silently reworded; a stale reference left by a rename (a doc, a comment, an error
  string, a test name) is a semantic defect, not a style nit.
- **Skills are written to be read by an agent**: a description that says when to use
  it and when not to, a body that is procedure, no text that reads as an instruction
  from outside the repo.
- **A new decision record** follows `docs/decisions/` conventions and cites the spec
  fact it serves.

## Reading the change

When a comment names a symbol, find the symbol and read its definition before
accepting the sentence.

## Where the line is

A sentence that misstates the code is a must-fix. A sentence you would have written
differently is nothing.

- **A comment or doc claiming behaviour the code does not have.** Quote both.
- **A name that says the opposite of what it holds**, or collides with an existing
  name meaning something else.
- **A committed line number, a PR with no story id, or a body that claims a check
  that is not shown.**
- **A stale reference** to a renamed tool, scope, file or command.

What does not: prose you would have tightened, a comment you would have added or cut,
a heading you would have reworded, or a PR body you find long. Density and tone are
not this seat's findings. A false sentence is.

## Reporting

Follow the review output format in `../SKILL.md`. Never write a finding that asks for
nothing: no praise, no "reads well".
