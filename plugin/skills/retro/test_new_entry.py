"""Tests for new_entry.py (the /retro writer).

    python3 -m unittest discover -s plugin/skills/retro
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


m = load(HERE / "new_entry.py", "new_entry")
INDEX = "# Project memory\n\n## Index\n\n"


def write(d, **kw):
    args = dict(name="a-lesson.md", title="A lesson", summary="Do it differently.", role="engineer",
                links=[], body="It broke; run `make test` to see it (PR 1).")
    args.update(kw)
    return m.write_entry(d, **args)


class Retro(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.tmp.name)
        (self.d / "README.md").write_text(INDEX)

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_entry_and_index_and_validates(self):
        self.assertEqual(write(self.d), (0, []))
        self.assertIn("(a-lesson.md)", (self.d / "README.md").read_text())
        self.assertTrue((self.d / "a-lesson.md").read_text().startswith("---\n"))

    def test_apostrophe_and_colon_survive_quoting(self):
        self.assertEqual(write(self.d, title="Don't: ever"), (0, []))

    def test_dry_run_writes_nothing(self):
        self.assertEqual(write(self.d, dry_run=True), (0, []))
        self.assertFalse((self.d / "a-lesson.md").exists())
        self.assertEqual((self.d / "README.md").read_text(), INDEX)

    def test_bad_link_is_rejected_and_rolled_back(self):
        code, errs = write(self.d, links=["nope.md"])
        self.assertEqual(code, 1)
        self.assertTrue(errs)
        self.assertFalse((self.d / "a-lesson.md").exists())
        self.assertEqual((self.d / "README.md").read_text(), INDEX)

    def test_bad_filename_is_rejected(self):
        self.assertEqual(write(self.d, name="Bad_Name.md")[0], 1)
        self.assertFalse((self.d / "Bad_Name.md").exists())

    def test_no_evidence_is_rejected(self):
        self.assertEqual(write(self.d, body="  ")[0], 1)

    def test_private_names_are_rejected(self):
        self.assertEqual(write(self.d, body="see https://host.tail1234.ts.net/x")[0], 1)
        self.assertEqual(write(self.d, body="in " + "/ho" + "me/someone/Code")[0], 1)

    def test_existing_entry_is_not_overwritten(self):
        write(self.d)
        self.assertEqual(write(self.d)[0], 1)

    def test_missing_dir(self):
        self.assertEqual(write(self.d / "none")[0], 2)


if __name__ == "__main__":
    unittest.main()
