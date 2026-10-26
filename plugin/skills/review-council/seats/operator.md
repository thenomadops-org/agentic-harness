# Seat: operator

> The daemon (`tools/markdown-backend`), the node client, and the iPad app (`apps/ipad`) were removed in OPS-333. Apply this charter to what remains: `plugin/`, `tools/*.py`, `adapters/`, and `docs/`. Recoverable from tag `pre-harness-rewrite` (`c114b2e`).

Day-2 operations. Could somebody on call at 3am read this, and is the configuration
safe to get wrong? Nothing else.

## Charter

- Runbooks, configuration schemas, container and install files, environment
  variables, workflows.
- A failure whose message does not say what to do about it.
- A default that is unsafe, or a knob with no stated blast radius.

## Agentic-OS rules this charter enforces

- **The daemon image must be able to do its job.** It shells out to `git` and `ssh`;
  an image that builds but lacks them starts cleanly and fails every write. A change
  to `tools/markdown-backend/Dockerfile` keeps the CI step that proves the image can
  reach git, and keeps it able to fail.
- **Install and update paths verify before they trust.** `tools/markdown-backend/cmd/aos/packaging/install-aos.sh`-style
  scripts check a checksum, check the fast-forward, refuse a port in use and do not
  run the service as a fixed account. Removing one of those checks is the finding,
  and each has a "break test" step in `.github/workflows/gate.yml` that should still be there.
- **Hosting is documented where it is configured.** A new environment variable,
  flag or secret path appears in `tools/markdown-backend/HOSTING.md` or the node
  setup doc in the same change, with what happens when it is wrong.
- **Credentials are read from local configuration, never baked in.** No token or
  private endpoint in an image layer, a workflow, an example or a default.
- **CI runs on the organisation's runner variable**, with no hosted fallback; a
  workflow change that reintroduces a hardcoded hosted runner is the finding.
- **Stdlib-only Python.** A script that needs a package to install is unsafe to ship
  to a clean machine.

## Where the line is

The 3am question is answered against the diff: for each failure path the change
adds, does the message name what failed and what to set or restart? For each new
knob, does the diff say what happens when it is wrong? A finding quotes the message
or default from the diff and the consequence of getting it wrong. "Could be
clearer" is not this seat's finding, and neither is a log line's wording where the
operator's next step is already in it.

## Reading the change

When a PR edits an operational surface, search the docs and workflows for the thing
it changed and say whether they moved.

## Reporting

Follow the review output format in `../SKILL.md`. A knob or default that is unsafe
and undocumented is a Critical Issue (`failure`); a missing doc line is a `warning`.
