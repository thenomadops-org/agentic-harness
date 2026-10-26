# Glossary format

Agentic-OS keeps one glossary at `docs/GLOSSARY.md`. If it does not exist yet, the
first resolved term creates it. **Never create a second glossary**, and never put a
decision, an implementation detail or scratch notes in it.

## Structure

```md
# Glossary

The words this project uses on purpose. Where the spec, the code and conversation
disagree about one of them, this file is the tiebreak, and the disagreement is a
bug in whichever one is wrong.

## A

### Actor

The identity a call is attributed to: the named member (or the owner) behind a
credential. Not the same as a [role](#role), which is the seat the credential is
scoped to.

## J

### Job token

A short-lived credential minted for one agent for one job, scoped to a role and a
project and revoked at hand-back. See `docs/decisions/`.
```

## Rules

- **One canonical entry per concept.** When several words exist for one thing, define
  the preferred term and mention the synonyms inside its definition. Do not create
  competing entries.
- **Keep definitions tight**: a sentence or two. Define what it is, then link out for
  depth (a spec fact, a decision record, the tool contract).
- **Alphabetical**, under single-letter `##` headings, cross-linked with
  `[Term](#term)`.
- **Only terms a reader of this repo needs defined**, with this project's meaning.
  Generic programming words stay out.
- **Truth order.** Verify each definition against the spec, the decision records and
  the code. If the glossary and the code disagree, say so and ask which is right; do
  not silently pick.
- **Publishable.** The glossary is public with the rest of the repo. Define terms by
  what they mean here, with no names, hosts or tickets from any other organisation.

## Maintenance

Update it inline during a grilling session, the moment a term is resolved. After
editing, run `python3 tools/check_public.py`.
