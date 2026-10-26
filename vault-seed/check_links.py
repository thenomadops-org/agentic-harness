#!/usr/bin/env python3
"""Every `[[wikilink]]` resolves to a note that exists. Stdlib only.

Obsidian resolves links by **basename**, not path, so this does too — which
means a link is fine if any note anywhere in the vault has that name.

Run: python3 check_links.py
Exit code is non-zero when a link is broken, so it is usable as a gate.
"""

import os
import re
import sys

VAULT = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {".git", ".obsidian", "__pycache__", ".trash", "node_modules", ".venv"}
# Templates are copied, not read. Their links are placeholders — `[[{{thing}}]]`
# is the instruction, not a broken reference.
SKIP_TREES = ("Templates",)

LINK = re.compile(r"\[\[([^\]]+)\]\]")
# Links inside code fences or backticks are examples, not references.
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)


def notes():
    found = {}
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".md"):
                found.setdefault(name[:-3], os.path.relpath(
                    os.path.join(root, name), VAULT))
    return found


def target(raw):
    """`[[Page#Heading|Alias]]` -> `Page`. An empty result is a bare anchor."""
    return raw.split("|")[0].split("#")[0].strip().rstrip("\\").strip()


def main():
    known = notes()
    broken, total = [], 0

    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            relative = os.path.relpath(path, VAULT)
            if relative.startswith(SKIP_TREES):
                continue
            with open(path, encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
            blanked = CODE.sub(lambda m: " " * len(m.group(0)), text)
            for line_number, line in enumerate(blanked.splitlines(), 1):
                for match in LINK.finditer(line):
                    name_only = target(match.group(1))
                    if not name_only:
                        continue          # [[#heading]] — same-note anchor
                    total += 1
                    if name_only not in known:
                        broken.append(f"{relative}:{line_number}  [[{name_only}]]")

    print(f"notes {len(known)} · wikilinks {total} · broken {len(broken)}")
    if broken:
        for entry in broken[:40]:
            print(f"  {entry}")
        if len(broken) > 40:
            print(f"  … and {len(broken) - 40} more")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
