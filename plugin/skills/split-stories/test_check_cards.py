"""Tests for check_cards.py (the /split-stories dry run).

    python3 -m unittest discover -s plugin/skills/split-stories
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


m = load(HERE / "check_cards.py", "check_cards")
SPEC = "# Spec\n\n1. **Refuse an empty scope.** x\n2. **Cite a fact.** y\n"


def card(**kw):
    c = {"title": "A", "priority": 2, "scope": ["tools/a.go"],
         "spec_ref": "projects/Demo/spec/s.md#f1-refuse-an-empty-scope", "body": "b"}
    c.update(kw)
    return c


class Cards(unittest.TestCase):
    def test_good_cards_pass(self):
        self.assertEqual(m.check([card()], None, SPEC), [])

    # The guard this skill exists for: a glob reserves its whole prefix.
    def test_globs_are_refused(self):
        for g in ("tools/*.go", "tools/**", "tools/a?.go", "tools/[ab].go", "tools/{a,b}.go"):
            self.assertTrue(m.check([card(scope=[g])]), g)

    def test_directories_are_refused(self):
        self.assertTrue(m.check([card(scope=["tools/"])]))
        self.assertTrue(m.check([card(scope=["."])]))
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "tools").mkdir()
            self.assertTrue(m.check([card(scope=["tools"])], d))
            self.assertEqual(m.check([card(scope=["tools/new.go"])], d), [])

    def test_escaping_paths_are_refused(self):
        for p in ("/etc/x", "../x", "a/../../x", "a\\b"):
            self.assertTrue(m.check([card(scope=[p])]), p)

    def test_empty_scope_is_refused(self):
        self.assertTrue(m.check([card(scope=[])]))
        c = card()
        del c["scope"]
        self.assertTrue(m.check([c]))

    def test_fact_citation_is_checked_against_the_spec(self):
        self.assertTrue(m.check([card(spec_ref="projects/Demo/spec/s.md#f1")], None, SPEC))
        self.assertTrue(m.check([card(spec_ref="projects/Demo/spec/s.md#f1-wrong")], None, SPEC))
        self.assertTrue(m.check([card(spec_ref="projects/Demo/spec/s.md#f9-x")], None, SPEC))
        self.assertTrue(m.check([card(spec_ref="o/r:docs/x.md#f1-y")]))

    def test_shared_file_needs_a_dependency(self):
        a, b = card(title="A"), card(title="B")
        self.assertTrue(m.check([a, b]))
        self.assertEqual(m.check([a, card(title="B", depends_on=["A"])]), [])

    def test_cli_exit_codes(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "c.json"
            f.write_text(json.dumps([card()]))
            self.assertEqual(m.main([str(f)]), 0)
            f.write_text(json.dumps([card(scope=["tools/*.go"])]))
            self.assertEqual(m.main([str(f)]), 1)
            self.assertEqual(m.main([str(f) + "x"]), 2)


if __name__ == "__main__":
    unittest.main()
