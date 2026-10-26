---
title: "Home"
tags: [vault, type/index]
type: index
status: active
created: 2026-01-01
---

# Home

The entry point. Everything reachable from here is findable; anything not is
an orphan, and `lint_vault.py` will say so.

## The org

- [[Team-ORG]] — who we are, who decides
- [[Team-Operating-Agreement]] — how work moves

## Clients

<!-- One line per client, linking its home page. -->

*No clients yet.*

## Reading

- **Journals** — `Sessions/`, one per agent per session, with PRs and tokens
- **The brief** — `Sessions/Brief-YYYY-MM-DD.md`, bulleted, capped, written for
  the principal
- **Memory** — `.claude/memory/_shared/` travels; `.claude/memory/<client>/`
  does not

## Maintenance

```bash
python3 lint_vault.py
```
