"""Tests for check_spec.py (the /spec dry run).

    python3 -m unittest discover -s plugin/skills/spec
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


m = load(HERE / "check_spec.py", "check_spec")
GOOD = "# Spec\n\n1. **Refuse an empty scope.** It is refused.\n2. **Cite a fact.** Stories cite it.\n"


class Spec(unittest.TestCase):
    def test_good_spec_gives_anchors(self):
        errs, fs = m.check(GOOD)
        self.assertEqual(errs, [])
        self.assertEqual([m.slug(t) for _, t in fs], ["refuse-an-empty-scope", "cite-a-fact"])

    def test_gap_in_numbering_is_refused(self):
        errs, _ = m.check(GOOD.replace("2. **Cite", "3. **Cite"))
        self.assertTrue(any("expected number 2" in e for e in errs))

    def test_reused_number_and_repeated_slug_are_refused(self):
        self.assertTrue(m.check(GOOD.replace("2. **Cite a fact.**", "1. **Other.**"))[0])
        self.assertTrue(m.check(GOOD.replace("Cite a fact", "Refuse an empty scope!"))[0])

    def test_no_facts_is_refused(self):
        self.assertTrue(m.check("# Spec\n\njust prose\n")[0])

    def test_slug_matches_the_daemon_rule(self):
        self.assertEqual(m.slug("Scope is exact, files only."), "scope-is-exact-files-only")
        self.assertEqual(m.slug("日本語 test"), "日本語-test")

    def test_cli_prints_anchors_and_spec_ref(self):
        import contextlib, io
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "s.md"
            f.write_text(GOOD)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = m.main([str(f), "--project", "Demo", "--page", "s"])
            self.assertEqual(code, 0)
            self.assertIn("#f1-refuse-an-empty-scope", out.getvalue())
            self.assertIn("projects/Demo/spec/s.md#f1-refuse-an-empty-scope", out.getvalue())
            self.assertEqual(m.main([str(f) + "x"]), 2)


if __name__ == "__main__":
    unittest.main()
