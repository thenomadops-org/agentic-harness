# Intent — agents carry approved work through the SDLC

**Originator:** the principal
**Recorded:** 2026-09-27, transcribed by Codex from this conversation
**Status:** ACTIVE goal; the implementation contract is a draft

## Problem

The principal does not want to distribute a credential to each agent or
repeatedly chase work through its stages:

> "I dont want to have to be required to had my agents tokens all the time."

The reason for agent identities was to keep workers within their roles:

> "it intent was to keep agetns from getting of track and wotking outside of there line"

The desired outcome is a flow into which the principal can put new stories:

> "make the SDLC a flow i can pipe new storys to and the agents will work them without me hounding each task to be compelted."

These are the principal's words, including spelling. The synthesis below is
Codex's interpretation, not a separate owner ruling.

## Desired outcome

After an initial installation and approval of the work, the org handles the
routine coordination needed to finish it. The owner supplies intent and makes
the decisions that require their judgment. Agent access, task assignment,
review handoffs, and recovery do not require repeated credential transfers or
reminders from the owner.

Roles remain meaningful: a worker cannot give itself a different job or act
outside the authority granted for its assignment. The record still identifies
who built, reviewed, and verified each change.

## Constraints and open decisions

- Preserve the intent → spec → story chain and the shared source of truth
  established in the original markdown-backend intent (not published).
- Preserve role boundaries while removing routine credential handling from
  the owner. Whether internal credentials remain is an implementation choice;
  removing all agent identities has not been requested or approved.
- Make stalled work visible and recoverable. A worker reporting completion
  should result in the next stage being handled, not another owner reminder.
- **Open:** which merge and production release decisions may be automated.
  The draft preserves the existing owner approval gates pending the owner's
  answer. Routine work should progress up to those gates without chasing.

## Relationship to existing documents

This is an additional intent for the credential lifecycle and work execution
loop. It does not rewrite the historical owner's words or claim the current
backend already supplies this behavior. Proposed mechanisms and evidence belong
in [the draft spec](../spec/agent-workflow.md); the stories, their acceptance
criteria and their ordering belong on the board, not in this repository.
