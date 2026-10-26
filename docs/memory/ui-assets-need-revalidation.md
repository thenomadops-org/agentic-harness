---
title: UI assets without Cache-Control keep a browser on the old bundle after a deploy
summary: Serve every embedded UI file through client.UIHandler (no-cache plus a content ETag), never a bare FileServer.
role: engineer
links: []
---
AOS-313. In the owner's human test of AOS-309 the server already served the new
bundle but the browser ran its cached /ui/*.js, so the approval wrote the old
default. http.FileServer on an embedded FS has no modification time, so it sends
no validator and the browser may reuse the file heuristically. `client.UIHandler`
now wraps both the server's /ui/ and the node's / with `Cache-Control: no-cache`
and an ETag from the content hash; an unchanged file is a 304. A new UI route
must use it; `ui_assets_cache_test.go` fails on a bare FileServer.
