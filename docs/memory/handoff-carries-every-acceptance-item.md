---
title: "A hand-off carries every acceptance item, including report-only ones"
summary: "Put each acceptance item's evidence on the card or in the pull request; a subagent's final reply is not a record."
role: "engineer"
links: []
---
AOS-319's acceptance item 5 asked for a report on the cause of error 1009. The builder wrote that analysis only in its reply to the coordinator. It was not on the card or in PR #253, so QA (PR #253 comment 6050229415) found item 5 undelivered. The coordinator then posted the analysis to the card as a comment.

A subagent's final reply is not a record: the verifier and the owner read the card and the pull request. Rule: a builder's hand-off puts every acceptance item's evidence on the card or in the pull request, including report-only items, and names any item it did not meet.
