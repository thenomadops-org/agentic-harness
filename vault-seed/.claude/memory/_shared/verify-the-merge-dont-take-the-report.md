---
title: "Verify the merge — don't take the report"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: 2026-08-14
trigger: "an agent or a person reports that work landed"
---

A report listed five items as merged. Four were. The fifth sat closed with its
code absent from the main branch — the tracker said done, the report said
merged, and the branch had never landed.

**Why:** a report is a claim about the world made by something with an interest
in having succeeded. It is not evidence, and it is most confident exactly where
it is most wrong, because a partial failure rarely announces itself.

**How to apply:** check the artefact, not the account. For a merge that means
the commit is reachable from the target branch — not that a PR shows as merged,
which can be true after a revert.

```bash
git fetch origin main
git merge-base --is-ancestor <sha> origin/main && echo "landed" || echo "NOT ON MAIN"
```

Do this per item. A batch report is a single claim about several things and it
takes only one of them being wrong to make it false.

Related: [[claims-strengthen-as-they-propagate]] · [[git-delete-branch-closes-stacked-prs]]
