"""The launch command plans through vendors.plan_session and runs that argv.

Run from the repo root:

    python3 tools/test_launch.py
"""

import contextlib
import io
import json
import os
import shlex
import stat
import tempfile
import unittest

import launch
import render
import vendors


class LaunchTests(unittest.TestCase):
    def test_launch_runs_the_real_argv_in_the_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            os.makedirs(vault)
            os.makedirs(home)
            code, output, rows = _launch(
                home, vault,
                ["engineer-1", "OPS-347", "build the adapter", "--vault", vault],
                ["grok"],
            )
            self.assertEqual(code, 0)
            plan = vendors.plan_session(
                "engineer-1", "OPS-347", ["grok"], goal="build the adapter",
                vault=os.path.realpath(vault),
            )
            ran = self._pane_run(rows, plan["argv"])
            self.assertEqual(ran["cwd"], os.path.realpath(vault))
            self._assert_opened_in_vault(rows, vault)
            self._assert_renamed(rows, plan["pane"])
            self.assertIn("vendor: grok", output)
            self.assertIn("build the adapter", output)
            self.assertFalse(os.path.exists(os.path.join(home, ".claude")))

    def test_goal_with_spaces_and_a_quote_is_one_vendor_argument(self):
        # herdr joins the command tail and runs it through a shell. An unquoted
        # goal is word-split, so "test" arrives as its own vendor argument and
        # the quote characters never do.
        goal = 'build the "adapter" test'
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            os.makedirs(vault)
            os.makedirs(home)
            code, _output, _rows = _launch(
                home, vault,
                ["engineer-1", "OPS-347", goal, "--vault", vault],
                ["grok"],
                through_shell=True,
            )
            self.assertEqual(code, 0)
            plan = vendors.plan_session(
                "engineer-1", "OPS-347", ["grok"], goal=goal,
                vault=os.path.realpath(vault),
            )
            with open(os.path.join(home, "bin", "vendor.jsonl"), encoding="utf-8") as handle:
                vendor_rows = [json.loads(line) for line in handle if line.strip()]
            self.assertEqual(len(vendor_rows), 1)
            received = vendor_rows[0]["argv"][1:]
            self.assertEqual(received, plan["argv"][5:])
            self.assertEqual(received[-1], goal)
            self.assertIn(" ", received[-1])
            self.assertIn('"', received[-1])
            self.assertNotIn("test", received)

    def test_codex_goal_tells_the_session_to_adopt_its_persona_file(self):
        # Codex has no agent flag. The pane shell must still receive one goal
        # argument that names the vault persona file and keeps the real goal.
        goal = 'review the "change"'
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            os.makedirs(vault)
            os.makedirs(home)
            code, _output, _rows = _launch(
                home, vault,
                ["qa", "OPS-347", goal, "--vault", vault],
                ["codex"],
                through_shell=True,
            )
            self.assertEqual(code, 0)
            received = _vendor_args(home)
            persona = os.path.join(
                os.path.realpath(vault), ".claude", "agents", "qa.md",
            )
            self.assertEqual(received[-1].count(persona), 1)
            self.assertIn("Read and adopt", received[-1])
            self.assertIn(goal, received[-1])
            self.assertIn(" ", received[-1])
            self.assertIn('"', received[-1])
            self.assertNotIn("change", received[:-1])
            plan = vendors.plan_session(
                "qa", "OPS-347", ["codex"], goal=goal, vault=os.path.realpath(vault),
            )
            self.assertEqual(received, plan["argv"][5:])

    def test_grok_agent_flag_is_the_vault_persona_file(self):
        # A bare --agent engineer-1 does not load the vault definition.
        # The flag's own file-path form does, so the launched argv must use it.
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            os.makedirs(vault)
            os.makedirs(home)
            code, _output, _rows = _launch(
                home, vault,
                ["engineer-1", "OPS-347", "state your role", "--vault", vault],
                ["grok"],
                through_shell=True,
            )
            self.assertEqual(code, 0)
            received = _vendor_args(home)
            persona = os.path.join(
                os.path.realpath(vault), ".claude", "agents", "engineer-1.md",
            )
            self.assertEqual(received[received.index("--agent") + 1], persona)
            self.assertNotEqual(received[received.index("--agent") + 1], "engineer-1")
            plan = vendors.plan_session(
                "engineer-1", "OPS-347", ["grok"], goal="state your role",
                vault=os.path.realpath(vault),
            )
            self.assertEqual(received, plan["argv"][5:])
            self.assertEqual(plan["argv"][plan["argv"].index("--agent") + 1], persona)

    def test_claude_agent_flag_stays_the_persona_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            os.makedirs(vault)
            os.makedirs(home)
            code, _output, rows = _launch(
                home, vault,
                ["lead", "OPS-347", "state your role", "--vault", vault],
                ["claude"],
            )
            self.assertEqual(code, 0)
            plan = vendors.plan_session(
                "lead", "OPS-347", ["claude"], goal="state your role",
            )
            ran = self._pane_run(rows, plan["argv"])
            agent = ran["argv"][ran["argv"].index("--agent") + 1]
            self.assertEqual(agent, "lead")

    def test_dry_run_prints_the_plan_and_does_not_run_herdr(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            os.makedirs(vault)
            os.makedirs(home)
            code, output, rows = _launch(
                home, vault,
                ["lead", "OPS-347", "state your role", "--vault", vault, "--dry-run"],
                ["claude"],
            )
            self.assertEqual(code, 0)
            self.assertEqual(rows, [])
            self.assertIn("vendor: claude", output)
            self.assertIn("state your role", output)
            self.assertFalse(os.path.exists(os.path.join(home, ".claude")))

    def test_usage_is_passed_to_the_real_planner(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            os.makedirs(vault)
            os.makedirs(home)
            code, _output, rows = _launch(
                home, vault,
                [
                    "engineer-1", "OPS-347", "build it", "--vault", vault,
                    "--usage", "grok=0.0", "--usage", "codex=0.5",
                ],
                ["grok", "codex"],
            )
            self.assertEqual(code, 0)
            plan = vendors.plan_session(
                "engineer-1", "OPS-347", ["grok", "codex"], goal="build it",
                usage={"grok": 0.0, "codex": 0.5},
                vault=os.path.realpath(vault),
            )
            ran = self._pane_run(rows, plan["argv"])
            self.assertEqual(plan["vendor"], "codex")
            self.assertNotEqual(ran["argv"][4], "grok")

    def test_qa_lands_on_a_vendor_other_than_the_builder(self):
        # codex is the preferred QA vendor. With exactly two vendors installed,
        # QA must not take it when it built the change. Widening the
        # "more than one vendor" check past two puts codex back in the argv.
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            os.makedirs(vault)
            os.makedirs(home)
            installed = ["codex", "grok"]
            code, _output, rows = _launch(
                home, vault,
                [
                    "qa", "OPS-347", "check the change", "--vault", vault,
                    "--builder", "codex",
                ],
                installed,
            )
            self.assertEqual(code, 0)
            plan = vendors.plan_session(
                "qa", "OPS-347", installed, goal="check the change",
                builder_vendor="codex",
                vault=os.path.realpath(vault),
            )
            ran = self._pane_run(rows, plan["argv"])
            self.assertEqual(ran["cwd"], os.path.realpath(vault))
            self._assert_opened_in_vault(rows, vault)
            self._assert_renamed(rows, plan["pane"])
            self.assertEqual(plan["vendor"], "grok")
            self.assertNotEqual(plan["vendor"], "codex")
            self.assertNotEqual(ran["argv"][4], "codex")
            self.assertEqual(
                ran["argv"][4:], [shlex.quote(part) for part in plan["argv"][4:]],
            )
            self.assertFalse(os.path.exists(os.path.join(home, ".claude")))

    def test_every_rendered_agent_posts_or_stays_quiet(self):
        with tempfile.TemporaryDirectory() as vault:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(render.main([
                    "--principal", "owner",
                    "--packs", "core,engineering,product,operations",
                    "--vault", vault, "--out", vault, "--today", "2026-01-01",
                ]), 0)
            agents = os.path.join(vault, ".claude", "agents")
            names = sorted(os.listdir(agents))
            self.assertGreaterEqual(len(names), 9)
            for name in names:
                with open(os.path.join(agents, name), encoding="utf-8") as handle:
                    text = handle.read()
                self.assertIn("team-post", text)
                self.assertIn("ready for QA", text)
                self.assertIn("QA pass", text)
                self.assertIn("QA fail", text)
                self.assertIn("blocked", text)
                self.assertIn("say nothing", text)
                lowered = text.lower()
                self.assertNotIn("slack", lowered)
                self.assertNotRegex(lowered, r"tower[0-9]")

    def _pane_run(self, rows, planned):
        # A shebang recorder sees its own path as argv[0]. herdr addresses a
        # pane by the id workspace create returned, so that slot differs from
        # the plan's pane name. The command after it is the plan's argv.
        quoted = [shlex.quote(part) for part in planned[4:]]
        matches = [
            row for row in rows
            if os.path.basename(row["argv"][0]) == planned[0]
            and row["argv"][1:3] == ["pane", "run"]
            and row["argv"][4:] == quoted
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["argv"][3], "pane-1")
        return matches[0]

    def _assert_renamed(self, rows, pane):
        renamed = [row for row in rows if row["argv"][1:3] == ["pane", "rename"]]
        self.assertEqual(len(renamed), 1)
        self.assertEqual(renamed[0]["argv"][3:], ["pane-1", pane])

    def _assert_opened_in_vault(self, rows, vault):
        vault = os.path.realpath(vault)
        opened = [
            row for row in rows
            if row["argv"][1:3] == ["workspace", "create"] and vault in row["argv"]
        ]
        self.assertEqual(len(opened), 1)
        self.assertIn("--cwd", opened[0]["argv"])


def _launch(home, vault, args, vendor_commands, through_shell=False):
    bindir = os.path.join(home, "bin")
    record = _fake_path(bindir, vendor_commands, through_shell=through_shell)
    saved = os.environ.copy()
    os.environ["HOME"] = home
    os.environ["PATH"] = bindir
    os.environ["HERDR_RECORD"] = record
    os.environ["VENDOR_RECORD"] = os.path.join(bindir, "vendor.jsonl")
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            try:
                code = launch.main(args)
            except SystemExit as exc:
                code = exc.code
    finally:
        os.environ.clear()
        os.environ.update(saved)
    rows = []
    if os.path.exists(record):
        with open(record, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    return code, stdout.getvalue(), rows


def _vendor_args(home):
    path = os.path.join(home, "bin", "vendor.jsonl")
    with open(path, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if len(rows) != 1:
        raise AssertionError(f"expected one vendor command, got {rows!r}")
    return rows[0]["argv"][1:]


def _fake_path(bindir, vendor_commands, through_shell=False):
    os.makedirs(bindir)
    record = os.path.join(bindir, "record.jsonl")
    herdr = os.path.join(bindir, "herdr")
    if through_shell:
        # pane run joins the command tail and hands that line to a shell,
        # the same way the real runner sends the line to the pane shell.
        herdr_body = (
            "#!/usr/bin/python3\n"
            "import json, os, subprocess, sys\n"
            "path = os.environ['HERDR_RECORD']\n"
            "with open(path, 'a', encoding='utf-8') as handle:\n"
            "    handle.write(json.dumps({'argv': sys.argv, 'cwd': os.getcwd()}) + '\\n')\n"
            "if sys.argv[1:3] == ['workspace', 'create']:\n"
            "    json.dump({'result': {'root_pane': {'pane_id': 'pane-1'},"
            " 'tab': {'tab_id': 'tab-1'}}}, sys.stdout)\n"
            "    raise SystemExit(0)\n"
            "if sys.argv[1:3] == ['pane', 'rename']:\n"
            "    raise SystemExit(0)\n"
            "if sys.argv[1:3] == ['pane', 'run']:\n"
            "    command = ' '.join(sys.argv[4:])\n"
            "    raise SystemExit(subprocess.call(['/bin/sh', '-c', command]))\n"
            "raise SystemExit(0)\n"
        )
        vendor_body = (
            "#!/usr/bin/python3\n"
            "import json, os, sys\n"
            "path = os.environ['VENDOR_RECORD']\n"
            "with open(path, 'a', encoding='utf-8') as handle:\n"
            "    handle.write(json.dumps({'argv': sys.argv}) + '\\n')\n"
        )
    else:
        herdr_body = (
            "#!/usr/bin/python3\n"
            "import json, os, sys\n"
            "path = os.environ['HERDR_RECORD']\n"
            "with open(path, 'a', encoding='utf-8') as handle:\n"
            "    handle.write(json.dumps({'argv': sys.argv, 'cwd': os.getcwd()}) + '\\n')\n"
            "if 'workspace' in sys.argv and 'create' in sys.argv:\n"
            "    json.dump({'result': {'root_pane': {'pane_id': 'pane-1'},"
            " 'tab': {'tab_id': 'tab-1'}}}, sys.stdout)\n"
        )
        vendor_body = "#!/bin/sh\nexit 0\n"
    with open(herdr, "w", encoding="utf-8") as handle:
        handle.write(herdr_body)
    os.chmod(herdr, os.stat(herdr).st_mode | stat.S_IEXEC)
    for name in vendor_commands:
        path = os.path.join(bindir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(vendor_body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return record


if __name__ == "__main__":
    unittest.main()
