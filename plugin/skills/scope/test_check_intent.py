"""Tests for check_intent.py (the /scope dry run).

    python3 -m unittest discover -s plugin/skills/scope
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


m = load(HERE / "check_intent.py", "check_intent")
GOOD = "# Portable workforce\n\nThe owner wants any node to run the org's work without hand-holding.\n"


class Intent(unittest.TestCase):
    def test_good_page_passes_and_payloads_cite_the_page(self):
        self.assertEqual(m.check(GOOD, "Demo", "workforce", "Workforce intent"), [])
        card = m.payloads(GOOD, "Demo", "workforce", "T")[1]["args"]
        self.assertEqual(card["kind"], "intent")
        self.assertEqual(card["spec_ref"], "projects/Demo/intent/workforce.md#portable-workforce")

    def test_numbered_facts_are_refused(self):
        errs = m.check(GOOD + "1. **A fact.** x\n", "Demo", "w", "T")
        self.assertTrue(any("spec" in e for e in errs))

    def test_empty_intent_is_refused(self):
        self.assertTrue(m.check("# Only a heading\n", "Demo", "w", "T"))

    def test_bad_slug_and_missing_heading(self):
        self.assertTrue(m.check(GOOD, "Demo", "Bad Slug", "T"))
        self.assertTrue(m.check("no heading here at all, just words\n", "Demo", "w", "T"))

    def test_heading_the_board_cannot_cite_is_refused(self):
        self.assertTrue(m.check("# The goal: fast\n\nwords words words words words\n", "Demo", "w", "T"))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "i.md"
            f.write_text(GOOD)
            self.assertEqual(m.main([str(f), "--project", "Demo", "--page", "w", "--title", "T"]), 0)
            self.assertEqual(m.main([str(f), "--project", "Demo", "--page", "W", "--title", "T"]), 1)
            self.assertEqual(m.main([str(f) + "x"]), 2)


if __name__ == "__main__":
    unittest.main()
