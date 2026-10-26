# Sessions

Append-only. One journal per agent per working session, plus the chief of
staff's brief.

```
Sessions/Bob_SysEng_2026-08-14.md      an agent's journal
Sessions/Brief-2026-08-14.md           the roll-up the principal reads
```

Journals carry **PRs touched and tokens used** in frontmatter, measured rather
than estimated. `lint_vault.py` fails a journal missing them.

Nobody is expected to read every journal. That is what the brief is for — and
why it is capped at 20 bullets.

Templates: [[journal-entry]] · [[principal-brief]]
