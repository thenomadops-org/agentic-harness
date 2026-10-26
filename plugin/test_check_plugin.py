import json
import pathlib
import shutil
import tempfile
import unittest

import importlib.util

REPO = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_plugin", REPO / "plugin" / "check_plugin.py")
check_plugin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_plugin)


def fixture():
    """A copy of the real plugin inputs, so every case starts from reality."""
    root = pathlib.Path(tempfile.mkdtemp())
    shutil.copytree(REPO / "plugin", root / "plugin", ignore=shutil.ignore_patterns("__pycache__", "*.py"))
    (root / ".claude-plugin").mkdir()
    shutil.copy(REPO / ".claude-plugin/marketplace.json", root / ".claude-plugin/marketplace.json")
    return root


class CheckPlugin(unittest.TestCase):
    def run_check(self, root):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code, census = check_plugin.check(root)
        self.addCleanup(shutil.rmtree, root, True)
        return code, census, out.getvalue()

    # MUST-PASS: the real tree is clean (a checker that fails good input gets switched off)
    def test_real_tree_passes(self):
        code, census, out = self.run_check(fixture())
        self.assertEqual(code, 0, out)
        self.assertGreaterEqual(census["agents"], 6)
        self.assertGreaterEqual(census["skills"], 9)

    # MUST-FAIL cases: each is a way the guard could be hollowed out
    def test_agent_without_description_fails(self):
        r = fixture()
        (r / "plugin/agents/qa.md").write_text("---\nname: qa\n---\n")
        code, _, out = self.run_check(r)
        self.assertEqual(code, 1); self.assertIn("agents/qa.md", out)

    def test_agent_without_frontmatter_fails(self):
        r = fixture()
        (r / "plugin/agents/ghost.md").write_text("no frontmatter\n")
        code, _, out = self.run_check(r)
        self.assertEqual(code, 1); self.assertIn("agents/ghost.md", out)

    def test_zero_agents_is_an_error_not_a_pass(self):
        r = fixture()
        shutil.rmtree(r / "plugin/agents")
        code, census, out = self.run_check(r)
        self.assertEqual(code, 1); self.assertIn("zero agents", out)

    def test_zero_skills_is_an_error(self):
        r = fixture()
        shutil.rmtree(r / "plugin/skills")
        code, _, out = self.run_check(r)
        self.assertEqual(code, 1); self.assertIn("zero skills", out)

    def test_skill_without_frontmatter_fails(self):
        r = fixture()
        (r / "plugin/skills/testing/SKILL.md").write_text("no frontmatter\n")
        code, _, out = self.run_check(r)
        self.assertEqual(code, 1); self.assertIn("skills/testing", out)

    def test_marketplace_pointing_elsewhere_fails(self):
        r = fixture()
        p = r / ".claude-plugin/marketplace.json"
        d = json.loads(p.read_text()); d["plugins"][0]["source"] = "./nowhere"
        p.write_text(json.dumps(d))
        code, _, out = self.run_check(r)
        self.assertEqual(code, 1); self.assertIn("does not point at plugin/", out)

    def test_marketplace_name_mismatch_fails(self):
        r = fixture()
        p = r / ".claude-plugin/marketplace.json"
        d = json.loads(p.read_text()); d["plugins"][0]["name"] = "other"
        p.write_text(json.dumps(d))
        code, _, out = self.run_check(r)
        self.assertEqual(code, 1); self.assertIn("lists no plugin named", out)

    def test_manifest_without_version_fails(self):
        r = fixture()
        p = r / "plugin/.claude-plugin/plugin.json"
        d = json.loads(p.read_text()); del d["version"]
        p.write_text(json.dumps(d))
        code, _, out = self.run_check(r)
        self.assertEqual(code, 1); self.assertIn("name and a version", out)

    def test_missing_manifest_is_exit_2(self):
        r = fixture()
        (r / "plugin/.claude-plugin/plugin.json").unlink()
        code, _, _ = self.run_check(r)
        self.assertEqual(code, 2)

    def test_missing_hooks_dir_fails(self):
        r = fixture()
        shutil.rmtree(r / "plugin/hooks")
        code, _, out = self.run_check(r)
        self.assertEqual(code, 1); self.assertIn("plugin/hooks/", out)


if __name__ == "__main__":
    unittest.main()
