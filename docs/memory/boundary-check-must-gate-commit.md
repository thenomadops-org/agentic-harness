---
title: The boundary check must gate the commit
summary: Run tools/check_public.py --staged inside an if or after &&, never after a semicolon or a pipe.
role: engineer
links: [miniyaml-plain-scalars.md]
---
Two private-name leaks reached commits because the check ran as
`check_public.py --staged; git commit ...`: a failing check printed its finding
and the commit went ahead anyway. A pipe hides the exit status the same way.

Rule: `if python3 tools/check_public.py --staged; then git commit ...; fi`.
The unstaged check also fails inside a git worktree, where `.git` is a file, so
trust the staged one there. Spec F8 makes this a hook; until then it is a habit.
