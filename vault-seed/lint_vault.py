#!/usr/bin/env python3
"""The vault's gate — one command, and it can actually fail. Stdlib only.

Every agent is told to run this after writing to the vault. It exists because
the vault has zones with different rules, and the expensive failures are the
ones where a rule from one zone gets applied to another.

## The checks, and what each is really guarding

1.  **link integrity** — delegated to `check_links.py`.
2.  **duplicate note names** — runs FIRST. Obsidian resolves `[[links]]` by
    basename, so two notes with one name resolve unpredictably. Every check
    after this reads a basename-keyed map, so a duplicate corrupts their input
    before they see it.
3.  **orphans** — a page nothing links to. `check_links` proves a link reaches
    a page; only this proves a page is reachable. A correct page nothing points
    at will never be retrieved, which is worse than a missing one because you
    believe the ground is covered.
4.  **generated files** — `Team-ORG.md` and `*-Role.md` are rendered from
    `roles.yaml`. A hand-edit here is reverted by the next `org update`, and
    until then two files describe the same person differently.
5.  **untouched Souls** — the inverse. A Soul still carrying its generated
    callout after real work means nobody took ownership of that identity.
6.  **memory scope** — a client-specific fact filed in `_shared/` pollutes
    every other engagement.
7.  **journal metrics** — an entry without PRs and tokens is a diary. The
    numbers are the point.
8.  **brief length** — capped deliberately. A brief that grows to fill the
    space stops being read, and an unread brief is worse than none because it
    looks like reporting happened.
9.  **skills in the vault** — a skill in `~/.claude/skills/` that is not a
    symlink into this vault is untracked, unsynced, and invisible to history.
10. **frontmatter** — a note without it cannot be found by the properties that
    make retrieval work.

Run: python3 lint_vault.py
Exit code is non-zero if anything fails.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

VAULT = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {".git", ".obsidian", "__pycache__", ".trash", "node_modules",
             ".venv", ".scratch"}

LINK = re.compile(r"\[\[([^\]]+)\]\]")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
BULLET = re.compile(r"^\s*[-*+]\s+\S")

# A page in these trees is not expected to have an inbound link. Journals are
# append-only and nobody links each one; templates are copied, not referenced.
ORPHAN_EXEMPT = ("Sessions", "Templates", ".claude")
ORPHAN_EXEMPT_NAMES = {"Home", "README", "MEMORY", "index"}

GENERATED_MANIFEST = os.path.join(VAULT, ".claude", "generated.json")
SOUL_MARKER = "This is a starting point, not a finished person"
BRIEF_BULLET_CAP = 20

# Words that make a memory atom client-specific. Present in a `_shared` atom,
# they are a strong signal it was filed in the wrong scope.
CLIENT_SIGNALS = re.compile(
    r"\b(cluster|namespace|deploy(?:ment)?s?\b|tower\d|prod(?:uction)?\b|"
    r"board|sprint|ticket|epic|repo(?:sitory)?\b|bucket|database|"
    r"[A-Z]{2,6}-\d+)\b", re.IGNORECASE)

failures = []


def fail(check, detail=()):
    failures.append(check)
    print(f"  FAIL  {check}")
    for line in detail:
        print(f"          {line}")


def ok(check, detail=""):
    print(f"  ok    {check}" + (f"  — {detail}" if detail else ""))


def parse_frontmatter(text):
    """A deliberately shallow reader: top-level `key: value` only."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    data = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.startswith((" ", "-", "\t")):
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip().strip('"').strip("'")
    return data


# Skills are code, not knowledge. Their markdown is documentation of a tool —
# every skill has a SKILL.md, so walking them as notes reports nine duplicates
# of a filename that is a convention, and drags vendored seed docs into orphan
# and frontmatter checks that were never meant for them. The
# skills-in-the-vault check reads the filesystem directly and is unaffected.
NOT_NOTES = (os.path.join(".claude", "skills"),)


def walk_notes():
    """basename -> (relative path, text, frontmatter). Also returns duplicates."""
    by_name, paths = {}, defaultdict(list)
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if os.path.relpath(root, VAULT).startswith(NOT_NOTES):
            continue
        for name in files:
            if not name.endswith(".md"):
                continue
            full = os.path.join(root, name)
            relative = os.path.relpath(full, VAULT)
            paths[name[:-3]].append(relative)
            with open(full, encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
            by_name[name[:-3]] = (relative, text, parse_frontmatter(text))
    return by_name, paths


def main():
    print("lint_vault\n")
    print("delegated checks:")
    checker = os.path.join(VAULT, "check_links.py")
    if os.path.exists(checker):
        result = subprocess.run([sys.executable, checker], cwd=VAULT,
                                capture_output=True, text=True)
        tail = (result.stdout or result.stderr).strip().splitlines()
        if result.returncode == 0:
            ok("link integrity", tail[-1] if tail else "")
        else:
            fail("link integrity", tail[-8:])
    else:
        fail("link integrity", [f"check_links.py missing at {checker}"])

    notes, paths = walk_notes()
    print(f"\nvault checks ({len(notes)} notes):")

    # 1 — duplicates first; everything below reads the basename map.
    # README is a filesystem convention that appears once per directory, and
    # nobody writes `[[README]]`. Every other duplicate is a real ambiguity.
    dupes = {n: p for n, p in paths.items()
             if len(p) > 1 and n not in ("README",)}
    if dupes:
        fail(f"duplicate note names ({len(dupes)})",
             [f"[[{n}]] -> {', '.join(p)}" for n, p in sorted(dupes.items())[:8]]
             + ["Obsidian resolves these unpredictably; this lint keeps one."])
    else:
        ok("duplicate note names", "every name resolves to exactly one note")

    # 2 — orphans
    inbound = Counter()
    for name, (_path, text, _fm) in notes.items():
        blanked = CODE.sub(lambda m: " " * len(m.group(0)), text)
        for match in LINK.finditer(blanked):
            target = match.group(1).split("|")[0].split("#")[0].strip()
            if target in notes and target != name:
                inbound[target] += 1
    orphans = [
        name for name, (path, _t, _f) in notes.items()
        if inbound[name] == 0
        and not path.startswith(ORPHAN_EXEMPT)
        and name not in ORPHAN_EXEMPT_NAMES
    ]
    if orphans:
        fail(f"orphans ({len(orphans)} pages nothing links to)",
             [notes[n][0] for n in sorted(orphans)[:12]]
             + ["Link them from a client page or an index, or delete them."])
    else:
        ok("orphans", "every page is reachable")

    # 3 — generated files must match what was rendered
    if os.path.exists(GENERATED_MANIFEST):
        with open(GENERATED_MANIFEST, encoding="utf-8") as handle:
            manifest = json.load(handle)
        edited, missing = [], []
        for relative, digest in sorted(manifest.get("files", {}).items()):
            full = os.path.join(VAULT, relative)
            if not os.path.exists(full):
                missing.append(relative)
                continue
            with open(full, "rb") as handle:
                actual = hashlib.sha256(handle.read()).hexdigest()
            if actual != digest:
                edited.append(relative)
        if edited or missing:
            fail(f"generated files changed ({len(edited)} edited, "
                 f"{len(missing)} missing)",
                 [f"edited:  {p}" for p in edited[:6]]
                 + [f"missing: {p}" for p in missing[:4]]
                 + ["These render from roles.yaml. Edit roles.yaml and re-run",
                    "`org update` — a hand-edit here is reverted next time."])
        else:
            ok("generated files", f"{len(manifest.get('files', {}))} match the manifest")
    else:
        ok("generated files", "no manifest yet (org not rendered into this vault)")

    # 4 — Souls that were never made anyone's
    template_souls = [
        path for name, (path, text, _fm) in notes.items()
        if path.startswith("Team") and name.endswith("-Soul")
        and SOUL_MARKER in text
    ]
    sessions = [n for n, (p, _t, _f) in notes.items() if p.startswith("Sessions")]
    if template_souls and len(sessions) >= 5:
        fail(f"Souls still generated ({len(template_souls)})",
             template_souls[:8]
             + [f"{len(sessions)} sessions have happened; these identities are",
                "still the template. Rewrite them and delete the callout."])
    elif template_souls:
        ok("Souls", f"{len(template_souls)} still generated — expected this early")
    else:
        ok("Souls", "all rewritten")

    # 5 — memory scope
    misfiled = []
    for name, (path, text, _fm) in notes.items():
        if not path.startswith(os.path.join(".claude", "memory", "_shared")):
            continue
        if name in ("MEMORY", "README"):
            continue
        hits = {m.group(0).lower() for m in CLIENT_SIGNALS.finditer(text)}
        if len(hits) >= 3:
            misfiled.append(f"{path}  ({', '.join(sorted(hits)[:4])})")
    if misfiled:
        fail(f"client facts in shared memory ({len(misfiled)})",
             misfiled[:6]
             + ["_shared is for lessons that travel. A fact about one client's",
                "cluster or board belongs in .claude/memory/<client>/."])
    else:
        ok("memory scope", "no client specifics in _shared")

    # 6 — journal metrics
    thin = []
    for name, (path, _text, fm) in notes.items():
        if not path.startswith("Sessions") or fm.get("type") != "journal":
            continue
        for field in ("agent", "date", "prs", "tokens_in", "tokens_out"):
            if field not in fm:
                thin.append(f"{path}  missing `{field}`")
                break
    if thin:
        fail(f"journal entries missing metrics ({len(thin)})",
             thin[:8]
             + ["`prs: []` is valid — it records that none were touched.",
                "An absent key records nothing, which is the failure."])
    else:
        ok("journal metrics", "every entry carries PRs and tokens")

    # 7 — brief length
    long_briefs = []
    for name, (path, text, fm) in notes.items():
        if fm.get("type") != "brief":
            continue
        body = text.split("\n---", 2)[-1]
        bullets = sum(1 for line in body.splitlines() if BULLET.match(line))
        if bullets > BRIEF_BULLET_CAP:
            long_briefs.append(f"{path}  {bullets} bullets (cap {BRIEF_BULLET_CAP})")
    if long_briefs:
        fail(f"briefs over the cap ({len(long_briefs)})",
             long_briefs[:6]
             + ["The cap is the feature. Cut to what changed and what needs a",
                "decision; detail is available by asking."])
    else:
        ok("brief length", f"within {BRIEF_BULLET_CAP} bullets")

    # 8 — skills must live here
    # CLAUDE_HOME mirrors install.py's --home so the pair can be tested
    # together. Unset, it is the real home — which is the only thing that
    # matters in normal use.
    claude_home = os.environ.get("CLAUDE_HOME", os.path.expanduser("~"))
    installed = os.path.join(claude_home, ".claude", "skills")
    strays = []
    if os.path.isdir(installed):
        for entry in sorted(os.listdir(installed)):
            full = os.path.join(installed, entry)
            if not os.path.islink(full):
                strays.append(f"{entry}  (not a symlink)")
            elif not os.path.realpath(full).startswith(os.path.realpath(VAULT)):
                strays.append(f"{entry}  -> {os.path.realpath(full)}")
    if strays:
        fail(f"skills outside the vault ({len(strays)})",
             strays[:8]
             + ["A skill in ~/.claude is untracked, unsynced, and invisible to",
                "this vault's history. Move it here and re-run install-org."])
    else:
        ok("skills in the vault", "every installed skill links here")

    # 9 — frontmatter
    bare = [
        path for name, (path, _t, fm) in notes.items()
        if not fm and not path.startswith((".claude", "Templates"))
        and name not in ORPHAN_EXEMPT_NAMES
    ]
    if bare:
        fail(f"notes without frontmatter ({len(bare)})", bare[:10])
    else:
        ok("frontmatter", "present where required")

    print()
    if failures:
        print(f"LINT FAILED — {len(failures)} check(s): {', '.join(failures)}")
        return 1
    print("LINT CLEAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
