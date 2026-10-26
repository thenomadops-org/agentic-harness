---
name: spec
description: Write a spec as numbered facts, each serving the intent, plus a spec card. Use after /scope when the owner approves an intent and the work needs facts a story can cite, or when a spec fact must change.
---

# /spec

Stage 2 of the SDLC (portable-workforce spec F12). Output: one Spec page of
numbered facts and one `kind: spec` card. The owner approves; you draft.

## Steps

1. **Read the intent** (`get_project_page` kind `intent`). Every fact must
   serve a sentence in it; a fact with no intent behind it is dropped.
2. **Draft facts** in the board's form, one per numbered line:
   `N. **Title.** The fact, checkable: a command, a value, a refusal.`
   Number from 1, with no gaps and no reuse. A fact is testable by someone who
   did not write it. Put open questions under an `## Open` heading, not in a
   fact. Never renumber a published fact: stories cite it as `#f<N>-<slug>`,
   and the board refuses a citation whose title has changed.
3. **Dry run.** `python3 ${CLAUDE_PLUGIN_ROOT}/skills/spec/check_spec.py FILE.md`
   checks the numbering, the titles and prints each fact's anchor
   (`#f3-refuse-an-empty-scope`) and the payloads it would send. Fix what it names.
4. **File it.** `write_project_page {project, kind: "spec", page, body}`, then
   `create_story` with `kind: "spec"` and a `spec_ref` of the form `projects/<project>/spec/<page>.md#<section>` (the dry run prints it).
5. Read back with `get_project_page`. Show the owner the anchors; the card
   stays `proposed` until the owner approves.

## Refuse

- A fact that says how (a file, a function) rather than what must hold.
- Skipping or renumbering a number that is already cited.
