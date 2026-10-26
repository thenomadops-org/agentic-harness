# Owner interface

**Status:** DRAFT, 2026-10-26
**Intent:** [../intent/owner-interface.md](../intent/owner-interface.md)
**Terms:** [Owner interface](../GLOSSARY.md#owner-interface)

The owner interface is the role in the owner's chat. It files work, starts work,
and brings updates back. Any chat front end can play it. The tracker under it is
the configured adapter. The relay is `team-post`.

Each fact is a ruling or a check in this repository.

1. **Any chat may play the role.** The owner interface is a role. Vendor ids in [`org/vendors.yaml`](../../org/vendors.yaml) name the CLIs a persona session runs. The chat is whichever front end the owner already has open. That front end plays the role by using the configured tracker adapter and the `team-post` relay in these facts.

2. **A described story is filed in the owner's words.** The owner describes the work in the chat. The interface files one tracker item carrying the project label, the intent in the owner's words, and the acceptance, using the operations in [the adapter contract](../../adapters/README.md). The item starts in the workflow's grooming status: filed, and not yet ordered. When the owner orders that work in the same conversation, the item starts in the ready status instead, the status `list_ready` returns. Status names are read from the live workflow. [`adapters/jira/ADAPTER.md`](../../adapters/jira/ADAPTER.md) resolves a transition by name on the live item. Example names for a workflow that uses them: grooming `Grooming`, ready `To Do`.

3. **Go moves the item to ready.** When the owner says go, the interface moves the item to the ready status and reads the status back. [The adapter contract](../../adapters/README.md) requires that read-back after every write. The lead then assigns a persona and a vendor from [`org/routing.yaml`](../../org/routing.yaml) (`lead_vendor`, `build_vendors`, `build_personas`, `qa_vendors`). The interface may prompt that persona in its pane. The persona builds the change.

4. **A relayed update is checked first.** A `team-post` outcome wakes the interface. The interface checks the pull request, that pull request's CI, and the tracker item, then tells the owner what those three show. When the three disagree with the post, the relay says so.

5. **Quiet hours hold ordinary outcomes.** From 22:00 to 08:00 in the owner's local time, the interface relays a `team-post` outcome only when the table says relay. A question the owner asks in the chat is answered when it is asked. The table covers agent posts.

| Outcome | From 22:00 to 08:00 |
|:---|:---|
| `blocked` | relay |
| `QA pass` | relay |
| `QA fail` | relay |
| `done` | hold until 08:00 |
| `ready for QA` | hold until 08:00 |

6. **An on-demand update reads live sources.** When the owner asks `update?`, the interface answers from the tracker item, the pull request and its CI, and the live session panes. Persona sessions are herdr panes opened by [`tools/launch.py`](../../tools/launch.py).

7. **No tracker access is a tagged note.** An agent that cannot perform a tracker transition still posts when `team-post` is on PATH. The message is one line of three fields separated by ` | `. The status field may contain spaces and may not contain `|`.

```text
no-tracker: <ITEM-KEY> | <status name> | <one line>
```

`<ITEM-KEY>` is the tracker's key. `<status name>` is the workflow's status name. The interface reads the matching transition on the live item and applies it, then reads the item back. A status name the live workflow does not have stays unchanged, and the interface tells the owner the name was refused. `<one line>` is the outcome the agent is reporting (`done`, `ready for QA`, `QA pass`, `QA fail`, or `blocked`) and the pull-request link.

8. **The tree names the command and does not read the post.** [`org/templates/agent.md.tmpl`](../../org/templates/agent.md.tmpl) tells the agent: when `team-post` is on PATH, post `done`, `ready for QA`, `QA pass`, `QA fail`, or `blocked` by running `team-post` with the vendor id of the CLI that started the session; when `team-post` is not on PATH, say nothing. `test_every_rendered_agent_posts_or_stays_quiet` in [`tools/test_launch.py`](../../tools/test_launch.py) asserts those words and rejects the transport name `slack` in a rendered agent. A search of the Python in this repository finds `team-post` in that test only. The program that implements `team-post` lives outside this repository. Its channel and its credentials stay outside with it.

9. **Closing stays with the owner.** The interface leaves an item short of done when an agent posts, including a `no-tracker:` note that names a done status. [The adapter contract](../../adapters/README.md) states this under "Never close."

## Posting

```bash
team-post <vendor-id> "ready for QA: <one line> https://example.invalid/pull/1"
```

An agent that cannot move the tracker uses fact 7:

```bash
team-post <vendor-id> "no-tracker: PROJ-123 | In Review | ready for QA: https://example.invalid/pull/1"
```

`PROJ-123`, `In Review`, and `example.invalid` are placeholders. Another workflow uses its own status name.

## Open

- A tracker workflow with no grooming status. Fact 2 names that status and does not invent a substitute.
- The zone of the quiet-hours clock. Fact 5 uses the owner's local time. A fixed zone is not set.

## See also

- [Tracker adapters](../../adapters/README.md)
- [Jira adapter](../../adapters/jira/ADAPTER.md)
- [Routing](../../org/routing.yaml)
