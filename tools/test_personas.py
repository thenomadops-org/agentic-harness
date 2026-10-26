"""Tests for role-id persona rendering and legacy org migration."""

import contextlib
import io
import json
import os
import tempfile
import unittest

import miniyaml
import render
import setup
import update


class PersonaTests(unittest.TestCase):
    def test_render_uses_role_ids_and_numbered_pool_seats(self):
        spec = miniyaml.load(render.ROLES)
        render.validate_roles(spec)
        roles = render.select_roles(
            spec, ["core", "engineering", "product", "operations"]
        )
        personas = render.persona_ids(roles)

        self.assertEqual(
            personas,
            [
                "lead", "product", "engineer-1", "engineer-2",
                "ios-engineer", "android-engineer", "devops", "qa", "sre",
            ],
        )
        self.assertTrue(all("default_name" not in role for role in spec["roles"]))

    def test_render_refuses_a_person_label_as_a_session_persona(self):
        with tempfile.TemporaryDirectory() as vault:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as err:
                render.main([
                    "--principal", "owner", "--packs", "core",
                    "--names", "Persona,Colleague,Operator",
                    "--vault", vault, "--out", vault, "--plan",
                ])
        self.assertEqual(err.exception.code, 2)

    def test_setup_refuses_person_name_selectors(self):
        with tempfile.TemporaryDirectory() as vault:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as err:
                setup.main([
                    "--vault", vault, "--principal", "owner",
                    "--names", "Persona,Colleague,Operator",
                ])
        self.assertEqual(err.exception.code, 2)

    def test_setup_and_render_no_longer_accept_theme_or_name_options(self):
        commands = (
            (render.main, ["--principal", "owner", "--vault", ".", "--out", "."]),
            (setup.main, ["--vault", ".", "--principal", "owner"]),
        )
        for command, base_args in commands:
            for option in ("--theme", "--names"):
                with self.subTest(command=command.__module__, option=option):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as err:
                        command([*base_args, option, "legacy"])
                    self.assertEqual(err.exception.code, 2)

    def test_update_migrates_legacy_config_without_losing_authored_files(self):
        with tempfile.TemporaryDirectory() as vault:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(setup.main([
                    "--vault", vault, "--principal", "owner",
                    "--packs", "core,engineering",
                    "--tracker", "none", "--today", "2026-01-01",
                ]), 0)

            config_path = os.path.join(vault, ".claude", "org.config.json")
            with open(config_path, encoding="utf-8") as handle:
                config = json.load(handle)
            config.update({"theme": "legacy", "names": ["Persona"],
                           "packs": ["core", "engineering", "retired-pack"],
                           "user_note": "keep"})
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(config, handle)

            authored = os.path.join(vault, "Team", "legacy-persona-Lead", "Authored.md")
            os.makedirs(os.path.dirname(authored))
            with open(authored, "w", encoding="utf-8") as handle:
                handle.write("authored content stays\n")

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(update.main(["--vault", vault, "--today", "2026-01-02"]), 0)

            with open(config_path, encoding="utf-8") as handle:
                migrated = json.load(handle)
            self.assertNotIn("theme", migrated)
            self.assertNotIn("names", migrated)
            self.assertEqual(migrated["packs"], ["core", "engineering"])
            self.assertEqual(migrated["user_note"], "keep")
            with open(authored, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "authored content stays\n")
            with open(os.path.join(vault, "Team", "Team-ORG.md"), encoding="utf-8") as handle:
                team_org = handle.read()
            self.assertIn("engineer-1", team_org)
            self.assertIn("<persona>-<TICKET>", team_org)


if __name__ == "__main__":
    unittest.main()
