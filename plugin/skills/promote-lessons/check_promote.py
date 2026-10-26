#!/usr/bin/env python3
"""Dry run for /promote-lessons: is this change set a lessons-only promotion?

    git diff --name-only origin/main | python3 check_promote.py [--root DIR]
    python3 check_promote.py [--root DIR] path ...

Every changed path must be a file directly under plugin/lessons/ (README.md is
the index and may change), no path may use `..`, and each existing lesson file
is scanned for private names. Exit 0, 1 with findings, 2 when no path is given.
"""
import argparse
import pathlib
import re
import sys

LESSONS = "plugin/lessons/"
PRIVATE = re.compile(r"\.ts\.net|Bearer\s+\S|/home/[a-z]+|\b(?:10|192\.168)\.\d+\.\d+(?:\.\d+)?\b|@gmail\.com")


def check(paths, root=None):
    errs = []
    if not paths:
        return ["no changed paths: nothing to promote"]
    for p in paths:
        parts = p.split("/")
        if p.startswith("/") or ".." in parts:
            errs.append(f"{p}: not a repository path")
        elif not p.startswith(LESSONS) or "/" in p[len(LESSONS):] or not p.endswith(".md"):
            errs.append(f"{p}: a promotion may only add or change files directly under {LESSONS}")
        elif root is not None and (pathlib.Path(root) / p).is_file():
            if PRIVATE.search((pathlib.Path(root) / p).read_text(encoding="utf-8")):
                errs.append(f"{p}: names a private host, address, token or home path")
    return errs


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--root")
    a = ap.parse_args(argv)
    paths = a.paths or ([] if sys.stdin.isatty() else [l.strip() for l in sys.stdin if l.strip()])
    if not paths:
        print("missing input: no changed paths", file=sys.stderr)
        return 2
    errs = check(paths, a.root)
    for e in errs:
        print("FAIL:", e)
    if not errs:
        print(f"promotion ok: {len(paths)} file(s) under {LESSONS}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
