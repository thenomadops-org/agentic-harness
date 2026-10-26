"""hx done, hx merge and hx reap against fake herdr, gh, git, docker and Postgres.

Run from the repo root:

    python3 tools/test_cleanup.py
"""

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cleanup  # noqa: E402
import hx_done  # noqa: E402
import hx_reap  # noqa: E402
from cleanup import Result  # noqa: E402

CO = "/srv/app"          # a main checkout
HARNESS = "/srv/harness"  # a second main checkout


def herdr_payloads(spaces, panes):
    return (
        json.dumps({"result": {"workspaces": spaces}}),
        json.dumps({"result": {"panes": panes}}),
    )


class FakeHost:
    """A machine: herdr panes, git worktrees, processes, containers, PRs, Jira."""

    def __init__(self):
        self.calls = []
        self.spaces = [
            {"workspace_id": "w4", "label": "main"},
            {"workspace_id": "w34", "label": "qa-OPS-347"},
            {"workspace_id": "w36", "label": "qa-OPS-347"},
            {"workspace_id": "w2V", "label": "qa"},
            {"workspace_id": "w50", "label": "grok-OPS-400"},
            {"workspace_id": "w51", "label": "scratch"},
        ]
        self.panes = [
            {"pane_id": "w4:p1", "workspace_id": "w4", "label": "lead", "agent": "claude"},
            {"pane_id": "w4:p2", "workspace_id": "w4", "label": "grok-OPS-347"},
            {"pane_id": "w34:p1", "workspace_id": "w34", "label": "qa-OPS-347"},
            {"pane_id": "w36:p1", "workspace_id": "w36", "label": "qa-OPS-347"},
            {"pane_id": "w2V:p1", "workspace_id": "w2V", "label": "qa-QUEUE3"},
            {"pane_id": "w50:p1", "workspace_id": "w50", "label": "grok-OPS-400"},
            {"pane_id": "w51:p1", "workspace_id": "w51", "label": ""},
        ]
        self.procs_by_pane = {"w4:p1": ["claude"], "w4:p2": ["grok"], "w50:p1": ["node"]}
        self.worktrees = {
            CO: [
                ("/srv/app", "ops-227-guard-fix", False),
                ("/srv/wt/app-ops-347", "ops-347-x", False),
                ("/srv/wt/app-ops-347-dirty", "ops-347-y", False),
                ("/srv/wt/app-ops-400", "ops-400-z", False),
                ("/srv/wt/gone", "ops-12-old", True),
                ("/srv/wt/app-ops-227", "ops-227-guard-fix-2", False),
            ],
            HARNESS: [("/srv/harness", "ops-347-codex-persona", False)],
        }
        self.dirty = {"/srv/wt/app-ops-347-dirty"}
        self.prs = {
            "OPS-347": [{"number": 7, "title": "OPS-347: persona", "headRefName": "ops-347-x",
                         "state": "MERGED", "mergedAt": "2026-10-26T07:48:18Z", "url": "u"}],
            "OPS-227": [{"number": 1879, "title": "OPS-227: guard", "headRefName": "ops-227-guard-fix",
                         "state": "MERGED", "mergedAt": "x", "url": "u"}],
            "OPS-218": [{"number": 1890, "title": "OPS-218: build", "headRefName": "ops-218",
                         "state": "OPEN", "mergedAt": None, "url": "u"}],
            "OPS-400": [],
        }
        self.pr_states = {"1894": "MERGED", "1999": "OPEN"}
        self.containers = [{"Names": "pg1894"}, {"Names": "pg1999"}, {"Names": "web"},
                           {"Names": "redis-ops-347"}]
        self.docker_ok = True
        self.fail = set()

    def __call__(self, argv, cwd=None, timeout=120):
        self.calls.append(list(argv))
        key = tuple(argv)
        if key in self.fail:
            return Result(1, "", "boom")
        if argv[:3] == ["herdr", "workspace", "list"]:
            return Result(0, herdr_payloads(self.spaces, self.panes)[0])
        if argv[:3] == ["herdr", "pane", "list"]:
            return Result(0, herdr_payloads(self.spaces, self.panes)[1])
        if argv[:3] == ["herdr", "pane", "process-info"]:
            names = self.procs_by_pane.get(argv[4], ["zsh"])
            procs = [{"name": n} for n in names]
            return Result(0, json.dumps({"result": {"process_info": {"foreground_processes": procs}}}))
        if argv[0] == "git" and argv[3:5] == ["worktree", "list"]:
            out = []
            for path, branch, prunable in self.worktrees.get(argv[2], []):
                out += [f"worktree {path}", "HEAD abc", f"branch refs/heads/{branch}"]
                if prunable:
                    out.append("prunable gitdir file points to non-existent location")
                out.append("")
            return Result(0, "\n".join(out))
        if argv[0] == "git" and argv[3:4] == ["status"]:
            return Result(0, " M file\n" if argv[2] in self.dirty else "")
        if argv[0] == "git" and argv[3:5] == ["remote", "get-url"]:
            return Result(0, {CO: "git@github.com:acme/app.git\n",
                              HARNESS: "https://github.com/acme/harness\n"}[argv[2]])
        if argv[:3] == ["gh", "pr", "list"]:
            repo, key = argv[4], argv[argv.index("--search") + 1]
            rows = self.prs.get(key, []) if repo == "acme/app" else []
            if repo == "acme/harness" and key == "OPS-347":
                rows = [{"number": 6, "title": "unrelated mention", "headRefName": "other",
                         "state": "OPEN"}]
            return Result(0, json.dumps(rows))
        if argv[:3] == ["gh", "pr", "view"]:
            state = self.pr_states.get(argv[3])
            if state is None:
                return Result(1, "", "no pull request")
            return Result(0, json.dumps({"number": int(argv[3]), "title": f"OPS-347: x",
                                         "headRefName": "ops-347-x", "state": state}))
        if argv[:2] == ["docker", "ps"]:
            if not self.docker_ok:
                return Result(1, "", "permission denied")
            return Result(0, "\n".join(json.dumps(c) for c in self.containers) + "\nnot json\n")
        return Result(0, "")


class FakeJira:
    def __init__(self, statuses):
        self.statuses = statuses

    def status(self, key):
        return self.statuses.get(key)


class FakeProcs:
    def __init__(self, cwds=(), postmasters=()):
        self._cwds, self._pg = list(cwds), list(postmasters)

    def cwds(self):
        return self._cwds

    def postmasters(self):
        return self._pg


def make_host(fake, statuses=None, procs=None, **config):
    base = {"checkouts": [CO, HARNESS], "projects": ["OPS"], "done_statuses": ["done"],
            "scratch_roots": ["/home/u/.cache", "/tmp"], "protect_workspaces": [],
            "max_scratch_age_hours": 6.0, "main_branch": "main", "jira_base_url": ""}
    base.update(config)
    statuses = statuses if statuses is not None else {
        "OPS-347": ("Done", "indeterminate"), "OPS-227": ("Done", "indeterminate"),
        "OPS-218": ("In Review", "indeterminate"), "OPS-400": ("In Progress", "indeterminate"),
        "OPS-12": ("Done", "done"),
    }
    return hx_done.Host(base, runner=fake, jira=FakeJira(statuses),
                        procs=procs or FakeProcs())


def quiet_log():
    return cleanup.Log(stream=io.StringIO())


def actions(fake):
    return [c for c in fake.calls if c[:3] in (["herdr", "workspace", "close"], ["herdr", "pane", "close"])
            or (c[0] == "git" and c[3:4] in (["switch"], ["merge"], ["fetch"]))
            or (c[0] == "git" and c[3:5] in (["worktree", "remove"], ["worktree", "prune"]))
            or c[:2] == ["docker", "stop"] or c[0] == "kill" or c[0].endswith("pg_ctl")]


class KeyTests(unittest.TestCase):
    def test_key_forms(self):
        pattern = cleanup.key_regex("OPS-347")
        for text in ("qa-OPS-347", "theside-ops347-main", "ops_347", "/tmp/x-ops-347/wt"):
            self.assertTrue(pattern.search(text), text)
        for text in ("OPS-3470", "XOPS-347", "ops-34"):
            self.assertFalse(pattern.search(text), text)
        self.assertEqual(cleanup.find_keys("ops227-main / OPS-12 / pg1894"), {"OPS-227", "OPS-12"})
        self.assertEqual(cleanup.normalize_key("ops347"), "OPS-347")
        with self.assertRaises(cleanup.CleanupError):
            cleanup.normalize_key("nope")
        with self.assertRaises(cleanup.CleanupError):
            cleanup.key_regex("347")
        self.assertEqual(cleanup.repo_slug("git@github.com:acme/app.git"), "acme/app")
        self.assertIsNone(cleanup.repo_slug("https://example.com/x"))

    def test_launcher_labels(self):
        for label in ("qa-OPS-347", "grok-OPS-217", "engineer-1-OPS-345", "qa-QUEUE3"):
            self.assertTrue(cleanup.LAUNCHER_LABEL.fullmatch(label), label)
        for label in ("theside", "qa", "agentis-os", ""):
            self.assertFalse(cleanup.LAUNCHER_LABEL.fullmatch(label), label)

    def test_is_done(self):
        self.assertTrue(cleanup.is_done(("Done", "indeterminate")))
        self.assertTrue(cleanup.is_done(("Shipped", "done")))
        self.assertFalse(cleanup.is_done(("In Review", "indeterminate")))
        self.assertFalse(cleanup.is_done(None))


class DoneTests(unittest.TestCase):
    def test_refuses_when_no_pr_is_merged(self):
        fake = FakeHost()
        log = quiet_log()
        code = hx_done.done_main(["OPS-400"], host=make_host(fake), log=log)
        self.assertEqual(code, 3)
        self.assertIn("no merged pull request", log.lines[-1])
        self.assertEqual(actions(fake), [])

    def test_refuses_when_a_pr_is_still_open(self):
        fake = FakeHost()
        fake.prs["OPS-218"].append({"number": 1, "title": "OPS-218 a", "headRefName": "b",
                                    "state": "MERGED"})
        log = quiet_log()
        self.assertEqual(hx_done.done_main(["OPS-218"], host=make_host(fake), log=log), 3)
        self.assertIn("still has open pull request", log.lines[-1])
        self.assertEqual(actions(fake), [])

    def test_refuses_when_jira_is_not_done(self):
        fake = FakeHost()
        log = quiet_log()
        statuses = {"OPS-347": ("In Review", "indeterminate")}
        fake.prs["OPS-347"] = fake.prs["OPS-347"]
        self.assertEqual(hx_done.done_main(["OPS-347", "--repo", "acme/app"],
                                           host=make_host(fake, statuses, checkouts=[CO]), log=log), 3)
        self.assertIn("not Done", log.lines[-1])
        self.assertEqual(actions(fake), [])

    def test_refuses_when_jira_cannot_be_read(self):
        fake = FakeHost()
        log = quiet_log()
        self.assertEqual(hx_done.done_main(["OPS-347"], host=make_host(fake, {}, checkouts=[CO]),
                                           log=log), 3)
        self.assertIn("cannot read Jira", log.lines[-1])

    def test_dry_run_plans_and_runs_nothing(self):
        fake = FakeHost()
        pg = {"pid": 9, "bindir": "/opt/pg/bin", "datadir": "/home/u/.cache/grok-tmp/ops347/pgdata",
              "age": 100.0, "clients": 0}
        other = dict(pg, pid=10, datadir="/var/lib/postgresql/ops347")
        host = make_host(fake, procs=FakeProcs(postmasters=[pg, other]), checkouts=[CO])
        log = quiet_log()
        self.assertEqual(hx_done.done_main(["ops-347", "--dry-run"], host=host, log=log), 0)
        text = "\n".join(log.lines)
        self.assertEqual(actions(fake), [])
        self.assertIn("would workspace: w34 qa-OPS-347", text)
        self.assertIn("would workspace: w36 qa-OPS-347", text)
        self.assertIn("would worktree: /srv/wt/app-ops-347 ", text)
        self.assertIn("skip worktree: /srv/wt/app-ops-347-dirty (uncommitted changes)", text)
        self.assertIn("skip pane: w4:p2 grok-OPS-347 (live agent (grok))", text)
        self.assertIn("kill -INT 9", text)
        self.assertNotIn("kill -INT 10", text)
        self.assertIn("docker stop redis-ops-347", text)
        self.assertNotIn("docker stop pg1999", text)
        self.assertNotIn("herdr workspace close w4", text)

    def test_executes_and_logs_to_file(self):
        fake = FakeHost()
        fake.containers.append({"Names": "pg1879"})
        with tempfile.TemporaryDirectory() as tmp:
            bindir = os.path.join(tmp, "bin")
            os.makedirs(bindir)
            Path(bindir, "pg_ctl").write_text("")
            pg = {"pid": 9, "bindir": bindir, "datadir": "/tmp/qa-ops227/pg", "age": 1.0, "clients": 1}
            busy = ("/srv/wt/app-ops-227", )
            host = make_host(fake, procs=FakeProcs(cwds=[(77, busy[0] + "/src")], postmasters=[pg]),
                             checkouts=[CO])
            log_path = Path(tmp, "state", "cleanup.log")
            log = cleanup.Log(log_path, stream=io.StringIO())
            fake.fail.add(("git", "-C", CO, "worktree", "prune"))
            code = hx_done.done_main(["OPS-227"], host=host, log=log)
            self.assertEqual(code, 1)  # the prune failure is reported
            ran = actions(fake)
            self.assertIn(["git", "-C", CO, "switch", "main"], ran)
            self.assertIn(["git", "-C", CO, "merge", "--ff-only", "origin/main"], ran)
            self.assertIn(["docker", "stop", "pg1879"], ran)
            self.assertIn([os.path.join(bindir, "pg_ctl"), "stop", "-D", "/tmp/qa-ops227/pg", "-m", "fast"], ran)
            self.assertNotIn(["git", "-C", CO, "worktree", "remove", "/srv/wt/app-ops-227"], ran)
            written = log_path.read_text()
            self.assertIn("in use by pid 77", written)
            self.assertIn("FAILED rc=1", written)

    def test_force_closes_a_live_single_pane_but_never_a_shared_one(self):
        fake = FakeHost()
        fake.prs["OPS-400"] = [{"number": 2, "title": "OPS-400", "headRefName": "ops-400-z",
                                "state": "MERGED"}]
        fake.panes.append({"pane_id": "w4:p3", "workspace_id": "w4", "label": "codex-OPS-400",
                           "agent": "codex"})
        fake.panes.append({"pane_id": "w4:p4", "workspace_id": "w4", "label": "qa-OPS-400"})
        statuses = {"OPS-400": ("Done", "done")}
        log = quiet_log()
        hx_done.done_main(["OPS-400", "--dry-run"], host=make_host(fake, statuses, checkouts=[CO]), log=log)
        self.assertIn("skip pane: w50:p1 grok-OPS-400 (live agent (node))", log.lines)
        log = quiet_log()
        hx_done.done_main(["OPS-400", "--force"], host=make_host(fake, statuses, checkouts=[CO]), log=log)
        ran = actions(fake)
        self.assertIn(["herdr", "workspace", "close", "w50"], ran)
        self.assertIn(["herdr", "pane", "close", "w4:p4"], ran)
        self.assertNotIn(["herdr", "pane", "close", "w4:p3"], ran)
        self.assertNotIn(["herdr", "workspace", "close", "w4"], ran)

    def test_protected_workspace_and_missing_tools(self):
        fake = FakeHost()
        fake.docker_ok = False
        fake.fail.add(("herdr", "workspace", "list"))
        log = quiet_log()
        hx_done.done_main(["OPS-347", "--dry-run"], host=make_host(fake, checkouts=[CO]), log=log)
        text = "\n".join(log.lines)
        self.assertIn("herdr unavailable", text)
        self.assertIn("docker unavailable", text)
        fake = FakeHost()
        log = quiet_log()
        hx_done.done_main(["OPS-347", "--dry-run"],
                          host=make_host(fake, checkouts=[CO], protect_workspaces=["w34"]), log=log)
        self.assertIn("skip pane: w34:p1 qa-OPS-347 (workspace is protected)", log.lines)

    def test_no_checkouts_and_bad_key(self):
        err = io.StringIO()
        sys.stderr, saved = err, sys.stderr
        try:
            self.assertEqual(hx_done.done_main(["OPS-1"], host=make_host(FakeHost(), checkouts=[]),
                                               log=quiet_log()), 2)
            self.assertEqual(hx_done.done_main(["bogus"], host=make_host(FakeHost()), log=quiet_log()), 2)
        finally:
            sys.stderr = saved
        self.assertIn("no main checkouts", err.getvalue())


class MergeTests(unittest.TestCase):
    def test_refuses_admin(self):
        err = io.StringIO()
        sys.stderr, saved = err, sys.stderr
        try:
            self.assertEqual(hx_done.merge_main(["5", "--squash", "--admin"], host=make_host(FakeHost())), 2)
        finally:
            sys.stderr = saved
        self.assertIn("refusing --admin", err.getvalue())

    def test_merge_then_done(self):
        fake = FakeHost()
        seen = []
        log = quiet_log()

        def done(argv, host=None, log=None):
            seen.append(argv)
            return 0

        code = hx_done.merge_main(["1894", "-R", "acme/app", "--squash", "--checkout", CO],
                                  host=make_host(fake), log=log, done=done)
        self.assertEqual(code, 0)
        self.assertIn(["gh", "pr", "merge", "1894", "-R", "acme/app", "--squash"], fake.calls)
        self.assertEqual(seen, [["OPS-347", "--repo", "acme/app", "--checkout", CO]])

    def test_merge_variants(self):
        fake = FakeHost()
        log = quiet_log()
        self.assertEqual(hx_done.merge_main(["1894", "--dry-run"], host=make_host(fake), log=log), 0)
        self.assertNotIn("merge", [c[2] for c in fake.calls if c[:2] == ["gh", "pr"]])
        self.assertIn("would merge", log.lines[-1])
        # queued auto-merge: done is not run
        self.assertEqual(hx_done.merge_main(["1999", "--auto"], host=make_host(fake), log=log,
                                            done=lambda *a, **k: 99), 0)
        self.assertIn("auto-merge queued", log.lines[-1])
        # merge failed
        fake.fail.add(("gh", "pr", "merge", "7"))
        self.assertEqual(hx_done.merge_main(["7"], host=make_host(fake), log=log), 1)
        # unreadable after merge
        self.assertEqual(hx_done.merge_main(["4242"], host=make_host(fake), log=log), 0)
        self.assertIn("could not read", log.lines[-1])
        # Jira not Done yet: merge still succeeds
        self.assertEqual(hx_done.merge_main(["1894"], host=make_host(fake), log=log,
                                            done=lambda *a, **k: 3), 0)
        self.assertIn("will run once the ticket is Done", log.lines[-1])

    def test_merge_without_a_single_key(self):
        fake = FakeHost()
        log = quiet_log()
        fake_view = cleanup.GitHub(lambda argv, **_: Result(0, json.dumps(
            {"number": 3, "title": "no key here", "headRefName": "misc", "state": "MERGED"})))
        host = make_host(fake)
        host.github = fake_view
        self.assertEqual(hx_done.merge_main(["3"], host=host, log=log), 0)
        self.assertIn("hx done was not run", log.lines[-1])


class ReapTests(unittest.TestCase):
    def plan(self, fake=None, procs=None, **config):
        fake = fake or FakeHost()
        return fake, hx_reap.plan_reap(make_host(fake, procs=procs, **config), 6.0,
                                       tmp_root=self.tmp)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        for name in ("agentic-harness-ops347", "wt-ops400", "unrelated"):
            os.makedirs(os.path.join(self.tmp, name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_classification(self):
        old = {"pid": 5, "bindir": "/x", "datadir": "/home/u/.cache/grok-tmp/ops218/pgdata",
               "age": 7 * 3600.0, "clients": 0}
        young = dict(old, pid=6, age=60.0, datadir="/home/u/.cache/grok-tmp/ops218b/pg")
        busy = dict(old, pid=7, clients=2, datadir="/tmp/pg-busy")
        live = dict(old, pid=8, datadir="/tmp/ops400/pg")
        system = dict(old, pid=9, datadir="/var/lib/postgresql/data")
        fake, plan = self.plan(procs=FakeProcs(postmasters=[old, young, busy, live, system]))
        targets = {(a.kind, a.target.split(" ")[0]) for a in plan.actions}
        self.assertIn(("workspace", "w34"), targets)
        self.assertIn(("workspace", "w36"), targets)
        self.assertIn(("workspace", "w2V"), targets)  # qa-QUEUE3 bare shell
        self.assertNotIn(("workspace", "w4"), targets)
        self.assertNotIn(("workspace", "w50"), targets)  # live
        self.assertNotIn(("workspace", "w51"), targets)  # not a launcher pane
        self.assertIn(("worktree", "/srv/wt/app-ops-347"), targets)
        self.assertIn(("worktree", "/srv/wt/app-ops-227"), targets)
        self.assertNotIn(("worktree", "/srv/wt/app-ops-400"), targets)
        self.assertIn(("prune", CO), targets)
        self.assertIn(("checkout", CO), targets)
        self.assertIn(("checkout", HARNESS), targets)
        pg = [a.argv for a in plan.actions if a.kind == "postgres"]
        self.assertEqual(pg, [["kill", "-INT", "5"]])
        boxes = [a.target for a in plan.actions if a.kind == "container"]
        self.assertEqual(sorted(boxes), ["pg1894", "redis-ops-347"])
        skipped = {(k, t.split(" ")[0]): r for k, t, r in plan.skipped}
        self.assertEqual(skipped[("worktree", "/srv/wt/app-ops-347-dirty")], "uncommitted changes")
        self.assertIn("shared workspace", skipped[("workspace", "w4")])
        self.assertIn("pull request open", skipped[("container", "pg1999")])
        self.assertTrue(any("agentic-harness-ops347" in n for n in plan.notes))
        self.assertFalse(any("wt-ops400" in n for n in plan.notes))
        self.assertEqual(actions(fake), [])

    def test_report_only_by_default_and_close_acts(self):
        fake = FakeHost()
        log = quiet_log()
        code = hx_reap.main(["--tmp-root", self.tmp], host=make_host(fake), log=log)
        self.assertEqual(code, 0)
        self.assertEqual(actions(fake), [])
        self.assertIn("agent reaper: would close", log.lines[-1])
        posted = []

        def post(argv, check=False):
            posted.append(argv)
            return Result(1)

        log = quiet_log()
        hx_reap.main(["--close", "--chat", "--tmp-root", self.tmp], host=make_host(fake), log=log,
                     post=post)
        ran = actions(fake)
        self.assertIn(["herdr", "workspace", "close", "w34"], ran)
        self.assertNotIn(["herdr", "workspace", "close", "w4"], ran)
        self.assertNotIn(["herdr", "workspace", "close", "w50"], ran)
        self.assertTrue(any("closed" in line for line in log.lines))
        self.assertEqual(posted[0][2:4], ["chat", "post"])
        self.assertIn("chat post failed", log.lines[-1])

    def test_protected_unavailable_and_errors(self):
        fake = FakeHost()
        fake.docker_ok = False
        fake.fail.add(("git", "-C", HARNESS, "worktree", "list", "--porcelain"))
        _, plan = self.plan(fake, protect_workspaces=["w34"])
        self.assertIn(("workspace", "w34 qa-OPS-347", "protected"), plan.skipped)
        self.assertTrue(any("docker unavailable" in n for n in plan.notes))
        self.assertTrue(any("worktree list failed" in n for n in plan.notes))
        fake = FakeHost()
        fake.fail.add(("herdr", "pane", "list"))
        _, plan = self.plan(fake)
        self.assertTrue(any("herdr unavailable" in n for n in plan.notes))
        err = io.StringIO()
        sys.stderr, saved = err, sys.stderr
        try:
            with tempfile.TemporaryDirectory() as tmp:
                bad = Path(tmp, "c.json")
                bad.write_text("[")
                self.assertEqual(hx_reap.main(["--config", str(bad)], log=quiet_log()), 2)
        finally:
            sys.stderr = saved


class HostReadTests(unittest.TestCase):
    def test_unknown_process_state_is_live(self):
        fake = FakeHost()
        fake.fail.add(("herdr", "pane", "process-info", "--pane", "w34:p1"))
        spaces = {s.workspace_id: s for s in cleanup.herdr_state(fake)}
        self.assertTrue(spaces["w34"].panes[0].live)
        self.assertFalse(spaces["w36"].panes[0].live)

    def test_herdr_bad_json(self):
        with self.assertRaises(cleanup.CleanupError):
            cleanup.herdr_state(lambda argv, **_: Result(0, "not json"))

    def test_detached_and_locked_worktrees(self):
        calls = {
            ("git", "-C", "/r", "worktree", "list", "--porcelain"): Result(0, "\n".join([
                "worktree /r", "HEAD a", "branch refs/heads/main", "",
                "worktree /r/d", "HEAD b", "detached", "",
                "worktree /r/l", "HEAD c", "branch refs/heads/x", "locked", "",
            ])),
            ("git", "-C", "/r/d", "status", "--porcelain"): Result(0, ""),
            ("git", "-C", "/r/d", "branch", "-r", "--contains", "HEAD"): Result(0, ""),
        }
        runner = lambda argv, **_: calls.get(tuple(argv), Result(1, "", "x"))  # noqa: E731
        trees = cleanup.worktrees("/r", runner)
        self.assertEqual([t.main for t in trees], [True, False, False])
        plan = cleanup.Plan()
        for tree in trees:
            cleanup.worktree_action(plan, "/r", tree, "t", [], runner)
        self.assertEqual(plan.actions, [])
        self.assertEqual([r for _k, _t, r in plan.skipped],
                         ["detached HEAD not on any remote branch", "locked"])
        plan = cleanup.Plan()
        cleanup.checkout_actions(plan, "/nope", "main", "t", runner)
        self.assertEqual(plan.skipped, [("checkout", "/nope", "git status failed")])
        self.assertEqual(cleanup.current_branch("/r", runner), "")
        with self.assertRaises(cleanup.CleanupError):
            cleanup.worktrees("/missing", runner)

    def test_procs_reads_a_proc_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "uptime").write_text("1000.0 5.0\n")

            def proc(pid, argv, ppid, start, cwd):
                d = root / str(pid)
                d.mkdir()
                (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
                fields = ["S", str(ppid)] + ["0"] * 17 + [str(start)]
                (d / "stat").write_text(f"{pid} (x y) " + " ".join(fields))
                os.symlink(cwd, d / "cwd")

            proc(10, ["/opt/pg/bin/postgres", "-D", "/tmp/ops218/pgdata", "-p", "5"], 1, 100, tmp)
            proc(11, ["postgres: checkpointer"], 10, 100, tmp)
            proc(12, ["postgres: u db [local] idle"], 10, 100, tmp)
            proc(13, ["/usr/bin/zsh"], 1, 100, "/srv/wt/a")
            proc(14, ["/opt/pg/bin/postgres", "-D"], 1, 100, tmp)
            (root / "self").mkdir()
            procs = cleanup.Procs(root, clock_ticks=100)
            pg = procs.postmasters()
            self.assertEqual(len(pg), 1)
            self.assertEqual(pg[0]["clients"], 1)
            self.assertEqual(pg[0]["datadir"], "/tmp/ops218/pgdata")
            self.assertAlmostEqual(pg[0]["age"], 999.0)
            self.assertIn((13, "/srv/wt/a"), procs.cwds())
            self.assertEqual(procs.age_seconds(999), 0.0)
            self.assertEqual(cleanup.Procs(root / "missing", clock_ticks=100).cwds(), [])


class ClientTests(unittest.TestCase):
    def test_jira_status_and_cache(self):
        seen = []

        class Response:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return self.body

        def opener(request, timeout=0):
            seen.append(request)
            if "OPS-2" in request.full_url:
                raise urllib.error.URLError("down")
            return Response(json.dumps({"fields": {"status": {
                "name": "Done", "statusCategory": {"key": "indeterminate"}}}}).encode())

        jira = cleanup.Jira("https://jira.example/", "a@example.org", "t0k", opener)
        self.assertEqual(jira.status("OPS-1"), ("Done", "indeterminate"))
        self.assertEqual(jira.status("OPS-1"), ("Done", "indeterminate"))
        self.assertIsNone(jira.status("OPS-2"))
        self.assertEqual(len(seen), 2)
        self.assertTrue(seen[0].get_header("Authorization").startswith("Basic "))
        self.assertNotIn("t0k", seen[0].full_url)
        self.assertIsNone(cleanup.Jira("", None, None).status("OPS-1"))
        jira = cleanup.Jira.from_env({"jira_base_url": "https://j"}, {"JIRA_EMAIL": "e",
                                                                      "JIRA_API_TOKEN": "t"})
        self.assertEqual(jira.base_url, "https://j")

    def test_github_errors(self):
        gh = cleanup.GitHub(lambda argv, **_: Result(1, "", "auth"))
        with self.assertRaises(cleanup.CleanupError):
            gh.prs_for_key("a/b", "OPS-1")
        with self.assertRaises(cleanup.CleanupError):
            gh.pr_view(1)

    def test_run_and_containers(self):
        self.assertEqual(cleanup.run([sys.executable, "-c", "print('hi')"]).stdout.strip(), "hi")
        self.assertEqual(cleanup.run(["definitely-not-a-command-xyz"]).returncode, 127)
        self.assertEqual(cleanup.run([sys.executable, "-c", "import time; time.sleep(5)"],
                                     timeout=0.2).returncode, 124)

    def test_config_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "cleanup.json")
            path.write_text(json.dumps({"checkouts": ["~/app"], "jira_base_url": "https://j",
                                        "protect_workspaces": ["w4"]}))
            config = cleanup.load_config(path, environ={})
            self.assertTrue(config["checkouts"][0].endswith("app"))
            self.assertEqual(config["protect_workspaces"], ["w4"])
            env = {"HX_CHECKOUTS": "/a" + os.pathsep + "/b", "JIRA_BASE_URL": "https://e"}
            config = cleanup.load_config(path, environ=env)
            self.assertEqual(config["checkouts"], ["/a", "/b"])
            self.assertEqual(config["jira_base_url"], "https://e")
            self.assertEqual(cleanup.load_config(path, environ=env, checkouts=["/c"])["checkouts"], ["/c"])
            path.write_text("[]")
            with self.assertRaises(cleanup.CleanupError):
                cleanup.load_config(path, environ={})
            self.assertEqual(cleanup.default_config_path({"HX_CLEANUP_CONFIG": str(path)}), path)
            self.assertEqual(cleanup.default_config_path({"XDG_CONFIG_HOME": tmp}),
                             Path(tmp, "agentic-os", "cleanup.json"))
            self.assertEqual(cleanup.state_dir({"XDG_STATE_HOME": tmp}), Path(tmp, "agentic-os"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
