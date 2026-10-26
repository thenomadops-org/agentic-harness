#!/usr/bin/env python3
"""Find what a finished ticket left on an agent host. Stdlib only.

Shared by `hx done`, `hx merge` and `hx reap`. Every outside call goes through
one `run` function and two small clients (Jira, GitHub through `gh`), so the
tests swap them for fakes. Nothing here acts on its own: the planners return
`Action` rows, and `execute` runs them, or only prints them on a dry run.

Safety rules shared by every caller:

- a pane whose foreground process is not a bare shell, or that herdr reports
  an agent in, is live and is never closed by the reaper;
- a worktree with uncommitted changes, a lock, a process inside it, or a
  detached HEAD no remote branch contains is reported, never removed, and
  removal never passes `--force`;
- a main checkout is switched to main only when it is clean, and only with a
  fast-forward;
- only Postgres clusters under the scratch roots and containers named after a
  ticket or pull request are stopped.
"""

import base64
import datetime as _dt
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

SHELLS = {"zsh", "bash", "sh", "fish", "dash", "login", "-zsh", "-bash"}
DONE_STATUSES = ("done", "closed", "resolved")
# Pane labels the launcher writes: `<persona>-<TICKET>`, with an optional seat
# number, e.g. qa-OPS-347, grok-OPS-217, engineer-1-OPS-345, qa-QUEUE3.
LAUNCHER_LABEL = re.compile(r"\A[a-z][a-z0-9]*(?:-[0-9]+)?-[A-Z][A-Z0-9]*(?:-[0-9]+)?\Z")
# Postgres backends that are server housekeeping, not a client connection.
PG_AUX = ("checkpointer", "background writer", "walwriter", "autovacuum",
          "logical replication", "io worker", "archiver", "stats", "startup",
          "walsender", "walreceiver", "postmaster")
SCRATCH_CONTAINER = re.compile(r"\A(?:pg|postgres|db|redis|mysql)[-_]?(\d+)\Z", re.IGNORECASE)


class CleanupError(Exception):
    """An error whose message is safe to print (no credentials)."""


@dataclass
class Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def run(argv, cwd=None, timeout=120):
    """Run argv and capture text output. A missing command is exit 127."""
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except FileNotFoundError:
        return Result(127, "", f"{argv[0]}: command not found")
    except subprocess.TimeoutExpired:
        return Result(124, "", f"{argv[0]}: timed out after {timeout}s")
    return Result(done.returncode, done.stdout, done.stderr)


# ----------------------------------------------------------------- tickets

def key_regex(key):
    """Match a ticket key in a label, branch or path: OPS-347, ops347, ops_347."""
    match = re.fullmatch(r"([A-Za-z]+)-(\d+)", key or "")
    if not match:
        raise CleanupError(f"not a ticket key: {key!r}")
    prefix, number = match.groups()
    return re.compile(rf"(?<![A-Za-z0-9]){prefix}[-_]?{number}(?![0-9])", re.IGNORECASE)


def find_keys(text, projects=("OPS",)):
    """Return every PROJECT-N key named in text, normalized to upper case."""
    found = set()
    for project in projects:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(project)}[-_]?(\d+)(?![0-9])"
        for number in re.findall(pattern, text or "", re.IGNORECASE):
            found.add(f"{project.upper()}-{int(number)}")
    return found


def normalize_key(key):
    match = re.fullmatch(r"([A-Za-z]+)[-_]?(\d+)", (key or "").strip())
    if not match:
        raise CleanupError(f"not a ticket key: {key!r}")
    return f"{match.group(1).upper()}-{int(match.group(2))}"


# ----------------------------------------------------------------- config

def default_config_path(environ=None):
    environ = os.environ if environ is None else environ
    if environ.get("HX_CLEANUP_CONFIG"):
        return Path(environ["HX_CLEANUP_CONFIG"]).expanduser()
    base = environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "agentic-os" / "cleanup.json"


def state_dir(environ=None):
    environ = os.environ if environ is None else environ
    base = environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "agentic-os"


def load_config(path=None, environ=None, checkouts=None):
    """Read the local cleanup config. Command-line checkouts win over the file."""
    environ = os.environ if environ is None else environ
    path = Path(path) if path else default_config_path(environ)
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CleanupError(f"cleanup config {path} is not JSON: {exc.msg}") from None
        if not isinstance(data, dict):
            raise CleanupError(f"cleanup config {path} must be an object")
    env_checkouts = [p for p in environ.get("HX_CHECKOUTS", "").split(os.pathsep) if p]
    chosen = checkouts or env_checkouts or data.get("checkouts") or []
    config = {
        "checkouts": [str(Path(p).expanduser()) for p in chosen],
        "projects": [str(p).upper() for p in data.get("projects", ["OPS"])],
        "jira_base_url": environ.get("JIRA_BASE_URL") or data.get("jira_base_url", ""),
        "done_statuses": [s.lower() for s in data.get("done_statuses", DONE_STATUSES)],
        "scratch_roots": [str(Path(p).expanduser())
                          for p in data.get("scratch_roots", ["~/.cache", "/tmp"])],
        "max_scratch_age_hours": float(data.get("max_scratch_age_hours", 6)),
        "protect_workspaces": [str(w) for w in data.get("protect_workspaces", [])],
        "main_branch": data.get("main_branch", "main"),
    }
    return config


class Log:
    """Print each line and append it, time-stamped, to the cleanup log."""

    def __init__(self, path=None, stream=None, clock=None):
        self.path = Path(path) if path else None
        self.stream = stream
        self.clock = clock or (lambda: _dt.datetime.now().astimezone())
        self.lines = []

    def __call__(self, text):
        self.lines.append(text)
        print(text, file=self.stream)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            stamp = self.clock().isoformat(timespec="seconds")
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(f"{stamp} {text}\n")


# ----------------------------------------------------------------- clients

class Jira:
    """Read one issue's status over the Jira REST API, with a cache."""

    def __init__(self, base_url, email, token, opener=None):
        self.base_url = (base_url or "").rstrip("/")
        self.email, self.token = email, token
        self.opener = opener or urllib.request.urlopen
        self.cache = {}

    @classmethod
    def from_env(cls, config, environ=None):
        environ = os.environ if environ is None else environ
        return cls(config.get("jira_base_url"), environ.get("JIRA_EMAIL"),
                   environ.get("JIRA_API_TOKEN"))

    def status(self, key):
        """Return (status name, category key), or None when it cannot be read."""
        if key in self.cache:
            return self.cache[key]
        value = None
        if self.base_url and self.email and self.token:
            auth = base64.b64encode(f"{self.email}:{self.token}".encode()).decode()
            request = urllib.request.Request(
                f"{self.base_url}/rest/api/3/issue/{key}?fields=status",
                headers={"Authorization": "Basic " + auth, "Accept": "application/json"},
            )
            try:
                with self.opener(request, timeout=20) as response:
                    body = json.loads(response.read().decode("utf-8"))
                status = body["fields"]["status"]
                value = (status["name"], status.get("statusCategory", {}).get("key", ""))
            except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
                value = None
        self.cache[key] = value
        return value


def is_done(status, done_statuses=DONE_STATUSES):
    if not status:
        return False
    name, category = status
    return name.lower() in done_statuses or category == "done"


class GitHub:
    """Pull request lookups through the gh CLI."""

    FIELDS = "number,title,headRefName,state,mergedAt,url"

    def __init__(self, runner=run):
        self.run = runner

    def prs_for_key(self, repo, key):
        result = self.run(["gh", "pr", "list", "-R", repo, "--state", "all",
                           "--search", key, "--limit", "100", "--json", self.FIELDS])
        if result.returncode != 0:
            raise CleanupError(f"gh pr list failed for {repo}: {result.stderr.strip()[:200]}")
        pattern = key_regex(key)
        rows = json.loads(result.stdout or "[]")
        return [dict(row, repo=repo) for row in rows
                if pattern.search(row.get("title", "")) or pattern.search(row.get("headRefName", ""))]

    def pr_view(self, number, repo=None):
        argv = ["gh", "pr", "view", str(number), "--json", self.FIELDS]
        if repo:
            argv += ["-R", repo]
        result = self.run(argv)
        if result.returncode != 0:
            raise CleanupError(f"gh pr view {number} failed: {result.stderr.strip()[:200]}")
        return json.loads(result.stdout)


def repo_slug(url):
    """owner/name from a GitHub remote URL, or None."""
    match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?\Z", (url or "").strip())
    return match.group(1) if match else None


# ----------------------------------------------------------------- host state

@dataclass
class Pane:
    pane_id: str
    workspace_id: str
    label: str = ""
    cwd: str = ""
    agent: str = ""
    live: bool = False
    processes: list = field(default_factory=list)


@dataclass
class Workspace:
    workspace_id: str
    label: str = ""
    panes: list = field(default_factory=list)


def _herdr_json(runner, argv):
    result = runner(argv)
    if result.returncode != 0:
        raise CleanupError(f"{' '.join(argv)} failed: {result.stderr.strip()[:200]}")
    try:
        return json.loads(result.stdout)["result"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise CleanupError(f"{' '.join(argv)} returned unexpected output") from None


def herdr_state(runner=run):
    """Workspaces with their panes, and whether each pane runs anything."""
    spaces = _herdr_json(runner, ["herdr", "workspace", "list"]).get("workspaces", [])
    panes = _herdr_json(runner, ["herdr", "pane", "list"]).get("panes", [])
    by_id = {w["workspace_id"]: Workspace(w["workspace_id"], w.get("label", ""))
             for w in spaces}
    for row in panes:
        pane = Pane(row["pane_id"], row.get("workspace_id", ""), row.get("label", ""),
                    row.get("cwd", ""), row.get("agent") or "")
        info = runner(["herdr", "pane", "process-info", "--pane", pane.pane_id])
        names = None
        if info.returncode == 0:
            try:
                procs = json.loads(info.stdout)["result"]["process_info"]["foreground_processes"]
                names = [p.get("name", "") for p in procs]
            except (json.JSONDecodeError, KeyError, TypeError):
                names = None
        pane.processes = names or []
        # Unknown process state counts as live: never close what cannot be read.
        pane.live = bool(pane.agent) or names is None or any(n not in SHELLS for n in names)
        by_id.setdefault(pane.workspace_id, Workspace(pane.workspace_id)).panes.append(pane)
    return list(by_id.values())


@dataclass
class Worktree:
    path: str
    branch: str = ""
    head: str = ""
    detached: bool = False
    prunable: bool = False
    locked: bool = False
    main: bool = False


def worktrees(checkout, runner=run):
    result = runner(["git", "-C", checkout, "worktree", "list", "--porcelain"])
    if result.returncode != 0:
        raise CleanupError(f"git worktree list failed in {checkout}: {result.stderr.strip()[:200]}")
    rows, current = [], None
    for line in result.stdout.splitlines() + [""]:
        if not line:
            if current:
                rows.append(current)
            current = None
            continue
        word, _, rest = line.partition(" ")
        if word == "worktree":
            current = Worktree(rest, main=not rows and current is None)
        elif current is None:
            continue
        elif word == "branch":
            current.branch = rest.removeprefix("refs/heads/")
        elif word == "HEAD":
            current.head = rest
        elif word == "detached":
            current.detached = True
        elif word == "prunable":
            current.prunable = True
        elif word == "locked":
            current.locked = True
    return rows


def dirty(path, runner=run):
    """True when git reports changes, None when the tree cannot be read."""
    result = runner(["git", "-C", path, "status", "--porcelain"])
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def head_on_remote(path, runner=run):
    result = runner(["git", "-C", path, "branch", "-r", "--contains", "HEAD"])
    return result.returncode == 0 and bool(result.stdout.strip())


def current_branch(path, runner=run):
    result = runner(["git", "-C", path, "branch", "--show-current"])
    return result.stdout.strip() if result.returncode == 0 else ""


class Procs:
    """Process facts read from /proc (root injectable for tests)."""

    def __init__(self, root="/proc", clock_ticks=None):
        self.root = Path(root)
        self.ticks = clock_ticks or os.sysconf("SC_CLK_TCK")

    def _pids(self):
        try:
            return [int(p.name) for p in self.root.iterdir() if p.name.isdigit()]
        except OSError:
            return []

    def _read(self, pid, name):
        try:
            return (self.root / str(pid) / name).read_bytes()
        except OSError:
            return b""

    def cmdline(self, pid):
        return [a.decode("utf-8", "replace") for a in self._read(pid, "cmdline").split(b"\0") if a]

    def _stat(self, pid):
        raw = self._read(pid, "stat").decode("utf-8", "replace")
        tail = raw.rpartition(")")[2].split()
        return tail  # tail[1] is ppid, tail[19] is starttime

    def ppid(self, pid):
        tail = self._stat(pid)
        return int(tail[1]) if len(tail) > 1 else 0

    def age_seconds(self, pid):
        tail = self._stat(pid)
        try:
            uptime = float((self.root / "uptime").read_text().split()[0])
            return max(0.0, uptime - int(tail[19]) / self.ticks)
        except (OSError, IndexError, ValueError):
            return 0.0

    def cwds(self):
        rows = []
        for pid in self._pids():
            try:
                rows.append((pid, os.readlink(self.root / str(pid) / "cwd")))
            except OSError:
                continue
        return rows

    def postmasters(self):
        """Running Postgres servers: pid, binary dir, data dir, age, clients."""
        rows, children = [], {}
        cmdlines = {pid: self.cmdline(pid) for pid in self._pids()}
        for pid, argv in cmdlines.items():
            if argv and argv[0].startswith("postgres:"):
                children.setdefault(self.ppid(pid), []).append(argv[0])
        for pid, argv in cmdlines.items():
            if not argv or os.path.basename(argv[0]) != "postgres" or "-D" not in argv:
                continue
            index = argv.index("-D")
            if index + 1 >= len(argv):
                continue
            clients = [c for c in children.get(pid, [])
                       if not any(aux in c for aux in PG_AUX)]
            rows.append({"pid": pid, "bindir": os.path.dirname(argv[0]),
                         "datadir": argv[index + 1], "age": self.age_seconds(pid),
                         "clients": len(clients)})
        return rows


def containers(runner=run):
    """Running containers as dicts, or None when docker cannot be used."""
    result = runner(["docker", "ps", "--format", "{{json .}}"])
    if result.returncode != 0:
        return None
    rows = []
    for line in result.stdout.splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


# ----------------------------------------------------------------- actions

@dataclass
class Action:
    kind: str
    target: str
    argv: list
    reason: str = ""


@dataclass
class Plan:
    actions: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def act(self, kind, target, argv, reason=""):
        if not any(a.argv == argv for a in self.actions):
            self.actions.append(Action(kind, target, list(argv), reason))

    def skip(self, kind, target, reason):
        self.skipped.append((kind, target, reason))


def workspace_actions(plan, space, matched, protected, allow_live=False):
    """Close a ticket's whole workspace, or only its panes in a shared one."""
    if space.workspace_id in protected or space.label in protected:
        for pane in matched:
            plan.skip("pane", f"{pane.pane_id} {pane.label}", "workspace is protected")
        return
    shared = len(space.panes) > len(matched)
    closable = []
    for pane in matched:
        if pane.live and (shared or not allow_live):
            plan.skip("pane", f"{pane.pane_id} {pane.label}",
                      f"live agent ({pane.agent or ','.join(pane.processes) or 'unknown'})")
        else:
            closable.append(pane)
    if not shared and len(closable) == len(space.panes):
        plan.act("workspace", f"{space.workspace_id} {space.label}".strip(),
                 ["herdr", "workspace", "close", space.workspace_id],
                 "ticket workspace")
        return
    for pane in closable:
        plan.act("pane", f"{pane.pane_id} {pane.label}",
                 ["herdr", "pane", "close", pane.pane_id], "ticket pane")


def worktree_action(plan, checkout, tree, reason, cwds, runner=run):
    """Remove one worktree when it is safe; otherwise record why not."""
    if tree.main:
        return
    if tree.prunable:
        plan.act("prune", checkout, ["git", "-C", checkout, "worktree", "prune"],
                 "metadata for deleted worktrees")
        return
    if tree.locked:
        plan.skip("worktree", tree.path, "locked")
        return
    state = dirty(tree.path, runner)
    if state is None:
        plan.skip("worktree", tree.path, "git status failed")
        return
    if state:
        plan.skip("worktree", tree.path, "uncommitted changes")
        return
    users = sorted({pid for pid, cwd in cwds if inside(cwd, tree.path)})
    if users:
        plan.skip("worktree", tree.path, f"in use by pid {','.join(map(str, users[:5]))}")
        return
    if tree.detached and not head_on_remote(tree.path, runner):
        plan.skip("worktree", tree.path, "detached HEAD not on any remote branch")
        return
    plan.act("worktree", tree.path, ["git", "-C", checkout, "worktree", "remove", tree.path], reason)


def checkout_actions(plan, checkout, main_branch, reason, runner=run):
    state = dirty(checkout, runner)
    if state is None or state:
        plan.skip("checkout", checkout, "uncommitted changes" if state else "git status failed")
        return
    plan.act("checkout", checkout, ["git", "-C", checkout, "fetch", "origin", main_branch], reason)
    plan.act("checkout", checkout, ["git", "-C", checkout, "switch", main_branch], reason)
    plan.act("checkout", checkout,
             ["git", "-C", checkout, "merge", "--ff-only", f"origin/{main_branch}"], reason)


def postgres_action(plan, pg, reason):
    pg_ctl = os.path.join(pg["bindir"], "pg_ctl")
    if os.path.exists(pg_ctl):
        argv = [pg_ctl, "stop", "-D", pg["datadir"], "-m", "fast"]
    else:
        # SIGINT is Postgres' fast shutdown, what `pg_ctl stop -m fast` sends.
        argv = ["kill", "-INT", str(pg["pid"])]
    plan.act("postgres", f"{pg['datadir']} (pid {pg['pid']})", argv, reason)


def execute(plan, log, dry_run, runner=run):
    """Run each action once; log it either way. Returns the failure count."""
    failures = 0
    for action in plan.actions:
        prefix = "would" if dry_run else "do"
        log(f"{prefix} {action.kind}: {action.target} ({action.reason}) :: {' '.join(action.argv)}")
        if dry_run:
            continue
        result = runner(action.argv)
        if result.returncode != 0:
            failures += 1
            log(f"  FAILED rc={result.returncode}: {(result.stderr or result.stdout).strip()[:300]}")
    for kind, target, reason in plan.skipped:
        log(f"skip {kind}: {target} ({reason})")
    for note in plan.notes:
        log(f"note: {note}")
    return failures
