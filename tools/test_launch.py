"""The launch command plans through vendors.plan_session and runs that argv.

Run from the repo root:

    python3 tools/test_launch.py
"""

import contextlib
import io
import json
import os
import re
import shlex
import stat
import tempfile
import tomllib
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

    def test_codex_loads_the_persona_file_as_developer_instructions(self):
        # Codex has no agent flag. It injects -c/--config developer_instructions
        # into the developer message before the user prompt. A goal that only
        # names the persona file does not. The value is parsed as TOML, and a
        # value that fails to parse is kept raw, which can rewrite a file that
        # is itself valid TOML. This fails unless the parsed override equals
        # the persona file.
        goal = 'review the "change"'
        body = (
            '# persona qa\n'
            'You are "qa".\n'
            "Don't drop this: PERSONA_BODY_MARKER_347\n"
        )
        decoy = "DECOY_AGENTS_NOT_THE_PERSONA\n"
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            os.makedirs(vault)
            os.makedirs(home)
            _write_persona(vault, "qa", body)
            with open(os.path.join(vault, "AGENTS.md"), "w", encoding="utf-8") as handle:
                handle.write(decoy)
            code, _output, _rows = _launch(
                home, vault,
                ["qa", "OPS-347", goal, "--vault", vault],
                ["codex"],
                through_shell=True,
            )
            self.assertEqual(code, 0)
            received = _vendor_args(home)
            loaded, used_raw = _codex_developer_instructions(received)
            self.assertFalse(used_raw)
            self.assertEqual(loaded, body)
            self.assertNotIn(decoy.strip(), loaded)
            self.assertEqual(received[-1], goal)
            self.assertIn(" ", received[-1])
            self.assertIn('"', received[-1])
            self.assertNotIn("change", received[:-1])
            with open(os.path.join(vault, "AGENTS.md"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), decoy)
            self.assertFalse(os.path.exists(os.path.join(home, ".claude")))
            self.assertFalse(os.path.exists(os.path.join(home, ".codex")))
            plan = vendors.plan_session(
                "qa", "OPS-347", ["codex"], goal=goal, vault=os.path.realpath(vault),
            )
            self.assertEqual(received, plan["argv"][5:])

    def test_codex_persona_survives_the_terminal_line_limit(self):
        # A pane shell in canonical mode keeps 4095 bytes of one line and
        # discards the rest. Inlining the persona makes that line longer, so
        # the shell runs a cut command and returns without an answer. The
        # marker sits at the end, where the cut lands. A goal that begins
        # with "-" is an option unless it follows "--". The shell reads a
        # staged argument and removes that file before the vendor starts.
        # The file is still there when this launch returns if the command
        # only cats it.
        goal = "-report the role id"
        body = (
            'You are "qa".\n'
            + ("persona line stays in the file.\n" * 300)
            + "MARKER_AT_END_347\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            stage = os.path.join(tmp, "stage")
            os.makedirs(vault)
            os.makedirs(home)
            os.makedirs(stage)
            _write_persona(vault, "qa", body)
            previous_tmpdir = os.environ.get("TMPDIR")
            previous_tempdir = tempfile.tempdir
            os.environ["TMPDIR"] = stage
            # tempfile caches the first directory it uses. Clear that so this
            # launch writes the staged argument under stage.
            tempfile.tempdir = None
            try:
                code, _output, rows = _launch(
                    home, vault,
                    ["qa", "OPS-347", goal, "--vault", vault],
                    ["codex"],
                    through_shell=True,
                )
            finally:
                tempfile.tempdir = previous_tempdir
                if previous_tmpdir is None:
                    os.environ.pop("TMPDIR", None)
                else:
                    os.environ["TMPDIR"] = previous_tmpdir
            self.assertEqual(code, 0)
            typed = _typed_command(rows)
            self.assertLessEqual(len(typed.encode()), 4095)
            staged = _staged_persona_paths(typed)
            self.assertTrue(staged, typed)
            for path in staged:
                self.assertFalse(
                    os.path.exists(path),
                    f"staged file still exists after the pane command: {path}",
                )
                self.assertIn(f"/bin/rm {path}", typed)
                self.assertLess(typed.index(f"/bin/rm {path}"), typed.index(" codex "))
            self.assertEqual(os.listdir(stage), [])
            received = _vendor_args(home)
            loaded, used_raw = _codex_developer_instructions(received)
            self.assertFalse(used_raw)
            self.assertEqual(loaded, body)
            self.assertEqual(received[received.index("--") + 1], goal)
            self.assertFalse(os.path.exists(os.path.join(home, ".codex")))

    def test_codex_launch_fails_when_the_persona_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = os.path.join(tmp, "vault")
            home = os.path.join(tmp, "home")
            os.makedirs(vault)
            os.makedirs(home)
            code, _output, rows = _launch(
                home, vault,
                ["qa", "OPS-347", "review it", "--vault", vault],
                ["codex"],
                through_shell=True,
            )
            self.assertNotEqual(code, 0)
            self.assertEqual(rows, [])
            self.assertFalse(os.path.exists(os.path.join(home, "bin", "vendor.jsonl")))

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
            _write_persona(vault, "engineer-1", "You are engineer-1.\n")
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
                self.assertIn("no-tracker:", text)
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


def _write_persona(vault, persona, body):
    directory = os.path.join(vault, ".claude", "agents")
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, persona + ".md"), "w", encoding="utf-8") as handle:
        handle.write(body)


def _codex_developer_instructions(argv):
    """Return (text, used_raw) for Codex's last developer_instructions override.

    Codex parses the value of -c/--config as TOML and uses the raw string only
    when that parse fails. Unknown keys are ignored, so a prefix in the user
    prompt does not count as a loaded persona.
    """
    found = None
    index = 0
    while index < len(argv):
        if argv[index] in ("-c", "--config") and index + 1 < len(argv):
            key, sep, raw = argv[index + 1].partition("=")
            if sep and key == "developer_instructions":
                try:
                    found = (tomllib.loads("v = " + raw)["v"], False)
                except (tomllib.TOMLDecodeError, KeyError):
                    found = (raw, True)
            index += 2
            continue
        index += 1
    if found is None:
        raise AssertionError("Codex developer_instructions were not loaded")
    return found


def _staged_persona_paths(typed):
    """Return absolute paths the pane command reads with /bin/cat."""
    return re.findall(r"/bin/cat (/[A-Za-z0-9_./-]+)", typed)


def _typed_command(rows):
    runs = [row for row in rows if row["argv"][1:3] == ["pane", "run"]]
    if len(runs) != 1:
        raise AssertionError(f"expected one pane run, got {runs!r}")
    return " ".join(runs[0]["argv"][4:])


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
            # A canonical terminal line holds 4095 bytes. The rest is discarded
            # and the shell still executes what arrived.
            "    raw = command.encode()\n"
            "    if len(raw) > 4095:\n"
            "        command = raw[:4095].decode('utf-8', 'ignore')\n"
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
