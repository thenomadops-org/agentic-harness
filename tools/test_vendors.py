"""Vendor adapters, routing, and the one shared memory store.

Run from the repo root:

    python3 tools/test_vendors.py
"""

import contextlib
import io
import os
import pathlib
import tempfile
import textwrap
import unittest

import miniyaml
import setup
import update
import vendors


ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLED = ["claude", "codex", "grok"]


def _write(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(textwrap.dedent(text).lstrip("\n"))
    return path


class VendorTests(unittest.TestCase):
    def test_shipped_adapters_cover_each_cli(self):
        catalog = vendors.load_vendors()
        by_id = {record["id"]: record for record in catalog["vendors"]}
        self.assertEqual(list(by_id), ["claude", "codex", "grok"])
        for record in by_id.values():
            self.assertEqual(record["model_flag"], "--model")
            self.assertTrue(record["command"])
            self.assertTrue(record["memory_link"])
        self.assertEqual(by_id["claude"]["command"], "claude")
        self.assertEqual(by_id["claude"]["agent_flag"], "--agent")
        self.assertEqual(by_id["claude"]["session_flag"], "-n")
        self.assertEqual(by_id["codex"]["command"], "codex")
        self.assertIsNone(by_id["codex"]["agent_flag"])
        self.assertEqual(by_id["grok"]["command"], "grok")
        self.assertEqual(by_id["grok"]["agent_flag"], "--agent")

        postures = miniyaml.load(ROOT / "org" / "roles.yaml")["budget_postures"]
        self.assertEqual(by_id["claude"]["models"], postures)

        source = pathlib.Path(vendors.__file__).read_text(encoding="utf-8")
        for literal in ("opus", "gpt-6-sol", "grok-4.7", "subprocess", "os.system"):
            self.assertNotIn(literal, source)

    def test_adding_a_vendor_is_a_data_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            vendors_path = _write(tmp, "vendors.yaml", """
                version: 1
                vendors:
                  - id: stub
                    command: stubcli
                    model_flag: "--model"
                    agent_flag: null
                    session_flag: null
                    memory_link: ".stub/memory"
                    models:
                      frugal: { lead: stub-lead, specialist: stub-spec, ic: stub-ic }
                      balanced: { lead: stub-lead, specialist: stub-spec, ic: stub-ic }
                      max: { lead: stub-lead, specialist: stub-spec, ic: stub-ic }
            """)
            routing_path = _write(tmp, "routing.yaml", """
                version: 1
                lead_vendor: stub
                build_vendors: [stub]
                build_personas: [engineer, ios-engineer, android-engineer, devops]
                qa_persona: qa
                qa_vendors: [stub]
                usage_rebalance_below: 0.15
                memory_store: memory
            """)
            plan = vendors.plan_session(
                "lead", "OPS-347", ["stub"],
                vendors_path=vendors_path, routing_path=routing_path,
            )
            self.assertEqual(plan["vendor"], "stub")
            self.assertEqual(plan["model"], "stub-lead")
            self.assertEqual(plan["pane"], "lead-OPS-347")
            self.assertEqual(
                plan["argv"],
                ["herdr", "pane", "run", "lead-OPS-347", "stubcli", "--model", "stub-lead"],
            )
            self.assertNotIn("stubcli", pathlib.Path(vendors.__file__).read_text(encoding="utf-8"))

            vault = os.path.join(tmp, "vault")
            os.makedirs(vault)
            vendors.bind_shared_memory(vault, vendors_path=vendors_path, routing_path=routing_path)
            link = os.path.join(vault, ".stub", "memory")
            self.assertTrue(os.path.islink(link))
            with open(os.path.join(link, "note.md"), "w", encoding="utf-8") as handle:
                handle.write("from-stub\n")
            with open(os.path.join(vault, "memory", "note.md"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "from-stub\n")

    def test_lead_vendor_is_the_configured_name(self):
        routing = vendors.load_routing()
        self.assertEqual(routing["lead_vendor"], "claude")
        self.assertEqual(routing["usage_rebalance_below"], 0.15)

        plan = vendors.plan_session("lead", "OPS-347", INSTALLED, posture="balanced")
        self.assertEqual(plan["vendor"], "claude")
        self.assertEqual(plan["tier"], "lead")
        self.assertEqual(plan["model"], "opus")
        self.assertEqual(plan["pane"], "lead-OPS-347")
        self.assertEqual(
            plan["argv"],
            [
                "herdr", "pane", "run", "lead-OPS-347", "claude",
                "--model", "opus", "--agent", "lead", "-n", "lead-OPS-347",
            ],
        )
        self.assertFalse(plan["rebalanced"])

        frugal = vendors.plan_session("lead", "OPS-347", ["claude"], posture="frugal")
        self.assertEqual(frugal["model"], "sonnet")

        product = vendors.plan_session("product", "OPS-347", INSTALLED)
        sre = vendors.plan_session("sre", "OPS-347", INSTALLED)
        self.assertEqual(product["vendor"], "claude")
        self.assertEqual(sre["vendor"], "claude")
        self.assertEqual(product["model"], "sonnet")

        with tempfile.TemporaryDirectory() as tmp:
            text = (ROOT / "org" / "routing.yaml").read_text(encoding="utf-8")
            text = text.replace("lead_vendor: claude", "lead_vendor: codex", 1)
            path = os.path.join(tmp, "routing.yaml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            renamed = vendors.plan_session(
                "lead", "OPS-347", INSTALLED, routing_path=path,
            )
        self.assertEqual(renamed["vendor"], "codex")
        self.assertEqual(renamed["model"], "gpt-6-sol")
        self.assertEqual(renamed["argv"][4], "codex")
        self.assertNotIn("--agent", renamed["argv"])

    def test_build_personas_prefer_grok_then_codex(self):
        plan = vendors.plan_session(
            "engineer-1", "OPS-347", INSTALLED, goal="build the adapter",
        )
        self.assertEqual(plan["vendor"], "grok")
        self.assertEqual(plan["tier"], "ic")
        self.assertEqual(plan["model"], "grok-4.7-build-fast")
        self.assertEqual(plan["pane"], "engineer-1-OPS-347")
        self.assertEqual(
            plan["argv"],
            [
                "herdr", "pane", "run", "engineer-1-OPS-347", "grok",
                "--model", "grok-4.7-build-fast", "--agent", "engineer-1",
                "build the adapter",
            ],
        )
        other = vendors.plan_session("engineer-2", "OPS-347", INSTALLED)
        self.assertEqual(other["vendor"], "grok")
        self.assertEqual(other["pane"], "engineer-2-OPS-347")

        codex_only = vendors.plan_session(
            "engineer-1", "OPS-347", ["claude", "codex"],
        )
        self.assertEqual(codex_only["vendor"], "codex")
        self.assertEqual(codex_only["model"], "gpt-6-sol")
        self.assertEqual(codex_only["argv"][4], "codex")

        devops = vendors.plan_session("devops", "OPS-347", INSTALLED, posture="balanced")
        self.assertEqual(devops["vendor"], "grok")
        self.assertEqual(devops["tier"], "specialist")
        self.assertEqual(devops["model"], "grok-4.7")

        frugal = vendors.plan_session(
            "engineer-1", "OPS-347", ["grok"], posture="frugal",
        )
        self.assertEqual(frugal["model"], "grok-4.5")

        with self.assertRaises(vendors.VendorError):
            vendors.plan_session("engineer", "OPS-347", INSTALLED)
        with self.assertRaises(vendors.VendorError):
            vendors.plan_session("no-such-persona", "OPS-347", INSTALLED)
        with self.assertRaises(vendors.VendorError):
            vendors.plan_session("lead", "OPS-347", [])

    def test_qa_uses_a_different_vendor_than_the_builder(self):
        built_by_grok = vendors.plan_session(
            "qa", "OPS-347", INSTALLED, builder_vendor="grok",
        )
        self.assertEqual(built_by_grok["vendor"], "codex")
        self.assertNotEqual(built_by_grok["vendor"], "grok")
        self.assertEqual(built_by_grok["pane"], "qa-OPS-347")
        self.assertEqual(built_by_grok["model"], "gpt-6-sol")

        built_by_codex = vendors.plan_session(
            "qa", "OPS-347", INSTALLED, builder_vendor="codex",
        )
        self.assertEqual(built_by_codex["vendor"], "grok")
        self.assertNotEqual(built_by_codex["vendor"], "codex")

        built_by_claude = vendors.plan_session(
            "qa", "OPS-347", INSTALLED, builder_vendor="claude",
        )
        self.assertEqual(built_by_claude["vendor"], "codex")
        self.assertNotEqual(
            built_by_claude["pane"],
            vendors.plan_session("engineer-1", "OPS-347", INSTALLED)["pane"],
        )

        with self.assertRaises(vendors.VendorError):
            vendors.plan_session("qa", "OPS-347", ["claude", "grok"])

    def test_qa_with_one_vendor_is_a_separate_session(self):
        qa = vendors.plan_session(
            "qa", "OPS-347", ["claude"], builder_vendor="claude",
        )
        build = vendors.plan_session("engineer-1", "OPS-347", ["claude"])
        self.assertEqual(qa["vendor"], "claude")
        self.assertEqual(build["vendor"], "claude")
        self.assertEqual(qa["pane"], "qa-OPS-347")
        self.assertEqual(build["pane"], "engineer-1-OPS-347")
        self.assertNotEqual(qa["pane"], build["pane"])
        self.assertNotEqual(qa["argv"], build["argv"])

    def test_qa_split_holds_for_two_vendors_and_falls_back_for_one(self):
        # Exactly two installed vendors is already "more than one". A guard
        # written as len(installed) > 2 lets QA use the builder's vendor.
        two = ["codex", "grok"]
        built_by_codex = vendors.plan_session(
            "qa", "OPS-347", two, builder_vendor="codex",
        )
        self.assertEqual(built_by_codex["vendor"], "grok")
        self.assertEqual(built_by_codex["model"], "grok-4.7")
        self.assertNotEqual(built_by_codex["model"], "gpt-6-sol")

        built_by_grok = vendors.plan_session(
            "qa", "OPS-347", two, builder_vendor="grok",
        )
        self.assertEqual(built_by_grok["vendor"], "codex")
        self.assertEqual(built_by_grok["model"], "gpt-6-sol")
        self.assertNotEqual(built_by_grok["model"], "grok-4.7")

        with self.assertRaises(vendors.VendorError):
            vendors.plan_session("qa", "OPS-347", two)

        qa = vendors.plan_session(
            "qa", "OPS-347", ["claude"], builder_vendor="claude",
        )
        build = vendors.plan_session("engineer-1", "OPS-347", ["claude"])
        self.assertEqual(qa["vendor"], "claude")
        self.assertEqual(qa["pane"], "qa-OPS-347")
        self.assertNotEqual(qa["pane"], build["pane"])

    def test_rebalance_when_usage_left_is_at_or_below_the_floor(self):
        floor = vendors.load_routing()["usage_rebalance_below"]
        self.assertEqual(floor, 0.15)

        moved = vendors.plan_session(
            "engineer-1", "OPS-347", INSTALLED,
            usage={"grok": floor, "codex": 0.5, "claude": 0.5},
        )
        self.assertEqual(moved["vendor"], "codex")
        self.assertTrue(moved["rebalanced"])
        self.assertFalse(moved["below_floor"])
        self.assertEqual(moved["model"], "gpt-6-sol")

        stayed = vendors.plan_session(
            "engineer-1", "OPS-347", INSTALLED,
            usage={"grok": 0.16, "codex": 0.5, "claude": 0.5},
        )
        self.assertEqual(stayed["vendor"], "grok")
        self.assertFalse(stayed["rebalanced"])
        self.assertFalse(stayed["below_floor"])

        skipped_exhausted = vendors.plan_session(
            "engineer-1", "OPS-347", INSTALLED,
            usage={"grok": 0.0, "codex": floor, "claude": 0.4},
        )
        self.assertEqual(skipped_exhausted["vendor"], "claude")
        self.assertTrue(skipped_exhausted["rebalanced"])

        none_left = vendors.plan_session(
            "engineer-1", "OPS-347", INSTALLED,
            usage={"grok": 0.10, "codex": 0.10, "claude": 0.10},
        )
        self.assertEqual(none_left["vendor"], "grok")
        self.assertFalse(none_left["rebalanced"])
        self.assertTrue(none_left["below_floor"])

        lead = vendors.plan_session(
            "lead", "OPS-347", INSTALLED,
            usage={"claude": floor, "codex": 0.8, "grok": 0.8},
        )
        self.assertEqual(lead["vendor"], "codex")
        self.assertEqual(lead["model"], "gpt-6-sol")
        self.assertTrue(lead["rebalanced"])

        unread = vendors.plan_session(
            "engineer-1", "OPS-347", INSTALLED, usage={"grok": 0.10},
        )
        self.assertEqual(unread["vendor"], "grok")
        self.assertFalse(unread["rebalanced"])
        self.assertTrue(unread["below_floor"])

        for bad in (1.1, -0.01):
            with self.assertRaises(vendors.VendorError):
                vendors.plan_session(
                    "lead", "OPS-347", ["claude"], usage={"claude": bad},
                )

    def test_qa_rebalance_does_not_land_on_the_builder(self):
        stuck = vendors.plan_session(
            "qa", "OPS-347", INSTALLED, builder_vendor="claude",
            usage={"claude": 0.9, "codex": 0.10, "grok": 0.10},
        )
        self.assertEqual(stuck["vendor"], "codex")
        self.assertNotEqual(stuck["vendor"], "claude")
        self.assertFalse(stuck["rebalanced"])
        self.assertTrue(stuck["below_floor"])

        moved = vendors.plan_session(
            "qa", "OPS-347", INSTALLED, builder_vendor="claude",
            usage={"claude": 0.9, "codex": 0.10, "grok": 0.9},
        )
        self.assertEqual(moved["vendor"], "grok")
        self.assertTrue(moved["rebalanced"])
        self.assertNotEqual(moved["vendor"], "claude")

    def test_launch_invokes_the_runner_and_refuses_without_one(self):
        seen = []
        plan = vendors.launch_persona(
            "lead", "OPS-347", ["claude"],
            goal="state your role", runner=seen.append,
        )
        self.assertEqual(seen, [plan["argv"]])
        self.assertEqual(plan["argv"][-1], "state your role")
        with self.assertRaises(vendors.VendorError):
            vendors.launch_persona("lead", "OPS-347", ["claude"], runner=None)

    def test_shared_memory_is_one_store(self):
        with tempfile.TemporaryDirectory() as vault:
            store = vendors.bind_shared_memory(vault)
            self.assertEqual(os.path.basename(os.path.dirname(store)), ".claude")
            note = os.path.join(vault, ".grok", "memory", "note.md")
            with open(note, "w", encoding="utf-8") as handle:
                handle.write("shared\n")
            for rel in (".codex/memory/note.md", ".claude/memory/note.md"):
                with open(os.path.join(vault, rel), encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "shared\n")
            self.assertTrue(os.path.samefile(
                note, os.path.join(vault, ".codex", "memory", "note.md"),
            ))
            self.assertTrue(os.path.islink(os.path.join(vault, ".grok", "memory")))
            self.assertTrue(os.path.islink(os.path.join(vault, ".codex", "memory")))
            self.assertFalse(os.path.isabs(os.readlink(os.path.join(vault, ".grok", "memory"))))
            self.assertFalse(os.path.islink(os.path.join(vault, ".claude", "memory")))
            self.assertEqual(_real_memory_dirs(vault), 1)

            vendors.bind_shared_memory(vault)
            self.assertEqual(_real_memory_dirs(vault), 1)
            with open(note, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "shared\n")

    def test_shared_memory_adopts_a_directory_and_refuses_a_conflict(self):
        with tempfile.TemporaryDirectory() as vault:
            adopted = os.path.join(vault, ".codex", "memory")
            os.makedirs(adopted)
            with open(os.path.join(adopted, "keep.md"), "w", encoding="utf-8") as handle:
                handle.write("keep\n")
            vendors.bind_shared_memory(vault)
            self.assertTrue(os.path.islink(adopted))
            with open(os.path.join(vault, ".claude", "memory", "keep.md"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "keep\n")
            self.assertEqual(_real_memory_dirs(vault), 1)
            self.assertFalse(os.path.isfile(os.path.join(adopted, "keep.md")) and not os.path.islink(adopted))

        with tempfile.TemporaryDirectory() as vault:
            store = os.path.join(vault, ".claude", "memory")
            other = os.path.join(vault, ".grok", "memory")
            os.makedirs(store)
            os.makedirs(other)
            with open(os.path.join(store, "a.md"), "w", encoding="utf-8") as handle:
                handle.write("store\n")
            with open(os.path.join(other, "a.md"), "w", encoding="utf-8") as handle:
                handle.write("other\n")
            with self.assertRaises(vendors.VendorError) as err:
                vendors.bind_shared_memory(vault)
            self.assertIn("different contents", str(err.exception))
            with open(os.path.join(store, "a.md"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "store\n")
            with open(os.path.join(other, "a.md"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "other\n")
            self.assertFalse(os.path.islink(other))

    def test_setup_and_update_bind_the_shared_store(self):
        with tempfile.TemporaryDirectory() as vault:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(setup.main([
                    "--vault", vault, "--principal", "owner",
                    "--packs", "core", "--tracker", "none", "--today", "2026-01-01",
                ]), 0)
            self.assertIn("one shared store", output.getvalue())
            self.assertTrue(os.path.islink(os.path.join(vault, ".grok", "memory")))
            self.assertEqual(_real_memory_dirs(vault), 1)

            dry = io.StringIO()
            with contextlib.redirect_stdout(dry):
                self.assertEqual(update.main(["--vault", vault, "--dry-run"]), 0)
            self.assertNotIn("one shared store", dry.getvalue())
            self.assertTrue(os.path.islink(os.path.join(vault, ".codex", "memory")))

            link = os.path.join(vault, ".grok", "memory")
            os.remove(link)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(update.main(["--vault", vault]), 0)
            self.assertTrue(os.path.islink(link))
            self.assertEqual(
                os.path.realpath(link),
                os.path.realpath(os.path.join(vault, ".claude", "memory")),
            )


def _real_memory_dirs(vault):
    count = 0
    for dirpath, dirnames, _filenames in os.walk(vault):
        dirnames[:] = [name for name in dirnames if name != "__pycache__"]
        if os.path.basename(dirpath) == "memory" and not os.path.islink(dirpath):
            count += 1
    return count


if __name__ == "__main__":
    unittest.main()
