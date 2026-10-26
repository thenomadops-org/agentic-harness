#!/usr/bin/env python3
"""Dry run for /split-stories: check work cards, print the create_story calls.

    python3 check_cards.py [--repo DIR] [--spec SPEC.md] CARDS.json

CARDS.json is a list of {title, priority, spec_ref, scope, body, ...}. Scope
entries must be exact files: a glob reserves its whole literal prefix at
dispatch (board memory scope-globs-reserve-their-whole-prefix). With --repo an
entry that exists must be a file, not a directory. With --spec the cited fact
must exist and its slug must match, as the board checks. Exit 0, 1, 2.
"""
import argparse
import json
import pathlib
import re
import sys
import unicodedata

GLOB_CHARS = set("*?[]{}")
REF = re.compile(r"^projects/[^/]+/spec/[a-z0-9-]+\.md#f([1-9][0-9]*)-(.+)$")
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


def scope_errors(entry, repo=None):
    if not isinstance(entry, str) or not entry.strip():
        return ["empty entry"]
    if GLOB_CHARS & set(entry):
        return [f"{entry!r} is a glob; list exact files"]
    if entry.endswith("/") or entry in (".", ""):
        return [f"{entry!r} is a directory; list exact files"]
    if entry.startswith("/") or "\\" in entry or ".." in entry.split("/"):
        return [f"{entry!r} must be a path inside the repository"]
    if repo is not None and (pathlib.Path(repo) / entry).is_dir():
        return [f"{entry!r} is a directory; list exact files"]
    return []


def check(cards, repo=None, spec_text=None):
    errs = []
    if not isinstance(cards, list) or not cards:
        return ["cards: must be a non-empty list"]
    facts = {}
    if spec_text is not None:
        for line in spec_text.split("\n"):
            m = FACT.match(line.strip())
            if m:
                facts.setdefault(int(m.group(1)), m.group(2).strip())
    owner = {}
    titles = [c.get("title") for c in cards if isinstance(c, dict)]
    for i, c in enumerate(cards, 1):
        label = f"card {i}"
        if not isinstance(c, dict):
            errs.append(f"{label}: must be an object")
            continue
        if not str(c.get("title", "")).strip():
            errs.append(f"{label}: title required")
        if c.get("kind", "work") != "work":
            errs.append(f"{label}: kind must be work")
        if not isinstance(c.get("priority"), int):
            errs.append(f"{label}: priority must be an integer")
        m = REF.match(c.get("spec_ref") or "")
        if not m:
            errs.append(f"{label}: spec_ref must be projects/<project>/spec/<page>.md#f<N>-<slug>")
        elif spec_text is not None:
            n = int(m.group(1))
            if n not in facts:
                errs.append(f"{label}: spec fact {n} not found in the spec")
            elif slug(facts[n]) != m.group(2):
                errs.append(f"{label}: fact {n} is {slug(facts[n])!r}, not {m.group(2)!r}")
        scope = c.get("scope")
        if not isinstance(scope, list) or not scope:
            errs.append(f"{label}: scope must list exact files (empty means the whole repository)")
            continue
        for e in scope:
            errs += [f"{label}: scope {x}" for x in scope_errors(e, repo)]
        deps = set(c.get("depends_on") or [])
        for e in scope:
            if isinstance(e, str):
                j = owner.setdefault(e, i)
                prior = cards[j - 1]
                if j != i and prior.get("title") not in deps:
                    errs.append(f"card {i}: shares {e!r} with card {j} and does not depend on it; they cannot run in parallel")
    return errs


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("cards")
    ap.add_argument("--repo")
    ap.add_argument("--spec")
    a = ap.parse_args(argv)
    for f in (a.cards, a.spec):
        if f and not pathlib.Path(f).is_file():
            print(f"missing input: {f}", file=sys.stderr)
            return 2
    try:
        cards = json.loads(pathlib.Path(a.cards).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: cards is not JSON: {e}")
        return 1
    spec = pathlib.Path(a.spec).read_text(encoding="utf-8") if a.spec else None
    errs = check(cards, a.repo, spec)
    if errs:
        print("\n".join(f"FAIL: {e}" for e in errs))
        return 1
    print(json.dumps([{"tool": "create_story", "args": {"kind": "work", **c}} for c in cards], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
