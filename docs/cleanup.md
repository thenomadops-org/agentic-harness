# Agent cleanup: `hx done`, `hx merge`, `hx reap`

Nothing used to close what an agent opened. The launcher opens one herdr
workspace per ticket, agents add worktrees and scratch databases, and herdr
restores every saved workspace on restart, so finished panes come back as
bare shells. These three commands close that loop. All are stdlib Python and
log every action to `$XDG_STATE_HOME/agentic-os/cleanup.log`
(`~/.local/state/agentic-os/cleanup.log` by default).

## Configure

Write `~/.config/agentic-os/cleanup.json` (or point `HX_CLEANUP_CONFIG` at
another file). Only `checkouts` is required; it lists the main checkouts whose
worktrees and branches are managed, and their `origin` remotes are the
repositories searched for pull requests.

```json
{
  "checkouts": ["~/Code/app", "~/Code/agentic-harness"],
  "jira_base_url": "https://your-site.atlassian.net",
  "projects": ["OPS"],
  "done_statuses": ["done"],
  "scratch_roots": ["~/.cache", "/tmp"],
  "max_scratch_age_hours": 6,
  "protect_workspaces": []
}
```

`HX_CHECKOUTS` (path-separated) or `--checkout` override `checkouts`;
`JIRA_BASE_URL` overrides `jira_base_url`. Jira is read with `JIRA_EMAIL` and
`JIRA_API_TOKEN`; pull requests with `gh` (so `GH_TOKEN` or a gh login).

## `hx done <KEY>`

```sh
bin/hx done OPS-347 --dry-run    # print what would be closed
bin/hx done OPS-347              # do it
```

Refuses (exit 3) unless a pull request whose title or branch names the key is
merged, none is still open, and Jira shows the ticket Done. Then it:

1. closes herdr workspaces whose pane or workspace label names the key; in a
   shared workspace it closes only those panes;
2. removes that ticket's worktrees (`git worktree remove`, never `--force`)
   and runs `git worktree prune`;
3. stops scratch Postgres clusters whose data directory under a scratch root
   names the key (`pg_ctl stop -m fast` beside the server binary, or SIGINT),
   and containers named after the key or its merged pull request (`pg1894`);
4. moves a main checkout that sits on the ticket's branch to `main`
   (`fetch`, `switch`, `merge --ff-only`).

It skips, and says why: a pane running an agent (`--force` closes a live
single-pane ticket workspace, never a pane in a shared one), a worktree with
uncommitted changes, a lock, a process inside it, or a detached HEAD no remote
branch contains, and a main checkout with changes.

## `hx merge <PR>`

```sh
bin/hx merge 1894 --repo owner/app --squash
```

Runs `gh pr merge` with the caller's flags, refuses `--admin`, and runs
`hx done` for the pull request's key once GitHub reports it merged. When Jira
is not Done yet, `done` refuses and the merge still succeeds; run `hx done`
after the ticket moves, or let the nightly reaper pick it up. An auto-merge
that is only queued does not run `done`.

A GitHub Actions post-merge step cannot do this: the gate runs on
GitHub-hosted runners (this repository is public and must not schedule onto
an org machine), and those runners cannot reach the agent host's herdr,
worktrees or databases. The local wrapper is the merge path.

## `hx reap`

```sh
bin/hx reap                 # report only (default)
bin/hx reap --close         # act
bin/hx reap --close --chat  # and post the summary with hx chat post
```

See the docstring of `tools/hx_reap.py` for the orphan rules. The report is
written to `$XDG_STATE_HOME/agentic-os/reaper/reap-<time>.log`. Old ticket
folders under `/tmp` that are not worktrees are reported, never removed.
`--chat` needs `HX_AGENT` and `HX_CHAT_CHANNEL` (see `docs/hx-chat.md`).

### Nightly timer

`ops/systemd/` holds `agent-reaper.service.in` and `agent-reaper.timer`
(00:30 local time, `Persistent=true`). Nothing is installed by merging this.

```sh
ops/systemd/install.sh --dry-run          # show the rendered units
ops/systemd/install.sh --report-only      # install as report-only, not enabled
ops/systemd/install.sh                    # install as --close, not enabled
systemctl --user enable --now agent-reaper.timer
journalctl --user -u agent-reaper.service # last run
```

The service reads its tokens from `~/.config/agentic-os/cleanup.env`
(`KEY=value` lines, mode 600): `GH_TOKEN`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and
for `--chat`, `HX_AGENT`, `HX_CHAT_CHANNEL` and the matching Slack token.
