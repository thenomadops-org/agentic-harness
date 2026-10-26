"""Tests for check_promote.py (the /promote-lessons dry run).

    python3 -m unittest discover -s plugin/skills/promote-lessons
"""
import importlib.util
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = load(HERE / "check_promote.py", "check_promote")


class Promote(unittest.TestCase):
    def test_lessons_only_passes(self):
        self.assertEqual(m.check(["plugin/lessons/a-rule.md", "plugin/lessons/README.md"]), [])

    def test_anything_else_is_refused(self):
        for p in ("plugin/skills/x/SKILL.md", "plugin/lessons/sub/a.md", "plugin/lessons/a.py",
                  "docs/memory/a.md", "plugin/lessons", "plugin/lessonsx/a.md", "../plugin/lessons/a.md"):
            self.assertTrue(m.check([p]), p)

    def test_mixed_set_is_refused(self):
        self.assertTrue(m.check(["plugin/lessons/a.md", "tools/x.go"]))

    def test_empty_set_is_refused(self):
        self.assertTrue(m.check([]))

    def test_private_names_in_a_lesson_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "plugin/lessons"
            p.mkdir(parents=True)
            (p / "a.md").write_text("see https://box.tailnet1.ts.net/mcp\n")
            self.assertTrue(m.check(["plugin/lessons/a.md"], d))
            (p / "a.md").write_text("a clean rule\n")
            self.assertEqual(m.check(["plugin/lessons/a.md"], d), [])

    def test_cli_exit_codes(self):
        self.assertEqual(m.main(["plugin/lessons/a.md"]), 0)
        self.assertEqual(m.main(["tools/x.go"]), 1)


if __name__ == "__main__":
    unittest.main()
