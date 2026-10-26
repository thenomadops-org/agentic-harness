#!/usr/bin/env python3
"""Did this session actually RUN the thing the PR body says it ran?

from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's
seed/tier0. Improve it upstream too, or this copy is a fork.

WHY THIS IS NOT A GREP.

The obvious implementation — `grep 'go test' transcript.jsonl` — is vacuous, and
vacuous in a way that is easy to miss. The PR body
being checked is ITSELF in the transcript, because the agent composed it there.
So a naive grep finds the claim and reports it as the evidence for the claim. It
would pass 100% of the time, including the runs it exists to catch.

So this walks the JSONL properly and looks only at what was actually EXECUTED:
`tool_use` blocks for the Bash tool, and their `input.command`. It then throws
away the commands that merely CARRY prose — `gh pr create/edit/comment`, `git
commit`, and heredoc writers like `cat > body.md` — because those contain the
claim text and would reintroduce the same circularity one layer down.

Usage:  transcript-evidence.py <transcript.jsonl> <extended-regex>
Exit:   0 = a real invocation matching the regex was found (printed to stdout)
        1 = the transcript is readable and contains no such invocation
        2 = the transcript could not be read at all

1 and 2 are DIFFERENT ON PURPOSE, and the caller must treat them differently:
"looked and found nothing" is a finding, "could not look" is an environment
fault. Collapsing the two is how a repo ends up with a skip-allowlist: on one
project thirty-five tests skipped themselves on an unset environment variable
and every job stayed green, because "did not run" and "passed" printed the same.

WIRING. Nothing in the seed calls this yet, and that is deliberate rather than an
oversight: the regex it is handed is the repo's own test command, which the seed
cannot know. See `.claude/hooks/README.md`, "The helper with no caller".
"""

import json
import re
import sys

# Commands that transport prose rather than run tests. A match inside one of
# these is the claim, never the evidence for it.
CARRIER = re.compile(
    r"""^\s*(
          gh\s+(pr|issue|release)\b
        | git\s+(commit|notes|tag)\b
        | (cat|echo|printf|tee|head|sed|grep|rg|awk)\b
        | [A-Za-z_][A-Za-z0-9_]*=\S*\s+gh\b
    )""",
    re.VERBOSE,
)
BODY_FLAG = re.compile(r"--body(-file)?\b|--notes(-file)?\b")

# The caller passes a POSIX ERE, because the same string is also handed to
# `grep -E` in assert-toolchain-present.sh — one pattern, two engines. Python's
# `re` does NOT understand `[[:space:]]`; it reads it as a nested set, emits a
# FutureWarning, and then matches something else entirely. Left untranslated the
# evidence lookup silently found nothing and every claim was refused, which is
# fail-CLOSED and therefore survivable — but it is still a check examining the
# wrong thing, so it is translated rather than tolerated.
POSIX_CLASSES = {
    "alnum": "0-9A-Za-z",
    "alpha": "A-Za-z",
    "blank": " \\t",
    "digit": "0-9",
    "lower": "a-z",
    "space": " \\t\\n\\r\\f\\v",
    "upper": "A-Z",
    "word": "0-9A-Za-z_",
    "xdigit": "0-9A-Fa-f",
}
_POSIX = re.compile(r"\[:([a-z]+):\]")


def posix_to_python(pattern):
    """Rewrite POSIX bracket classes into their Python equivalents.

    Raises ValueError on a class this does not know, rather than passing a
    pattern through that would match the wrong thing quietly.
    """

    def sub(match):
        name = match.group(1)
        if name not in POSIX_CLASSES:
            raise ValueError("unknown POSIX class [:%s:]" % name)
        return POSIX_CLASSES[name]

    out = _POSIX.sub(sub, pattern)
    if "[:" in out:
        raise ValueError("unconverted POSIX class remains in %r" % out)
    return out


def commands(path):
    """Yield every Bash tool_use command recorded in the transcript."""
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            message = rec.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                if block.get("name") != "Bash":
                    continue
                data = block.get("input")
                if not isinstance(data, dict):
                    continue
                cmd = data.get("command")
                if isinstance(cmd, str) and cmd.strip():
                    yield cmd


def main():
    if len(sys.argv) != 3:
        sys.stderr.write("usage: transcript-evidence.py <transcript.jsonl> <regex>\n")
        return 2
    path, pattern = sys.argv[1], sys.argv[2]
    try:
        needle = re.compile(posix_to_python(pattern))
    except (re.error, ValueError) as exc:
        sys.stderr.write("transcript-evidence.py: bad regex: %s\n" % exc)
        return 2
    try:
        found = None
        for cmd in commands(path):
            if CARRIER.search(cmd) or BODY_FLAG.search(cmd):
                continue
            if needle.search(cmd):
                found = cmd
                break
    except (OSError, IOError) as exc:
        sys.stderr.write("transcript-evidence.py: cannot read %s: %s\n" % (path, exc))
        return 2
    if found is None:
        return 1
    one_line = " ".join(found.split())
    if len(one_line) > 300:
        one_line = one_line[:297] + "..."
    sys.stdout.write(one_line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
