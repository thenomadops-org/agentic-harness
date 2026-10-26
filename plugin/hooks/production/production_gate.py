#!/usr/bin/env python3
"""PreToolUse hook: production is the owner's (portable-workforce spec F8,
third bullet; the field is spec F3's `production`).

Reads `production` from `.agentic-os.yaml` at the project's repository root and
blocks a Bash command that matches any pattern there, unless an owner override
is recorded. Exit 2 blocks; exit 0 allows.

Reading the file is defensive, because the schema belongs to the project-file
story. `production` may be a scalar, a flow list `[a, b]`, a block list, or a
block map; every scalar found under it is a pattern, except under keys named
in NON_PATTERN_KEYS. A pattern is a regular expression searched in the
command; one that does not compile is matched as plain text. A missing,
unreadable or empty file yields no patterns, so the hook gates nothing: other
actions are a right of the role (spec F8 closing line).

Owner override, either of:
  1. env AGENTIC_OS_PRODUCTION_OVERRIDE=owner, set in the environment Claude
     Code was launched from. A hook inherits the launcher's environment, not the
     agent's command, so `VAR=owner kubectl apply` does not satisfy it.
  2. a record at <override dir>/production-override.json, where the override
     dir is $AGENTIC_OS_OVERRIDE_DIR or ~/.agentic-os, shaped
     {"granted_by": "owner", "repo": "<repo root>", "expires_at": "<ISO UTC>"}.
     It must name this repository and be unexpired.
Limit, stated plainly: the record is a file the agent's own user can write.
The hook therefore also blocks any command that names the record, but a
determined same-user agent is outside what a hook can stop; the owner's
protection there is the env var, and revoking the record by deleting it.
"""
import datetime
import json
import os
import re
import sys

OVERRIDE_ENV = "AGENTIC_OS_PRODUCTION_OVERRIDE"
OVERRIDE_FILE = "production-override.json"
PROJECT_FILE = ".agentic-os.yaml"
NON_PATTERN_KEYS = {"description", "note", "notes", "comment", "owner", "override"}


def repo_root(start):
    here = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(here, PROJECT_FILE)) or os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


def strip_comment(s):
    return re.sub(r"\s+#.*$", "", s)


def read_patterns(text):
    """The literal command patterns under `production.commands` (spec F3, the
    shape published in plugin/skills/onboard-project/SCHEMA.md). Only that
    list gates; other keys under `production` (e.g. same_environment_as_staging)
    are never patterns. Read without a YAML library."""
    out, in_prod, in_cmds, cmds_indent = [], False, False, -1
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        body = strip_comment(raw.strip())
        if indent == 0:
            if in_prod:
                break
            in_prod = re.match(r"production\s*:", body) is not None
            continue
        if not in_prod:
            continue
        if in_cmds and indent <= cmds_indent and not body.startswith("- "):
            in_cmds = False
        m = re.match(r"commands\s*:\s*(.*)$", body)
        if m and not in_cmds:
            in_cmds, cmds_indent = True, indent
            if m.group(1).strip():
                out.extend(scalars(m.group(1)))
            continue
        if in_cmds and body.startswith("- "):
            out.extend(scalars(body[2:]))
    return [p for p in out if p]


def scalars(value):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return [unquote(v) for v in value[1:-1].split(",") if v.strip()]
    return [unquote(value)]


def matches(pattern, command):
    # Literal, case-insensitive substring (SCHEMA.md): never a regex. The tools
    # guarded (gh, fastlane) resolve names without regard to case (AOS-347).
    return pattern.casefold() in command.casefold()


def override_dir():
    return os.environ.get("AGENTIC_OS_OVERRIDE_DIR") or os.path.join(os.path.expanduser("~"), ".agentic-os")


def override_recorded(root, now=None):
    if os.environ.get(OVERRIDE_ENV) == "owner":
        return True
    try:
        with open(os.path.join(override_dir(), OVERRIDE_FILE), encoding="utf-8") as fh:
            rec = json.load(fh)
        expires = datetime.datetime.fromisoformat(str(rec["expires_at"]).replace("Z", "+00:00"))
        now = now or datetime.datetime.now(datetime.timezone.utc)
        return (rec.get("granted_by") == "owner"
                and os.path.realpath(rec.get("repo", "")) == os.path.realpath(root)
                and expires > now)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def decide(command, cwd):
    if OVERRIDE_FILE in command:
        return True, f"BLOCKED: a command may not read or write the owner override record ({OVERRIDE_FILE}). The owner records it."
    root = repo_root(cwd)
    if root is None:
        return False, ""
    try:
        with open(os.path.join(root, PROJECT_FILE), encoding="utf-8") as fh:
            patterns = read_patterns(fh.read())
    except (OSError, UnicodeDecodeError):
        return False, ""
    hit = next((p for p in patterns if matches(p, command)), None)
    if hit is None or override_recorded(root):
        return False, ""
    return True, (f"BLOCKED: this command matches the production pattern {hit!r} in {PROJECT_FILE}. "
                  "Production is the owner's. Stop and ask the owner; do not retry another route.")


def main():
    try:
        call = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if call.get("tool_name") != "Bash":
        return 0
    command = (call.get("tool_input") or {}).get("command") or ""
    blocked, message = decide(command, call.get("cwd") or os.getcwd())
    if blocked:
        print(message, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
