# Boundary hook

Spec F8, first bullet: the publication-boundary check gates every commit and
push in a publishable repository.

`boundary_gate.py` is a `PreToolUse` hook on `Bash`, registered in
`../hooks.json`. It acts on `git commit` and `git push` (through option flags,
`-C`, `&&` chains, `if ...; then` and `VAR=x` prefixes) and runs:

| git command | check |
|---|---|
| `commit` | `python3 tools/check_public.py --staged` |
| `push` | `python3 tools/check_public.py` (the whole tree) |

A non-zero exit blocks the call (hook exit 2) and the check's output reaches
the agent. The check's exit status is read directly and its output goes to
stderr. It is never put through a pipe: a pipe reports the last command's
status, so a failed check would read as a pass.

## Declaring a repository publishable

Put `.public-boundary.yaml` at the repository root. That is the file
`tools/check_public.py` reads, so the declaration and the rule are the same
file. A repository without it is private and is not gated.

A repository that declares itself publishable must also carry
`tools/check_public.py`. If the declaration is present and the check is not,
the hook blocks: a boundary nobody can run is not a boundary.

## Limits

- The repository is found from the hook's `cwd` (or `git -C`). A
  `cd other-repo && git commit` is checked against the starting repository.
- The builder-never-verifies-own-work law is not a hook. The board enforces it
  (`sign_off` and review refusals, extended to F9 verification records), and
  this plugin adds nothing to it.

Tests: `python3 -m unittest discover -s plugin/hooks/boundary`
