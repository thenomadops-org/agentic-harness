---
title: The stdlib YAML reader refuses an apostrophe in an unquoted value
summary: Quote any value in .agentic-os.yaml or frontmatter that contains an apostrophe or a colon.
role: engineer
links: []
---
`tools/miniyaml.py` reads a documented subset and refuses the rest, loudly, with
a line number. `deploy: the owner's host applies it` failed as "unterminated
quoted string" because the reader takes the apostrophe for a quote. Either
reword or wrap the whole value in double quotes. The refusal is the design: a
silent misparse of a project file would be worse. The plugin carries a copy of
the reader at `plugin/skills/onboard-project/miniyaml.py`; a test fails when the
copy drifts from the source.
