#!/usr/bin/env python3
"""PreToolUse hook: the publication-boundary check gates every commit and push
(portable-workforce spec F8, first bullet).

Claude Code passes the tool call as JSON on stdin. This hook acts only on a
Bash command that runs `git commit` or `git push`, in a repository that
declares itself publishable. Exit 2 blocks the call and sends stderr to the
agent; exit 0 allows it.

A repository declares itself publishable by having `.public-boundary.yaml` at
its root. That file is what tools/check_public.py reads, so the declaration and
the rule are one file. A repository without it is private and is not gated.

A publishable repository must carry `tools/check_public.py`. If the declaration
is there and the check is not, the hook blocks: a boundary nobody can run is not
a boundary. The check runs with its exit status read directly and its output
sent to stderr; it is never put through a pipe, because a pipe reports the
exit status of the last command and would turn a failed check into a pass.

    commit  ->  python3 tools/check_public.py --staged
    push    ->  python3 tools/check_public.py        (the whole tree)
"""
import json
import os
import re
import shlex
import subprocess
import sys

DECLARATION = ".public-boundary.yaml"
CHECK = os.path.join("tools", "check_public.py")
PREFIX_WORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "time", "sudo", "env", "command", "exec", "nice"}
GIT_OPTS_WITH_ARG = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


def git_invocations(command):
    """Yield (subcommand, directory-override) for each `git <sub>` in a command line."""
    for segment in re.split(r"&&|\|\||;|\||\n|\(|\)|`|\$\(", command):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        i = 0
        # The command word: skip shell keywords, wrappers and VAR=value prefixes.
        while i < len(words) and (words[i] in PREFIX_WORDS or re.match(r"[A-Za-z_][A-Za-z0-9_]*=", words[i])):
            i += 1
        if i >= len(words) or os.path.basename(words[i]) != "git":
            continue
        i += 1
        chdir = None
        while i < len(words) and words[i].startswith("-"):
            opt = words[i]
            if opt == "-C" and i + 1 < len(words):
                chdir = words[i + 1]
            if opt in GIT_OPTS_WITH_ARG:
                i += 1
            i += 1
        if i < len(words):
            yield words[i], chdir


def repo_root(start):
    here = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def decide(command, cwd):
    """Return (blocked, message)."""
    for sub, chdir in git_invocations(command):
        if sub not in ("commit", "push"):
            continue
        where = os.path.join(cwd, chdir) if chdir else cwd
        root = repo_root(where)
        if root is None or not os.path.exists(os.path.join(root, DECLARATION)):
            continue
        script = os.path.join(root, CHECK)
        if not os.path.exists(script):
            return True, (f"BLOCKED: {root} declares itself publishable ({DECLARATION}) "
                          f"but has no {CHECK}. A boundary that cannot be run is not enforced.")
        args = [sys.executable, script] + (["--staged"] if sub == "commit" else [])
        result = subprocess.run(args, cwd=root, stdout=sys.stderr, stderr=sys.stderr)
        if result.returncode != 0:
            return True, (f"BLOCKED: the publication-boundary check failed "
                          f"(exit {result.returncode}) before git {sub}. Fix the hits above; "
                          "do not bypass this hook.")
    return False, ""


def main():
    try:
        call = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0  # not a tool call we understand; the hook gates nothing it cannot read
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
