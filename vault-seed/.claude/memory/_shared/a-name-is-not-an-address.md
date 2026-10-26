---
title: "A name is not an address"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: 2026-08-28
trigger: "sending a message to a named agent, or attributing work to whoever wrote a commit"
---

A seat's name can resolve to two different things at the same instant: a
*spawnable agent type*, and *one or more live sessions* already running as that
seat. Nothing in a message distinguishes them.

In one night at six-to-nine concurrent agents this produced five misroutes. The
worst was a near-miss: an agent was asked to ratify a design artefact it had
never written, because the message went to a fresh instance of its type rather
than to the session that did the work. It had no way to know that, and an
agreeable answer would have manufactured authority for a document nobody had
reviewed. A correction sent to the wrong instance of a name was refused —
correctly — by an agent that had no record of the message it was being corrected
about.

**Why:** a name is a *lookup*, and lookups return sets. There are three distinct
failure modes and they look alike from the outside: the message reaches the
wrong live session, it reaches a new session with none of the context, or it
reaches something that answers confidently about work it never did.

**How to apply:** address a specific agent by its **session id**, never by its
name alone. When a correction arrives about something you did not do, say so and
ask for the source rather than accepting it — the discrepancy is the signal.

And attribute work by **the commit or branch that touched the artefact**, never
by the author field. Every agent in an org like this commits under the
principal's git identity, so `author` is constant across the whole team and
carries no information at all. Asking "who wrote this" of git returns the
principal every time, including for work done by something that no longer exists.

Related: [[verify-the-merge-dont-take-the-report]] · [[claims-strengthen-as-they-propagate]]
