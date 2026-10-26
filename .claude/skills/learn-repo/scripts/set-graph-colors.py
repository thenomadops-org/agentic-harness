#!/usr/bin/env python3
"""Regenerate the vault graph COLOUR template from note tags.

Colours are **tag-based**: every note carries a `repo/<repo>` tag, and each repo
maps to one graph colorGroup, so a note colours itself from its own tag — no
per-folder bookkeeping. Memory notes (`tag:#type/memory` or the `_Memory/` folder)
are gold and sit on top; `00-Index/` meta notes (no repo tag) are slate.

`.obsidian/graph.json` is **gitignored** (it churns per-user with view-state and
would conflict at scale). This script writes the tracked TEMPLATE
`scripts/graph.default.json` — commit that so every teammate shares the same
colours — and also refreshes the live `.obsidian/graph.json` if it is present.

Run it with NO args after `learn-repo` adds a new repo, so the new `repo/<name>`
tag gets a colour. Idempotent: repos listed in REPO_HUES keep their curated hue;
any other repo draws the next spare from FREE (add it to REPO_HUES to pin it).

Usage:  set-graph-colors.py            # regenerate from the repo/ tags in the vault
        VAULT=/path set-graph-colors.py
"""
import json, os, re, glob

# Vault root: $VAULT env wins; else self-locate — this script lives at
# <vault>/.claude/skills/learn-repo/scripts/, so four levels up is the vault.
_SELF = os.path.dirname(os.path.realpath(__file__))
VAULT = os.environ.get("VAULT", os.path.abspath(os.path.join(_SELF, "..", "..", "..", "..")))
TMPL  = os.path.join(VAULT, "scripts", "graph.default.json")
LIVE  = os.path.join(VAULT, ".obsidian", "graph.json")

MEMORY_GOLD = 0xCA8A04
META_SLATE  = 0x64748B

# Curated repo -> colour. Empty by default; add entries like
#     "my-service": 0x6366F1,
# to pin a repo to a stable, meaningful hue. Any repo not listed here draws the
# next unused colour from FREE below.
REPO_HUES = {
    "project-a": 0x6366F1,
    "load-gcp-infr": 0x2DD4BF,
    "project-b": 0xF59E0B,
    "tower-war": 0xA855F7,
    "vault": 0x64748B,
}
# Spare hues, handed out in order to repos not in REPO_HUES. Add curated ones to
# REPO_HUES for permanence; extend this list if you outgrow it.
FREE = [0x6366F1, 0x3B82F6, 0x2DD4BF, 0xF59E0B, 0xEF4444, 0xA855F7, 0xEC4899,
        0x22C55E, 0x0EA5E9, 0x14B8A6, 0xF43F5E, 0x84CC16, 0x8B5CF6, 0xD946EF,
        0x38BDF8, 0xFB923C, 0x34D399, 0x22D3EE, 0xFB7185]

def repos_in_vault():
    """Every `repo/<name>` tag on a note's frontmatter `tags:` line (body text ignored)."""
    found = set()
    for f in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
        if os.sep + ".git" + os.sep in f:
            continue
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if not txt.startswith("---"):
            continue
        end = txt.find("\n---", 3)               # frontmatter block only
        if end < 0:
            continue
        for line in txt[3:end].splitlines():
            if line.lstrip().startswith("tags:"):
                for m in re.findall(r"repo/([A-Za-z0-9_.-]+)", line):
                    found.add(m)
    return sorted(found)

def grp(query, rgb):
    return {"query": query, "color": {"a": 1, "rgb": rgb}}

def build_groups():
    repos = repos_in_vault()
    hues, nxt, new = dict(REPO_HUES), 0, []
    for r in repos:
        if r not in hues:
            hues[r] = FREE[nxt % len(FREE)]; nxt += 1; new.append(r)
    groups = [grp("tag:#type/memory", MEMORY_GOLD), grp('path:"_Memory/"', MEMORY_GOLD)]
    for r in repos:
        groups.append(grp(f"tag:#repo/{r}", hues[r]))
    groups.append(grp('path:"00-Index/"', META_SLATE))
    return groups, repos, new

def write(path, groups):
    base = {}
    if os.path.exists(path):
        try: base = json.load(open(path))
        except Exception: base = {}
    if not base:
        base = {"collapse-filter": True, "search": "", "showTags": False,
                "showAttachments": False, "hideUnresolved": False, "showOrphans": True}
    base["colorGroups"] = groups
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(base, f, indent=2); f.write("\n")

def main():
    groups, repos, new = build_groups()
    write(TMPL, groups)                       # the tracked template (source of truth)
    if os.path.exists(LIVE):                  # refresh this machine's live file too
        write(LIVE, groups)
    print(f"template scripts/graph.default.json: {len(groups)} colorGroups ({len(repos)} repos)")
    if new:
        print("new repos auto-coloured from spares (add to REPO_HUES for a permanent hue):", new)

if __name__ == "__main__":
    main()
