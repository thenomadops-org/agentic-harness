---
title: An empty or unread local file is not drift
summary: "Never report, store or adopt an empty copy, and never overwrite a copy that cannot be read; guard at the node, at report, and at accept."
role: engineer
links: []
---
AOS-326. The node sync loop reported a settings.json read that yielded "" as drift, and Accept would have made an empty file the standard for every node. The guard is in three places: the node skips an empty copy, config_report_drift refuses it, and resolveDriftAs refuses to accept an empty record. A stale empty record is cleared by the owner's dismiss (the keep action), which deletes it with no revert marker. The council also found the opposite hazard: a copy that cannot be read (no reader, or any error other than file-not-exist) must be left alone, not treated as absent and overwritten with no backup; the node now does nothing for that path and logs it once.

Cause of the empty read is unverified. One reading is a truncate-then-write race while Claude Code rewrote the file. A competing reading: since AOS-171 any copy containing a home path is refused, so an empty copy is the only kind that could land as a record. Either way, a settings.json with a home path cannot become the standard through any route; a node fact such as HOME (deresolved to the placeholder) is the route that works.

Round 2 found the sibling route: a seed from a node. SeedOnce now skips a blank copy and every server route that stores a standard (config_put, config_save, seed, restore) refuses one, through configsecret.Blank, the single definition of blank shared with the drift checks (whitespace and byte-order marks, matching JavaScript trim). No managed path is ever meant to be empty: an empty standard cannot be told from a failed read, and every node would write it.
