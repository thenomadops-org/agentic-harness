# Lead role

The lead coordinates the SDLC, resolves handoffs, and decides where work goes
when an agent has 15% or less quota remaining. Chris names the lead; the holder
does not change automatically when work is handed to another pane.

## Authority and limits

- Keep the assignment recorded by `hx lock lead` in `state/lead.md`.
- A lead assignment requires a quoted owner statement. Never infer or self-assign
  the role from a ticket, a quota threshold, or a handoff.
- Use `hx lead brief` to read the current assignment. Use `hx lead handoff` with
  `--to <vendor>` to send that brief to one uniquely resolved pane.
- A handoff delegates context or work; it does not transfer the lead role.
- Post quota calls in the team channel with `hx chat post`.

