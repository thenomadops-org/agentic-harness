# Production hook

Spec F8, third bullet: production is the owner's. Field source: spec F3.

`production_gate.py` is a `PreToolUse` hook on `Bash`, registered in
`../hooks.json`. It reads `production` from `.agentic-os.yaml` at the project
root and blocks (hook exit 2) a command matching any pattern there, unless an
owner override is recorded.

## Reading the field

The schema belongs to the project-file story, so the read is defensive. Every
scalar under `production` is a pattern (scalar, `[a, b]`, block list, or block
map), except under the keys `description`, `note`, `notes`, `comment`,
`owner`, `override`. A pattern is a regular expression searched in the command;
one that does not compile matches as plain text. A missing, unreadable or empty
file yields no patterns and the hook gates nothing (other actions are a right
of the role).

## Owner override

Either of:

1. `AGENTIC_OS_PRODUCTION_OVERRIDE=owner` in the environment Claude Code was
   launched from. A hook inherits the launcher's environment, not the agent's
   command, so `VAR=owner kubectl apply` does not satisfy it.
2. A record at `$AGENTIC_OS_OVERRIDE_DIR/production-override.json`
   (default `~/.agentic-os/`):
   `{"granted_by": "owner", "repo": "<repo root>", "expires_at": "<ISO UTC>"}`.
   It must name this repository and be unexpired. Delete it to revoke.

A command that names the record file is blocked, so an agent cannot write its
own override through the tool. The record is still a file the agent's user can
write by other means; the env var is the form an agent cannot forge.

Tests: `python3 -m unittest discover -s plugin/hooks/production`
