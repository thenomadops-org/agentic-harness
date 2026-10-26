---
title: A pairing is approved by the code the device shows, and the server cannot show that code
summary: Read what a tool keys on before promising a page a column; approve_pairing takes the code, which the server keeps only as a hash.
role: engineer
links: []
---
AOS-329 asked for a pairing list with a "code prefix". `approve_pairing`
(`devices.go`) is keyed on the code that `pair_device_request` returns once to
the device; `PairRow` keeps `CodeHash` only, so no page can list a prefix, and
a request approved by name or id would let any request called "ipad" be
approved by mistake. The page therefore lists names and times, and the owner
types the code the device shows (`pairingsSection.ts`, `servePairings`). There
is also no `deny_pairing` tool. A code prefix or a deny needs a `devices.go`
change (store a short prefix at request time; add a deny tool), which a story
scoped to the UI and `ui_server.go` cannot make. Check the tool's keying and
the story's scope before writing acceptance a page cannot meet.
