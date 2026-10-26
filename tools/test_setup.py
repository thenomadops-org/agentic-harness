"""Setup's question about where tasks run.

Run from the repo root:

    python3 tools/test_setup.py
"""

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import setup  # noqa: E402


class _Terminal(io.StringIO):
    """Stdin that claims to be an interactive terminal."""

    def isatty(self):
        return True


class _Pipe(io.StringIO):
    def isatty(self):
        return False


def _run_setup(vault, *extra, stdin=None):
    argv = ["--vault", vault, "--principal", "owner", "--packs", "core",
            "--tracker", "none", "--today", "2026-01-01", *extra]
    output = io.StringIO()
    with patch.object(sys, "stdin", stdin if stdin is not None else _Pipe("")):
        with contextlib.redirect_stdout(output):
            code = setup.main(argv)
    with open(os.path.join(vault, setup.CONFIG_NAME), encoding="utf-8") as handle:
        return code, json.load(handle), output.getvalue()


class SetupExecutionTests(unittest.TestCase):
    def test_empty_answer_defaults_to_local(self):
        out = io.StringIO()
        self.assertEqual(setup.ask_execution(None, _Terminal("\n"), out), "local")
        self.assertIn("own machines or in the cloud", out.getvalue())
        self.assertIn("default: local", out.getvalue())

    def test_end_of_input_defaults_to_local(self):
        self.assertEqual(setup.ask_execution(None, _Terminal(""), io.StringIO()), "local")

    def test_cloud_answer_is_returned(self):
        self.assertEqual(setup.ask_execution(None, _Terminal("Cloud\n"), io.StringIO()), "cloud")

    def test_unknown_answer_asks_again(self):
        out = io.StringIO()
        self.assertEqual(setup.ask_execution(None, _Terminal("maybe\ncloud\n"), out), "cloud")
        self.assertIn("Please answer local or cloud.", out.getvalue())

    def test_non_interactive_defaults_to_local_without_reading(self):
        stdin = _Pipe("cloud\n")
        out = io.StringIO()
        self.assertEqual(setup.ask_execution(None, stdin, out), "local")
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(stdin.tell(), 0)

    def test_explicit_choice_skips_the_question(self):
        out = io.StringIO()
        self.assertEqual(setup.ask_execution("cloud", _Terminal("local\n"), out), "cloud")
        self.assertEqual(out.getvalue(), "")

    def test_setup_saves_local_by_default(self):
        with tempfile.TemporaryDirectory() as vault:
            code, config, output = _run_setup(vault)
            self.assertEqual(code, 0)
            self.assertEqual(config["execution"], "local")
            self.assertIn("execution: local", output)

    def test_setup_saves_explicit_cloud(self):
        with tempfile.TemporaryDirectory() as vault:
            code, config, _ = _run_setup(vault, "--execution", "cloud")
            self.assertEqual(code, 0)
            self.assertEqual(config["execution"], "cloud")

    def test_setup_asks_on_a_terminal_and_saves_the_answer(self):
        with tempfile.TemporaryDirectory() as vault:
            code, config, output = _run_setup(vault, stdin=_Terminal("cloud\n"))
            self.assertEqual(code, 0)
            self.assertEqual(config["execution"], "cloud")
            self.assertIn("[local/cloud]", output)

    def test_setup_rejects_an_unknown_execution(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                setup.main(["--vault", "unused", "--principal", "owner",
                            "--execution", "elsewhere"])


if __name__ == "__main__":
    unittest.main()
