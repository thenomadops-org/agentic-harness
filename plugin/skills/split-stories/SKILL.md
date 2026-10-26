---
name: split-stories
description: Split an approved spec into work cards, each citing one numbered fact and declaring its scope as exact files, never globs. Use after the owner approves a spec, when work must be filed as stories, or when a card needs its scope fixed.
---

# /split-stories

Stage 3 of the SDLC (portable-workforce spec F12). Output: `kind: work` cards
in state `proposed`, one per concern, each citing the spec fact it implements.
Product approves `proposed` to `ready`; you do not.

## Rules

- **Cite a fact.** Every card's `spec_ref` is
  `projects/<project>/spec/<page>.md#f<N>-<title-slug>`. The board refuses a
  bare `#f<N>` and a slug that no longer matches the published fact.
- **Scope is exact files, never a glob.** List each file the card may change,
  relative to the repository root: `tools/render.py`, not
  `tools/*.py` and not `tools/`. Dispatch
  reserves a scope while the story runs and treats two entries that share a
  literal prefix as overlapping, so one glob reserves its whole prefix and
  blocks every story under it (board memory
  `scope-globs-reserve-their-whole-prefix`, AOS-266). A new file is listed by
  its exact path. If you cannot name the files, read the code until you can;
  if the work needs a file you cannot name, split it so the first card finds out.
- **No shared files.** Two cards that name the same file cannot run in
  parallel. Either merge them, or the later one `depends_on` the earlier.
- **One concern per card**, small enough for one pull request (stack them).

## Steps

1. Read the spec (`get_project_page`) and the code each fact touches.
2. Draft the cards as a JSON list: `title`, `priority`, `spec_ref`, `scope`,
   `body`, and optionally `role`, `verifier`, `depends_on` (ids of existing
   stories, or the title of an earlier card in this list).
3. **Dry run.** `python3 ${CLAUDE_PLUGIN_ROOT}/skills/split-stories/check_cards.py --repo . --spec SPEC.md CARDS.json`
   rejects a glob, a directory, an absolute or `..` path, a missing or
   mismatched fact, and two cards sharing a file. It prints the `create_story`
   payloads. Fix what it names.
4. Show the owner the cards. File only approved ones with `create_story`,
   then read each back with `get_story`.

## Refuse

- Any scope entry containing `*`, `?`, `[`, `]`, `{` or `}`, or ending in `/`.
- A card with an empty scope: that is the whole repository.
- A card with no fact to cite. Go back to `/spec`.
