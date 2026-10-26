#!/usr/bin/env python3
"""Fail if this repository contains anything that should not be published.

Agentic-OS is the template other people fork. The vault it generates is private
forever; **this repo is written on the assumption that it is not.**

That assumption is worth enforcing rather than remembering, because the leak
path here is not a careless commit — it is a useful one. The portable skills and
the seed memory atoms are exactly the material worth shipping, and in their
original form they are full of the incidents that made them worth writing:
ticket ids, PR numbers, cluster names, dates. Scrubbing those is a step someone
will skip once.

Reads `.public-boundary.yaml`. Exit code is non-zero on a hit, so it is usable
as a gate.

    python3 tools/check_public.py
    python3 tools/check_public.py --staged     # only what is about to commit
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import miniyaml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, ".public-boundary.yaml")
# An org's own names live outside the published file: a git-ignored local
# overlay, or a file named by PUBLIC_BOUNDARY_EXTRA. Both are optional and
# merged into the published boundary.
LOCAL = os.path.join(ROOT, ".public-boundary.local.yaml")

TEXT_SUFFIXES = {
    ".md", ".py", ".yaml", ".yml", ".json", ".tmpl", ".txt", ".sh", ".toml",
    ".cfg", ".ini", ".gitignore", "",
}


def load_config():
    if not os.path.exists(CONFIG):
        print(f"error: {CONFIG} missing — the boundary is undefined, so this",
              file=sys.stderr)
        print("       check cannot pass. Create it before publishing.",
              file=sys.stderr)
        raise SystemExit(2)
    config = miniyaml.load(CONFIG)
    extras = [LOCAL, os.environ.get("PUBLIC_BOUNDARY_EXTRA", "")]
    for extra in extras:
        if extra and os.path.exists(extra):
            more = miniyaml.load(extra) or {}
            for key in ("deny", "always_deny", "allow", "skip_dirs"):
                config[key] = list(config.get(key) or []) + list(more.get(key) or [])
    patterns = []
    for entry in config.get("deny") or []:
        patterns.append(("deny", re.compile(str(entry), re.IGNORECASE)))
    for entry in config.get("always_deny") or []:
        patterns.append(("always", re.compile(str(entry))))
    if not patterns:
        print("error: no patterns defined; an empty boundary is not a boundary",
              file=sys.stderr)
        raise SystemExit(2)
    return (
        patterns,
        [str(a) for a in (config.get("allow") or [])],
        set(str(d) for d in (config.get("skip_dirs") or [])),
        # The file that DECLARES the forbidden names necessarily contains them,
        # and so does the checker that documents its own purpose. Skipping by
        # path rather than by line content, because a line-content exception
        # would have to name every forbidden string and become a second copy.
        {os.path.abspath(CONFIG), os.path.abspath(LOCAL), os.path.abspath(__file__)},
    )


def candidate_files(skip_dirs, staged_only):
    if staged_only:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=ROOT, capture_output=True, text=True)
        names = [n for n in result.stdout.splitlines() if n.strip()]
        return [os.path.join(ROOT, n) for n in names if os.path.exists(
            os.path.join(ROOT, n))]

    found = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            found.append(os.path.join(root, name))
    return found


def scan(path, patterns, allow):
    suffix = os.path.splitext(path)[1].lower()
    if suffix not in TEXT_SUFFIXES:
        return []
    try:
        with open(path, encoding="utf-8", errors="strict") as handle:
            lines = handle.read().splitlines()
    except (UnicodeDecodeError, OSError):
        return []          # binary or unreadable: nothing to read means nothing to leak

    hits = []
    for number, line in enumerate(lines, 1):
        if any(token in line for token in allow):
            continue
        for kind, pattern in patterns:
            match = pattern.search(line)
            if match:
                shown = line.strip()
                if len(shown) > 100:
                    shown = shown[:97] + "…"
                hits.append((number, kind, match.group(0), shown))
                break
    return hits


def main(argv):
    staged_only = "--staged" in argv
    patterns, allow, skip_dirs, skip_files = load_config()

    total, files_hit = 0, 0
    for path in sorted(candidate_files(skip_dirs, staged_only)):
        if os.path.abspath(path) in skip_files:
            continue
        hits = scan(path, patterns, allow)
        if not hits:
            continue
        files_hit += 1
        relative = os.path.relpath(path, ROOT)
        print(f"\n{relative}")
        for number, kind, found, line in hits[:10]:
            label = "SECRET/PII" if kind == "always" else "private name"
            print(f"  {number:>5}  [{label}] {found!r}")
            print(f"         {line}")
        if len(hits) > 10:
            print(f"         … and {len(hits) - 10} more in this file")
        total += len(hits)

    scope = "staged changes" if staged_only else "the working tree"
    print()
    if total:
        print(f"BOUNDARY FAILED — {total} hit(s) in {files_hit} file(s) in {scope}")
        print()
        print("This repo is written to be publishable. Either generalise the")
        print("reference (describe the shape, not the org), or add a narrow")
        print("exception to `allow` in .public-boundary.yaml and say why.")
        return 1
    print(f"BOUNDARY CLEAN — nothing private found in {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
