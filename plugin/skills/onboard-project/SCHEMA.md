# `.agentic-os.yaml`

The project file (portable-workforce spec F3). It sits at a repository root.
`validate.py` in this directory is the executable form of this page; a file
that breaks any rule below fails it, and so does a key not listed here.

```yaml
board_project: Demo                  # the board project key, no spaces
roles: [engineer, qa]                # roles the project needs; lowercase slugs, no duplicates
test: make test                      # must pass before a hand-off
build: make build                    # builds the project
staging:
  deploy: how a merge to main deploys staging, in words, honestly
  url: https://staging.example.com   # http(s) URL, or env:NAME for a private one
  check: how to prove the deploy took, a command or a comparison
production:
  commands:                          # what the production hook (F8) blocks
    - kubectl apply
  same_environment_as_staging: false # true when staging and production are one
```

All six top-level keys are required. Every string is non-empty.

## `production`, the shape the production hook reads

- `production.commands` is a non-empty list of non-empty strings, no
  duplicates. Each string is a literal, case-insensitive substring. A shell
  command that contains any of them is a production command and is blocked
  without an owner override. There are no globs and no regular expressions:
  write `kubectl apply`, not `kubectl * apply`.
- `production.same_environment_as_staging` is `true` or `false`, never absent.
  When `true`, the commands that move staging are the commands listed, so the
  guard is the same one.

## `staging.url`

A private endpoint must not be written into a publishable repository. Write
`env:NAME` instead, where `NAME` is an upper-case environment variable that
holds the URL on the machines that need it.

## Reader limits

The file is read by the stdlib subset reader `miniyaml.py`, a vendored copy of
`tools/miniyaml.py`. It refuses anchors, block scalars (`|`, `>`), nested flow
collections and duplicate keys, and it takes an apostrophe in an unquoted value
for a quote. Wrap such a value in double quotes.

## `docs/memory/` entries

Defined in `docs/memory/README.md` of the project (spec F4) and checked by
`python3 validate.py memory docs/memory`.
