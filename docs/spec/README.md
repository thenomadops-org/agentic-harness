# Spec of record

Specs in this directory are the spec of record for Agentic-OS: what a
subsystem does, and what constrains it — stated as **facts**, never as
incidents. A spec says what is true and why; it does not narrate what
happened on some Tuesday to get there.

Every fact must be **checkable from this repo**: an owner ruling, a decision
record in [`../decisions/`](../decisions/), or, once code exists, a
`file:line`. Where something is not decided, a spec says `Open:` and stops —
a guess here becomes a requirement nobody chose.

An [intent](../intent/README.md) sits upstream and never overrides a spec;
where the two disagree, the intent is stale, not the spec.
