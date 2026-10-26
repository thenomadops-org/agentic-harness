"""The vault lint judges the home directory only after this vault is installed.

Run from the repo root:

    python3 tools/test_lint.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.vault = os.path.join(cls._tmp.name, "vault")
        shutil.copytree(os.path.join(ROOT, "vault-seed"), cls.vault)
        completed = subprocess.run(
            [
                sys.executable, os.path.join(ROOT, "tools", "render.py"),
                "--principal", "owner",
                "--packs", "core,engineering",
                "--vault", cls.vault, "--out", cls.vault,
                "--today", "2026-01-01",
            ],
            cwd=ROOT, capture_output=True, text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr or completed.stdout)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_a_host_skill_directory_does_not_fail_an_uninstalled_vault(self):
        # The home directory can hold its own skills. Until a link points at
        # this vault, those entries are not this vault's install. Removing
        # the "not installed" skip reports them as skills outside the vault.
        with tempfile.TemporaryDirectory() as home:
            synced = os.path.join(home, ".claude", "skills", "synced")
            os.makedirs(synced)
            with open(os.path.join(synced, "SKILL.md"), "w", encoding="utf-8") as handle:
                handle.write("host skill\n")
            code, output = _lint(home, self.vault)
            self.assertNotIn("skills outside the vault", output)
            self.assertIn("not installed into the home directory", output)
            self.assertEqual(code, 0)

    def test_a_sibling_directory_is_not_this_vault(self):
        # "<vault>-other" starts with the vault path. Without a path separator
        # that link would count as this install and the host directory would fail.
        sibling = self.vault + "-other"
        os.makedirs(os.path.join(sibling, "skill"))
        try:
            with tempfile.TemporaryDirectory() as home:
                skills = os.path.join(home, ".claude", "skills")
                os.makedirs(os.path.join(skills, "synced"))
                os.symlink(os.path.join(sibling, "skill"), os.path.join(skills, "skill"))
                code, output = _lint(home, self.vault)
                self.assertNotIn("skills outside the vault", output)
                self.assertEqual(code, 0)
        finally:
            shutil.rmtree(sibling)

    def test_a_real_skill_still_fails_once_this_vault_is_linked(self):
        with tempfile.TemporaryDirectory() as home:
            skills = os.path.join(home, ".claude", "skills")
            os.makedirs(os.path.join(skills, "synced"))
            source = os.path.join(self.vault, ".claude", "skills", "install-org")
            os.symlink(source, os.path.join(skills, "install-org"))
            code, output = _lint(home, self.vault)
            self.assertIn("skills outside the vault", output)
            self.assertIn("synced  (not a symlink)", output)
            self.assertNotEqual(code, 0)


def _lint(home, vault):
    env = os.environ.copy()
    env["CLAUDE_HOME"] = home
    env["HOME"] = home
    completed = subprocess.run(
        [sys.executable, os.path.join(vault, "lint_vault.py")],
        cwd=vault,
        env=env,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout + completed.stderr


if __name__ == "__main__":
    unittest.main()
