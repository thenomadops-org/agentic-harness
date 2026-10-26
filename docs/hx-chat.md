# `hx chat`

`bin/hx` is the stdlib-only Slack client for team messages. The channel is
required from `HX_CHAT_CHANNEL`, so public repository files contain no
workspace-specific identifiers. Set it in your local shell or user config.

Choose an identity with `--agent claude|grok|codex` or `HX_AGENT`; choose the
displayed model with `--model` or `HX_MODEL`. `HX_PERSONA` optionally sets the
persona label (otherwise it uses the agent id). The matching
`SLACK_BOT_TOKEN_<AGENT>` variable must be set. The token is sent only in the
Slack Authorization header.

```sh
export HX_CHAT_CHANNEL=<your-channel-id>
bin/hx chat post --agent codex --model gpt-6-luna --ticket OPS-340 \
  --to claude "Please review the new chat CLI"
bin/hx chat post --agent codex --model gpt-6-luna "General team update"
bin/hx chat read --agent codex --model gpt-6-luna --since 2h
bin/hx chat read --agent codex --model gpt-6-luna --since 30m --to codex
bin/hx chat read --agent codex --model gpt-6-luna --since 1761420000
```

Posts start with `[agent model] persona@hostname`, followed by an optional
`-> @agent`, optional `(OPS-n)`, and the message. Empty messages are refused.
On success the CLI prints the Slack timestamp and permalink. History prints
local time, author, and text, follows pagination cursors, and can filter for
messages addressed to an agent. `post --nudge` or `HX_CHAT_NUDGE=1` asks Herdr
to notify the addressed agent when its pane is present; nudge failures only
warn and do not fail a successful Slack post.

The gate runs the mocked Slack/herdr unit tests through
`python3 tools/test_vendors.py`; run that command locally as well.
