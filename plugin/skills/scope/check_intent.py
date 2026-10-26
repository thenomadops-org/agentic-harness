#!/usr/bin/env python3
"""Dry run for /scope: validate an intent page and print the board calls.

    python3 check_intent.py --project KEY --page SLUG --title TITLE FILE.md

Exit 0 and the two payloads on stdout when valid, 1 with every finding when
not, 2 when FILE is missing. Nothing is sent to the board.
"""
import argparse
import json
import pathlib
import re
import sys

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FACT_LINE = re.compile(r"^\s*\d+\.\s+\*\*")  # `N. **Title.**` is a spec fact
HEADING = re.compile(r"^#{1,6}\s+\S")


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


def check(body, project, page, title):
    errs = []
    if not project:
        errs.append("project: required")
    if not SLUG.match(page or ""):
        errs.append("page: lowercase letters, digits and hyphens only")
    if not (title or "").strip():
        errs.append("title: required")
    lines = body.split("\n")
    if not any(HEADING.match(l) for l in lines):
        errs.append("body: needs at least one heading")
    if len(re.sub(r"^#.*$", "", body, flags=re.M).split()) < 5:
        errs.append("body: the intent is empty or only a heading")
    if section_anchor(body) is None:
        errs.append("body: the first heading must be plain words (letters, digits, spaces; not starting with 'The') so a card can cite it")
    if any(FACT_LINE.match(l) for l in lines):
        errs.append("body: numbered facts belong in the spec (/spec), not the intent")
    return errs


def payloads(body, project, page, title):
    return [
        {"tool": "write_project_page", "args": {"project": project, "kind": "intent", "page": page, "body": body}},
        {"tool": "create_story", "args": {
            "project": project, "kind": "intent", "title": title, "priority": 2,
            "spec_ref": f"projects/{project}/intent/{page}.md#{section_anchor(body)}", "body": f"Intent card for the {page} intent page."}},
    ]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--project", default="")
    ap.add_argument("--page", default="")
    ap.add_argument("--title", default="")
    a = ap.parse_args(argv)
    p = pathlib.Path(a.file)
    if not p.is_file():
        print(f"missing input: {p}", file=sys.stderr)
        return 2
    body = p.read_text(encoding="utf-8")
    errs = check(body, a.project, a.page, a.title)
    if errs:
        print("\n".join(f"FAIL: {e}" for e in errs))
        return 1
    print(json.dumps(payloads(body, a.project, a.page, a.title), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
