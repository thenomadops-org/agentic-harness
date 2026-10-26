#!/usr/bin/env python3
"""Explode a Claude Code PreToolUse hook payload into flat files.

from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's
seed/tier0. Improve it upstream too, or this copy is a fork.

WHY THIS EXISTS AS ONE READER RATHER THAN ONE PER HOOK.

The hooks in this directory all need the same handful of fields out of the
same JSON blob on stdin, and every one of those fields can contain newlines, `$`,
backticks and unbalanced quotes (it is source code and shell commands). Parsing
that in shell is how a guard ends up examining nothing: an eval'd assignment on a
diff containing `$(rm -rf ...)` is a bug, and a `grep`-based field extractor
silently returns the empty string on any shape it did not anticipate — which every
one of these hooks would then read as "nothing to check, allow".

So: read the payload ONCE, write each field to its own file under a temp dir, and
let the shell hooks work with `cat`. A missing field yields an EMPTY file, never a
missing one, so a hook can never confuse "absent" with "unreadable" — and
`fields_present` records which keys the payload actually carried, so a hook that
needs to tell those apart can.

The fields written (all UTF-8, no trailing newline added):

  tool_name        e.g. Edit, Write, MultiEdit, NotebookEdit, Bash
  cwd              the session's working directory
  transcript_path  path to this session's JSONL transcript ("" if absent)
  file_path        tool_input.file_path ("" for Bash)
  command          tool_input.command ("" for non-Bash)
  old_text         every tool_input.old_string, plus every edits[].old_string,
                   joined by newlines. Empty for Write (which has no old side —
                   its hook reads the file from disk instead).
  new_text         every tool_input.new_string, plus every edits[].new_string,
                   plus tool_input.content and tool_input.new_source, joined by
                   newlines. This is the union of the "text being introduced"
                   across Edit / MultiEdit / Write / NotebookEdit.
  fields_present   newline-separated list of the tool_input keys that were
                   actually present, for hooks that must distinguish an empty
                   value from an absent one.

Usage:  payload.py <outdir>      (JSON on stdin; exit 0 = written, 2 = unusable)

Exit 2 is deliberate and means BLOCK: a payload this cannot parse is a payload
none of the hooks can check, and a check that cannot examine its input must
refuse rather than wave the action through.
"""

import json
import os
import sys


def _flatten(value):
    """Collect string leaves from a str, a list, or a dict's values."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_flatten(item))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_flatten(item))
        return out
    return []


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: payload.py <outdir>\n")
        return 2
    outdir = sys.argv[1]
    try:
        os.makedirs(outdir, exist_ok=True)
    except OSError as exc:
        sys.stderr.write("payload.py: cannot create %s: %s\n" % (outdir, exc))
        return 2

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError) as exc:
        sys.stderr.write(
            "payload.py: the hook payload on stdin is not JSON (%s). "
            "Refusing to let the tool call through, because no hook in "
            ".claude/hooks/ can inspect an unreadable payload.\n" % exc
        )
        return 2
    if not isinstance(payload, dict):
        sys.stderr.write("payload.py: hook payload is not a JSON object\n")
        return 2

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    old_parts = []
    if isinstance(tool_input.get("old_string"), str):
        old_parts.append(tool_input["old_string"])
    if isinstance(tool_input.get("old_source"), str):
        old_parts.append(tool_input["old_source"])

    new_parts = []
    for key in ("new_string", "content", "new_source"):
        if isinstance(tool_input.get(key), str):
            new_parts.append(tool_input[key])

    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            if isinstance(edit.get("old_string"), str):
                old_parts.append(edit["old_string"])
            if isinstance(edit.get("new_string"), str):
                new_parts.append(edit["new_string"])

    # NotebookEdit and any future shape: sweep cell_updates for string leaves so
    # a new payload key does not silently become an unexamined write.
    if isinstance(tool_input.get("cell_updates"), list):
        new_parts.extend(_flatten(tool_input["cell_updates"]))

    fields = {
        "tool_name": payload.get("tool_name") or "",
        "cwd": payload.get("cwd") or "",
        "transcript_path": payload.get("transcript_path") or "",
        "file_path": tool_input.get("file_path") or "",
        "command": tool_input.get("command") or "",
        "old_text": "\n".join(old_parts),
        "new_text": "\n".join(new_parts),
        "fields_present": "\n".join(sorted(str(k) for k in tool_input)),
    }

    for name, value in fields.items():
        if not isinstance(value, str):
            value = str(value)
        with open(os.path.join(outdir, name), "w", encoding="utf-8") as handle:
            handle.write(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
