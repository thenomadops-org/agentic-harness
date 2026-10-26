import contextlib
import importlib.util
import io
import pathlib
import shutil
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
_spec = importlib.util.spec_from_file_location("validate", HERE / "validate.py")
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)

GOOD = """\
board_project: Demo
roles: [engineer, qa]
test: make test
build: make build
staging:
  deploy: a merge to main publishes and rolls the staging workload
  url: https://staging.example.com
  check: curl -fsS https://staging.example.com/version
production:
  commands:
    - kubectl apply
    - helm upgrade
  same_environment_as_staging: false
"""


def project_errors(text):
    return validate.check_project_text(text)


def swap(old, new, text=GOOD):
    assert old in text, old
    return text.replace(old, new)


class ProjectFile(unittest.TestCase):
    # MUST-PASS: good input is accepted, and the repo's own file is good.
    def test_good_file_passes(self):
        self.assertEqual(project_errors(GOOD), [])

    def test_this_repos_file_passes(self):
        code, out = validate.run_project(REPO / ".agentic-os.yaml")
        self.assertEqual(code, 0, out)

    def test_env_reference_url_passes(self):
        self.assertEqual(project_errors(swap("https://staging.example.com\n", "env:STAGING_URL\n")), [])

    # MUST-FAIL: each guard, removed, lets one of these through.
    def test_missing_each_required_key_fails(self):
        for key in ("board_project", "roles", "test", "build", "staging", "production"):
            lines, out, skip = GOOD.split("\n"), [], False
            for ln in lines:
                if ln.startswith(key + ":"):
                    skip = True
                    continue
                if skip and ln.startswith(" "):
                    continue
                skip = False
                out.append(ln)
            errs = project_errors("\n".join(out))
            self.assertTrue(any(key in e for e in errs), (key, errs))

    def test_unknown_key_fails(self):
        self.assertTrue(any("unknown" in e for e in project_errors(GOOD + "bild: typo\n")))

    def test_empty_command_fails(self):
        for k in ("test", "build"):
            errs = project_errors(swap(f"{k}: make {k}", f'{k}: ""'))
            self.assertTrue(any(k in e for e in errs), errs)

    def test_roles_must_be_nonempty_unique_slugs(self):
        for bad in ("roles: []", "roles: [engineer, engineer]", "roles: [Engineer]", "roles: engineer"):
            self.assertTrue(project_errors(swap("roles: [engineer, qa]", bad)), bad)

    def test_staging_fields_required_and_typed(self):
        for old, new in (
            ("  deploy: a merge to main publishes and rolls the staging workload\n", ""),
            ("  check: curl -fsS https://staging.example.com/version\n", ""),
            ("  url: https://staging.example.com\n", ""),
            ("url: https://staging.example.com", "url: ftp://staging.example.com"),
            ("url: https://staging.example.com", "url: staging.example.com"),
            ("url: https://staging.example.com", "url: env:lower"),
            ("deploy: a merge", "deploy: \"\""),
        ):
            self.assertTrue(project_errors(swap(old, new)), (old, new))

    def test_production_must_guard_a_command(self):
        for old, new in (
            ("    - kubectl apply\n    - helm upgrade\n", ""),
            ("    - kubectl apply\n    - helm upgrade\n", "    - \"\"\n"),
            ("    - helm upgrade\n", "    - kubectl apply\n"),
            ("same_environment_as_staging: false", "same_environment_as_staging: maybe"),
            ("  same_environment_as_staging: false\n", ""),
        ):
            self.assertTrue(project_errors(swap(old, new)), (old, new))

    def test_production_commands_is_a_list_of_strings(self):
        self.assertTrue(project_errors(swap("  commands:\n    - kubectl apply\n    - helm upgrade\n", "  commands: kubectl apply\n")))
        self.assertTrue(project_errors(swap("    - helm upgrade", "    - 7")))

    def test_unparseable_yaml_fails(self):
        self.assertTrue(project_errors("board_project: [unclosed\n"))
        self.assertTrue(project_errors("&a x: 1\n"))

    def test_cli_exit_codes(self):
        d = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        (d / "ok.yaml").write_text(GOOD)
        (d / "bad.yaml").write_text(GOOD.replace("test: make test\n", ""))
        self.assertEqual(validate.run_project(d / "ok.yaml")[0], 0)
        self.assertEqual(validate.run_project(d / "bad.yaml")[0], 1)
        self.assertEqual(validate.run_project(d / "absent.yaml")[0], 2)


ENTRY = """\
---
title: A lesson
summary: One line that says what to do differently.
role: engineer
links: [other-lesson.md]
---
Body text.
"""


class MemoryDir(unittest.TestCase):
    def make(self, entries, readme=None):
        d = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        for name, text in entries.items():
            (d / name).write_text(text)
        if readme is None:
            readme = "# Memory\n\n" + "".join(f"- [{n}]({n})\n" for n in entries)
        (d / "README.md").write_text(readme)
        return d

    def errs(self, d):
        return validate.check_memory_dir(d)

    def test_good_dir_passes(self):
        d = self.make({"a-lesson.md": ENTRY, "other-lesson.md": ENTRY})
        self.assertEqual(self.errs(d), [])

    def test_this_repos_memory_passes(self):
        code, out = validate.run_memory(REPO / "docs/memory")
        self.assertEqual(code, 0, out)

    def test_missing_readme_fails(self):
        d = self.make({"a.md": ENTRY})
        (d / "README.md").unlink()
        self.assertTrue(any("README" in e for e in self.errs(d)))

    def test_entry_missing_from_index_fails(self):
        d = self.make({"a.md": ENTRY, "b.md": ENTRY.replace("[other-lesson.md]", "[]")}, readme="# Memory\n- [a](a.md)\n")
        self.assertTrue(any("b.md" in e and "index" in e for e in self.errs(d)))

    def test_index_naming_a_ghost_fails(self):
        d = self.make({"a.md": ENTRY.replace("[other-lesson.md]", "[]")}, readme="# M\n- [a](a.md)\n- [g](ghost.md)\n")
        self.assertTrue(any("ghost.md" in e for e in self.errs(d)))

    def test_each_frontmatter_key_required(self):
        for key in ("title", "summary", "role", "links"):
            text = "\n".join(l for l in ENTRY.split("\n") if not l.startswith(key + ":"))
            d = self.make({"a.md": text})
            self.assertTrue(any(key in e for e in self.errs(d)), key)

    def test_no_frontmatter_fails(self):
        self.assertTrue(self.errs(self.make({"a.md": "just text\n"})))

    def test_dangling_link_fails(self):
        d = self.make({"a.md": ENTRY})  # links to other-lesson.md, which is absent
        self.assertTrue(any("other-lesson.md" in e for e in self.errs(d)))

    def test_bad_filename_fails(self):
        d = self.make({"Bad Name.md": ENTRY.replace("[other-lesson.md]", "[]")})
        self.assertTrue(any("filename" in e for e in self.errs(d)))

    def test_empty_title_or_summary_fails(self):
        d = self.make({"a.md": ENTRY.replace("title: A lesson", 'title: ""').replace("[other-lesson.md]", "[]")})
        self.assertTrue(any("title" in e for e in self.errs(d)))


class Vendored(unittest.TestCase):
    # The plugin installs on its own, so it carries a copy of the YAML reader.
    # A copy that drifts from tools/miniyaml.py is a second, untested parser.
    @unittest.skipUnless((REPO / "tools/miniyaml.py").exists(), "installed plugin: no source tree to compare")
    def test_vendored_reader_matches_the_source(self):
        src = REPO / "tools/miniyaml.py"
        self.assertEqual((HERE / "miniyaml.py").read_bytes(), src.read_bytes())


if __name__ == "__main__":
    unittest.main()
