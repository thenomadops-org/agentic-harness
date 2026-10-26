---
title: "--delete-branch silently closes stacked PRs"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: 2026-08-14
trigger: "merging a PR with --delete-branch, or any branch cleanup on merge"
---

Merging with `--delete-branch` **closes** any PR that used that branch as its
base. It does not retarget them, nothing announces it, and once closed this way
a PR can be neither reopened nor retargeted — `--base` and `reopen` both fail.

Two stacked PRs vanished from the open list this way. They were found only
because the open count did not match expectations.

**Why:** deleting a base branch destroys the comparison a child PR is defined
by, so GitHub closes it. The parent merge succeeds and reports success; the
damage is to something the command never mentions.

**How to apply:** before merging, check whether the head branch is anyone's base.

```bash
gh pr list --json number,baseRefName,headRefName \
  --jq '.[] | select(.baseRefName == "<branch-about-to-be-deleted>") | .number'
```

If anything comes back, merge **without** `--delete-branch`, let the children
retarget, and delete the branch afterwards.

**If it has already happened**, the work is not lost — the branch still exists on
the remote. Rebase onto the updated target and open a *new* PR. Worth knowing:
if the parent was squash-merged and its content is byte-identical to what the
child carries, `git rebase --onto` drops the duplicated commits outright rather
than making you resolve them. Check that first by diffing the child's base
against the target across the parent's files; an empty diff turns a promised
conflict-fest into zero conflicts.

Related: [[verify-the-merge-dont-take-the-report]]
