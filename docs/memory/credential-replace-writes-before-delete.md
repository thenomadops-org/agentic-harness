---
title: "Replacing a credential writes the new one before deleting the old"
summary: "Write the new credential and its markers first, delete the old one only after the write is confirmed, and treat any path that can end with no credential as blocking."
role: "qa"
links: []
---
AOS-319 (PR #253): the iPad's Regenerate key flow called `SecureEnclaveKeyStore.save()`, which deletes the stored key before writing the new one. A failed write left the device with no signing key, and Settings still said "the existing key was kept".

QA (PR #253 comment 6050229415) rated this non-blocking. The council (comment 6050240433) blocked the merge on it. The council was right: on a credential surface, a path that loses the only key locks the owner out of every node until a new public key is installed by hand.

Rule: replacing a credential writes the new one, and its markers, first. It removes the old one only after that write is confirmed. A reviewer treats any path that can end with no credential as blocking, not cosmetic.
