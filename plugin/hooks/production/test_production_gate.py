"""Tests for production_gate.py. Each runs the hook as Claude Code does: JSON on
stdin, exit code and stderr out.

    python3 -m unittest discover -s plugin/hooks/production
"""
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("production_gate", HERE / "production_gate.py")
production_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(production_gate)
GATE = HERE / "production_gate.py"


class ProductionGate(unittest.TestCase):
    def setUp(self):
        self.repo = pathlib.Path(tempfile.mkdtemp())
        self.home = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo, True)
        self.addCleanup(shutil.rmtree, self.home, True)
        (self.repo / ".git").mkdir()

    def project(self, production_yaml):
        (self.repo / ".agentic-os.yaml").write_text("board_project: X\n" + production_yaml)

    def hook(self, command, env=None, tool="Bash"):
        e = {k: v for k, v in os.environ.items() if k != "AGENTIC_OS_PRODUCTION_OVERRIDE"}
        e["AGENTIC_OS_OVERRIDE_DIR"] = str(self.home)
        e.update(env or {})
        payload = json.dumps({"tool_name": tool, "tool_input": {"command": command}, "cwd": str(self.repo)})
        return subprocess.run([sys.executable, str(GATE)], input=payload, text=True, capture_output=True, env=e)

    def record(self, **kw):
        rec = {"granted_by": "owner", "repo": str(self.repo),
               "expires_at": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()}
        rec.update(kw)
        (self.home / "production-override.json").write_text(json.dumps(rec))

    def test_matching_command_is_blocked(self):
        self.project("production:\n  commands:\n    - kubectl apply\n  same_environment_as_staging: true\n")
        out = self.hook("kubectl apply -f prod.yaml")
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("owner", out.stderr)

    def test_non_matching_command_is_allowed(self):
        self.project("production:\n  commands:\n    - kubectl apply\n  same_environment_as_staging: true\n")
        self.assertEqual(self.hook("kubectl get pods").returncode, 0)

    def test_mixed_case_command_is_blocked_by_lowercase_pattern(self):
        # gh resolves workflow names case-insensitively (AOS-347, spec F8).
        self.project("production:\n  commands:\n    - promote\n  same_environment_as_staging: true\n")
        out = self.hook("gh workflow run Promote -f target=production")
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertEqual(self.hook("gh workflow run PROMOTE").returncode, 2)

    def test_lowercase_command_is_blocked_by_mixed_case_pattern(self):
        self.project("production:\n  commands:\n    - Promote\n  same_environment_as_staging: true\n")
        out = self.hook("gh workflow run promote -f target=production")
        self.assertEqual(out.returncode, 2, out.stderr)

    def test_env_override_allows(self):
        self.project("production:\n  commands:\n    - kubectl apply\n  same_environment_as_staging: true\n")
        self.assertEqual(self.hook("kubectl apply -f x", env={"AGENTIC_OS_PRODUCTION_OVERRIDE": "owner"}).returncode, 0)

    def test_recorded_override_allows(self):
        self.project("production:\n  commands:\n    - kubectl apply\n  same_environment_as_staging: true\n")
        self.record()
        self.assertEqual(self.hook("kubectl apply -f x").returncode, 0)

    def test_override_must_be_the_owners_unexpired_and_for_this_repo(self):
        self.project("production:\n  commands:\n    - kubectl apply\n  same_environment_as_staging: true\n")
        past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)).isoformat()
        for bad in ({"granted_by": "builder"}, {"expires_at": past}, {"repo": "/somewhere/else"}):
            self.record(**bad)
            self.assertEqual(self.hook("kubectl apply -f x").returncode, 2, bad)
        (self.home / "production-override.json").write_text("not json")
        self.assertEqual(self.hook("kubectl apply -f x").returncode, 2)

    def test_command_naming_the_override_record_is_blocked(self):
        self.project("production:\n  commands:\n    - kubectl apply\n  same_environment_as_staging: true\n")
        out = self.hook("echo '{}' > ~/.agentic-os/production-override.json")
        self.assertEqual(out.returncode, 2)

    def test_only_the_commands_list_gates(self):
        self.project("production:\n  note: kubectl get\n  commands:\n    - helm upgrade\n  same_environment_as_staging: true\n")
        self.assertEqual(self.hook("kubectl get pods").returncode, 0)
        self.assertEqual(self.hook("make test || true").returncode, 0)
        self.assertEqual(self.hook("helm upgrade x").returncode, 2)

    def test_missing_empty_or_odd_file_gates_nothing(self):
        self.assertEqual(self.hook("kubectl apply -f x").returncode, 0)  # no file
        self.project("roles: [a]\n")
        self.assertEqual(self.hook("kubectl apply -f x").returncode, 0)  # no field
        self.project("production:\ntest: make\n")
        self.assertEqual(self.hook("make").returncode, 0)  # empty field, next key ignored
        (self.repo / ".agentic-os.yaml").write_bytes(b"\xff\xfe\x00")
        self.assertEqual(self.hook("kubectl apply").returncode, 0)

    def test_other_tools_are_not_gated(self):
        self.project("production:\n  commands:\n    - kubectl apply\n  same_environment_as_staging: true\n")
        self.assertEqual(self.hook("kubectl apply", tool="Read").returncode, 0)


if __name__ == "__main__":
    unittest.main()


class SchemaShapeTests(unittest.TestCase):
    """AOS-286 published shape: production.commands (literal substrings) plus
    same_environment_as_staging (bool, never a pattern)."""

    DOC = (
        "board_project: X\n"
        "production:\n"
        "  commands:\n"
        "    - kubectl apply\n"
        "    - kubectl set image\n"
        "  same_environment_as_staging: true\n"
        "staging:\n"
        "  url: env:URL\n"
    )

    def test_only_commands_are_patterns(self):
        self.assertEqual(production_gate.read_patterns(self.DOC), ["kubectl apply", "kubectl set image"])

    def test_bool_sibling_never_gates(self):
        pats = production_gate.read_patterns(self.DOC)
        self.assertFalse(any(production_gate.matches(p, "make test || true") for p in pats))

    def test_literal_not_regex(self):
        self.assertFalse(production_gate.matches("kubectl.apply", "kubectlXapply"))
        self.assertTrue(production_gate.matches("kubectl apply", "ssh h 'kubectl apply -f x'"))

    def test_match_ignores_case_both_ways(self):
        self.assertTrue(production_gate.matches("promote", "gh workflow run Promote"))
        self.assertTrue(production_gate.matches("Promote", "gh workflow run promote"))
        self.assertFalse(production_gate.matches("promote", "gh workflow run demote"))
