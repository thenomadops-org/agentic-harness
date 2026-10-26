"""Lead assignment and handoff tests; herdr is always mocked."""

import contextlib
import datetime
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import hx_lead
import vendors


class LeadTests(unittest.TestCase):
    def env_for(self, tmp):
        routing = Path(tmp) / "routing.yaml"
        source = (hx_lead.ROOT / "org/routing.yaml").read_text(encoding="utf-8")
        routing.write_text(source.replace("lead_vendor: grok", "lead_vendor: claude", 1), encoding="utf-8")
        return {"HX_STATE_DIR": tmp, "HX_ROUTING_FILE": str(routing), "HX_HERDR": "/fake/herdr"}

    def test_lock_refuses_without_a_quoted_owner_statement(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self.env_for(tmp)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = hx_lead.lock_main(["--holder", "grok"], environ=env)
            self.assertEqual(code, 1)
            self.assertIn("quoted owner statement", err.getvalue())
            self.assertFalse((Path(tmp) / "lead.md").exists())
            self.assertIn("lead_vendor: claude", Path(env["HX_ROUTING_FILE"]).read_text())

    def test_lock_refuses_unquoted_owner_statement_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self.env_for(tmp)
            with self.assertRaisesRegex(hx_lead.LeadError, "quoted owner statement"):
                hx_lead.lock_lead("grok", "Bo holds lead", environ=env)
            self.assertFalse((Path(tmp) / "lead.md").exists())
            self.assertIn("lead_vendor: claude", Path(env["HX_ROUTING_FILE"]).read_text())

    def test_lock_records_holder_time_and_exact_owner_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self.env_for(tmp)
            now = datetime.datetime(2026, 10, 26, 18, 0, tzinfo=datetime.timezone.utc)
            path = hx_lead.lock_lead(
                "grok", '"Bo holds the lead role per design v3"',
                environ=env, now=now,
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("Holder: `grok`", text)
            self.assertIn("Recorded at: `2026-10-26T18:00:00Z`", text)
            self.assertIn("Named by: Chris", text)
            self.assertIn('Owner statement: "Bo holds the lead role per design v3"', text)
            self.assertIn("lead_vendor: grok", Path(env["HX_ROUTING_FILE"]).read_text())
            plan = vendors.plan_session(
                "lead", "OPS-337", ["claude", "grok", "codex"],
                usage={"grok": 0.10, "claude": 0.8, "codex": 0.8},
                routing_path=env["HX_ROUTING_FILE"],
            )
            self.assertEqual(plan["vendor"], "grok")
            self.assertFalse(plan["rebalanced"])
            self.assertTrue(plan["below_floor"])

    def test_brief_reads_the_exact_assignment_without_changing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self.env_for(tmp)
            path = hx_lead.lock_lead("grok", '"Bo holds the lead role"', environ=env)
            before = path.read_bytes()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(hx_lead.main(["brief"], environ=env), 0)
            self.assertEqual(out.getvalue(), before.decode())
            self.assertEqual(path.read_bytes(), before)

    def test_handoff_round_trip_to_grok_pane_preserves_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self.env_for(tmp)
            path = hx_lead.lock_lead(
                "grok", '"Bo holds the lead role per design v3"', environ=env,
                now=datetime.datetime(2026, 10, 26, tzinfo=datetime.timezone.utc),
            )
            original = path.read_bytes()
            listed = subprocess.CompletedProcess(
                ["herdr", "agent", "list"], 0,
                stdout=json.dumps({"result": {"agents": [
                    {"vendor": "grok", "name": "engineer-OPS-337", "pane_id": "pane-grok-7"},
                ]}}), stderr="",
            )
            calls = []

            def fake_run(argv, **kwargs):
                calls.append((argv, kwargs))
                if argv[-2:] == ["agent", "list"]:
                    return listed
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with patch.object(Path, "is_file", return_value=True), \
                 patch("os.access", return_value=True), \
                 patch("subprocess.run", side_effect=fake_run):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(hx_lead.main(["handoff", "--to", "grok"], environ=env), 0)
                brief = io.StringIO()
                with contextlib.redirect_stdout(brief):
                    self.assertEqual(hx_lead.main(["brief"], environ=env), 0)

            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][0], ["/fake/herdr", "agent", "list"])
            self.assertEqual(calls[1][0][0:4], ["/fake/herdr", "agent", "prompt", "pane-grok-7"])
            self.assertIn("Owner statement: \"Bo holds the lead role per design v3\"", calls[1][0][4])
            self.assertIn("holder unchanged", out.getvalue())
            self.assertEqual(brief.getvalue().encode(), original)
            self.assertEqual(path.read_bytes(), original)

    def test_handoff_refuses_ambiguous_vendor_panes(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self.env_for(tmp)
            hx_lead.lock_lead("grok", '"Bo holds the lead role"', environ=env)
            listed = subprocess.CompletedProcess(
                [], 0, stdout=json.dumps({"agents": [
                    {"agent": "grok", "pane_id": "pane-one"},
                    {"agent": "grok", "pane_id": "pane-two"},
                ]}), stderr="",
            )
            with patch.object(Path, "is_file", return_value=True), \
                 patch("os.access", return_value=True), \
                 patch("subprocess.run", return_value=listed) as run:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code = hx_lead.main(["handoff", "--to", "grok"], environ=env)
            self.assertEqual(code, 1)
            self.assertIn("multiple grok panes", err.getvalue())
            run.assert_called_once()

    def test_handoff_dry_run_resolves_a_pane_without_prompting(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self.env_for(tmp)
            hx_lead.lock_lead("grok", '"Bo holds the lead role"', environ=env)
            listed = subprocess.CompletedProcess(
                [], 0, stdout=json.dumps({"agents": [
                    {"agent": "grok", "pane_id": "pane-grok-7"},
                ]}), stderr="",
            )
            with patch.object(Path, "is_file", return_value=True), \
                 patch("os.access", return_value=True), \
                 patch("subprocess.run", return_value=listed) as run:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(
                        hx_lead.main(["handoff", "--to", "grok", "--dry-run"], environ=env), 0
                    )
            self.assertEqual(run.call_count, 1)
            self.assertIn("pane-grok-7", out.getvalue())
            self.assertIn("Bo holds the lead role", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
