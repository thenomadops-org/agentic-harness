#!/usr/bin/env python3
"""Dry run for /spec: check numbered facts and print their anchors.

    python3 check_spec.py [--project KEY --page SLUG] FILE.md

Facts are `N. **Title.** text` at the start of a line, the form a
`#f<N>-<slug>` citation uses. The slug rule is this script's own. Exit 0,
1 (findings), 2 (missing file).
"""
import argparse
import json
import pathlib
import re
import sys
import unicodedata

HEADING = re.compile(r"^#{1,6}\s+\S")
FACT = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*")


def slug(title):
    out, dash = [], False
    for ch in title.lower():
        if unicodedata.category(ch)[0] in ("L", "N"):
            out.append(ch)
            dash = False
        elif not dash and out:
            out.append("-")
            dash = True
    return "".join(out).rstrip("-")


def section_anchor(body):
    """The `#section` a card's spec_ref uses: the first heading, as the daemon's
    hasHeading reads it (lower case, hyphens for spaces). None when unusable."""
    for line in body.split("\n"):
        if HEADING.match(line):
            text = line.lstrip("#").strip()
            anchor = text.lower().replace(" ", "-")
            if re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", anchor) and not anchor.startswith("the-"):
                return anchor
            return None
    return None


def facts(body):
    found = []
    for line in body.split("\n"):
        m = FACT.match(line.strip())
        if m:
            found.append((int(m.group(1)), m.group(2).strip()))
    return found


def check(body):
    errs, fs = [], facts(body)
    if not fs:
        return ["body: no numbered facts (`N. **Title.** text`)"], fs
    if section_anchor(body) is None:
        errs.append("body: the first heading must be plain words (letters, digits, spaces; not starting with 'The') so a card can cite it")
    seen = set()
    for i, (n, title) in enumerate(fs, 1):
        if n != i:
            errs.append(f"fact {n}: expected number {i}; numbers run 1, 2, 3 with no gap or reuse")
        if not slug(title):
            errs.append(f"fact {n}: title has no letters or digits")
        elif slug(title) in seen:
            errs.append(f"fact {n}: title {title!r} repeats another fact's slug")
        seen.add(slug(title))
    return errs, fs


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--project", default="")
    ap.add_argument("--page", default="")
    a = ap.parse_args(argv)
    p = pathlib.Path(a.file)
    if not p.is_file():
        print(f"missing input: {p}", file=sys.stderr)
        return 2
    body = p.read_text(encoding="utf-8")
    errs, fs = check(body)
    if errs:
        print("\n".join(f"FAIL: {e}" for e in errs))
        return 1
    for n, t in fs:
        print(f"#f{n}-{slug(t)}")
    if a.project and a.page:
        print(json.dumps([
            {"tool": "write_project_page", "args": {"project": a.project, "kind": "spec", "page": a.page}},
            {"tool": "create_story", "args": {"project": a.project, "kind": "spec", "spec_ref": f"projects/{a.project}/spec/{a.page}.md#f1-{slug(fs[0][1])}"}},
        ], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
