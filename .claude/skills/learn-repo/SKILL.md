---
name: learn-repo
description: Ingest a code repo into this Obsidian vault as a structured, source-verified set of notes (a MOC + overview(s) + one component note per module) so teammates and their AI can onboard from the vault instead of re-reading the repo. Checkpoint-driven, two human gates. Use when asked to "learn"/"ingest"/"document a repo into the vault". Invoke as /learn-repo <repo-path-or-name> [target-folder-name].
---

# /learn-repo — ingest a repo into the vault

Vault = this folder (your Obsidian vault). The repo to ingest comes from the invocation argument, read by path. **Additive only** — never overwrite an existing note; prefer `mv` over `rm`. The bundled scripts self-locate the vault from their own path (or honour `VAULT=<path>`), so you never pass the vault path to them.

Follow the frontmatter contract and colour rules in the vault `CLAUDE.md`. Every note you write gets all 8 frontmatter fields, a `repo/<repo>` tag, body callouts matching its `color:`, and wiki-links to siblings (links resolve by basename).

## Phase 0 — Preflight
- Resolve `<repo>` to a path. Target vault folder = arg 2, else the repo basename.
- If the target folder already EXISTS → **extend mode**: compute and fill only the gap.

## Phase 1 — Survey → CHECKPOINT 1 (human gate)
- Map the repo: languages, top-level dirs, build systems, entry points, module/package list, READMEs.
- Propose a folder structure + the full note list: one MOC, one or more overviews, one component note per meaningful module.
- **PRESENT** the structure + note list to the user and **WAIT for approval / edits** before spending tokens. The user trims scope here.

## Phase 2 — Note #1 (depth gate)
- YOU write the most-central module's note first, source-verified against the actual code (cite file + line ranges). It sets the quality bar and becomes the exemplar for the rest. Show it to the user.

## Phase 3 — Fan-out
- Write the remaining component notes, each source-verified against specific files. Reuse note #1 as the pattern. For large repos, delegate notes to parallel subagents in small waves (give each the exact source files, the destination path, and note #1 as the exemplar).
- Generate the overview(s) and the MOC **last**, so they index the real set. Add every note to the MOC.
- Spot-check at least one note per language/app against source.

## Phase 4 — Graph colours (only if the repo is NEW to the vault)
- Colours are tag-based: each note's `repo/<repo>` tag drives its graph colour. Run `python3 .claude/skills/learn-repo/scripts/set-graph-colors.py` (no args) once — it re-derives `scripts/graph.default.json` from every `repo/` tag in the vault and colours the new repo (add it to the script's `REPO_HUES` to pin a permanent hue). Tell the user to reload Obsidian to see it.

## Phase 5 — Verify → CHECKPOINT 2 (human gate)
- Run `bash .claude/skills/learn-repo/scripts/verify.sh <folder>` — must end `RESULT: PASS`. Fix any ✗ (dangling links, missing frontmatter fields, invalid graph JSON).
- **PRESENT** the verify report + a short summary (notes written, structure, any source-accuracy caveats) and **WAIT for review.**

## Phase 6 — Wire-up
- Add the new folder's MOC to `00-Index/Master-Index.md` under the right theme.
- Add a row for the repo to `_Memory/00-Memory-Index.md`, and start its `_Memory/<repo>-Memory.md` file.

## If you rename or split a folder later
Fix ALL references in the same change (Master-Index links, any Dataview `FROM "<old>"`, Canvas `file:` paths), then re-run `verify.sh <folder> <old-name>` to confirm zero stray references.
