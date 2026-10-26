"""Tests for boundary_gate.py. Each runs the hook as Claude Code does: JSON on
stdin, exit code and stderr out, against a throwaway git repository that holds
a copy of the real tools/check_public.py.

    python3 -m unittest discover -s plugin/hooks/boundary
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
GATE = HERE / "boundary_gate.py"
TOOLS = HERE.parents[2] / "tools"


def run_hook(command, cwd, tool="Bash"):
    payload = json.dumps({"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd)})
    return subprocess.run([sys.executable, str(GATE)], input=payload, text=True, capture_output=True)


def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   cwd=repo, check=True, capture_output=True)


class Repo:
    def __init__(self, test, publishable=True, with_check=True):
        self.path = pathlib.Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, self.path, True)
        git(self.path, "init", "-q")
        if publishable:
            (self.path / ".public-boundary.yaml").write_text("version: 1\ndeny:\n  - forbidden-name\n")
        if with_check:
            (self.path / "tools").mkdir()
            for f in ("check_public.py", "miniyaml.py"):
                shutil.copy(TOOLS / f, self.path / "tools" / f)

    def stage(self, text):
        (self.path / "notes.md").write_text(text)
        git(self.path, "add", "notes.md")


class BoundaryGate(unittest.TestCase):
    def test_commit_blocked_when_staged_change_leaks(self):
        r = Repo(self); r.stage("hello forbidden-name\n")
        out = run_hook("git commit -m x", r.path)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("boundary check failed", out.stderr)

    def test_commit_allowed_when_staged_change_is_clean(self):
        r = Repo(self); r.stage("hello world\n")
        out = run_hook("git commit -m x", r.path)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_push_blocked_on_whole_tree_leak(self):
        r = Repo(self); r.stage("hello forbidden-name\n")
        out = run_hook("git push origin main", r.path)
        self.assertEqual(out.returncode, 2, out.stderr)

    def test_flags_and_chaining_do_not_hide_the_commit(self):
        r = Repo(self); r.stage("forbidden-name\n")
        for cmd in ("git -c user.name=a commit -m x",
                    "git add -A && git commit -m x",
                    "if true; then git commit -m x; fi",
                    "GIT_AUTHOR_NAME=a git push"):
            self.assertEqual(run_hook(cmd, r.path).returncode, 2, cmd)
        self.assertEqual(run_hook("git -C %s commit -m x" % r.path, "/").returncode, 2)

    def test_private_repo_is_not_gated(self):
        r = Repo(self, publishable=False); r.stage("forbidden-name\n")
        self.assertEqual(run_hook("git commit -m x", r.path).returncode, 0)

    def test_declared_but_no_check_blocks(self):
        r = Repo(self, with_check=False); r.stage("fine\n")
        out = run_hook("git commit -m x", r.path)
        self.assertEqual(out.returncode, 2)
        self.assertIn("no tools/check_public.py", out.stderr)

    def test_other_commands_and_tools_are_not_gated(self):
        r = Repo(self); r.stage("forbidden-name\n")
        self.assertEqual(run_hook("git status", r.path).returncode, 0)
        self.assertEqual(run_hook("echo git commit", r.path).returncode, 0)
        self.assertEqual(run_hook("git commit -m x", r.path, tool="Read").returncode, 0)

    def test_fixing_the_leak_allows_the_commit(self):
        r = Repo(self); r.stage("forbidden-name\n")
        self.assertEqual(run_hook("git commit -m x", r.path).returncode, 2)
        r.stage("clean now\n")
        self.assertEqual(run_hook("git commit -m x", r.path).returncode, 0)


class Registration(unittest.TestCase):
    def test_hooks_json_registers_both_gates_and_the_scripts_exist(self):
        reg = json.loads((HERE.parent / "hooks.json").read_text())
        cmds = [h["args"][0] for e in reg["hooks"]["PreToolUse"] if e["matcher"] == "Bash" for h in e["hooks"]]
        for script in ("hooks/boundary/boundary_gate.py", "hooks/production/production_gate.py"):
            self.assertIn("${CLAUDE_PLUGIN_ROOT}/" + script, cmds)
            self.assertTrue((HERE.parents[1] / script).exists())


if __name__ == "__main__":
    unittest.main()
