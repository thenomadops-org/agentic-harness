"""Unit tests for hx chat; Slack and herdr boundaries are mocked."""

import io
import json
import pathlib
import subprocess
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import hx_chat  # noqa: E402


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.payload


class HxChatTests(unittest.TestCase):
    def test_message_prefix_with_optional_recipient_and_ticket(self):
        result = hx_chat.format_message(
            "codex", "gpt-6-luna", "engineer", "example-host", "hello", "grok", "OPS-340"
        )
        self.assertEqual(
            result,
            "[codex gpt-6-luna] engineer@example-host -> @grok (OPS-340) hello",
        )

    def test_message_prefix_without_optional_fields(self):
        self.assertEqual(
            hx_chat.format_message("grok", "model-x", "qa", "example-host", " hi "),
            "[grok model-x] qa@example-host hi",
        )

    def test_since_duration_and_epoch(self):
        self.assertEqual(hx_chat.parse_since("2h", now=10000), "2800")
        self.assertEqual(hx_chat.parse_since("30m", now=10000), "8200")
        self.assertEqual(hx_chat.parse_since("1761420000.25"), "1761420000.25")
        with self.assertRaisesRegex(ValueError, "epoch or a duration"):
            hx_chat.parse_since("soon")

    def test_missing_token_names_variable_only(self):
        args = hx_chat.build_parser().parse_args(["post", "--agent", "codex", "--model", "m", "hello"])
        with self.assertRaises(hx_chat.ChatError) as caught:
            hx_chat.run(args, environ={"HX_CHAT_CHANNEL": "test-channel"})
        self.assertEqual(
            str(caught.exception), "missing required environment variable SLACK_BOT_TOKEN_CODEX"
        )

    def test_missing_channel_fails_closed(self):
        args = hx_chat.build_parser().parse_args(["post", "--agent", "codex", "--model", "m", "hello"])
        with self.assertRaisesRegex(hx_chat.ChatError, "HX_CHAT_CHANNEL"):
            hx_chat.run(args, environ={"SLACK_BOT_TOKEN_CODEX": "test-secret"})

    def test_token_is_only_in_auth_header_and_never_in_failure_text(self):
        token = "secret-SLACK-token-xyz"
        captured = {}

        def fail(request, timeout):
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            raise urllib.error.URLError(token)

        with self.assertRaises(hx_chat.ChatError) as caught:
            hx_chat.slack_call("chat.postMessage", {}, token, opener=fail)
        self.assertNotIn(token, captured["url"])
        self.assertEqual(captured["auth"], "Bearer " + token)
        self.assertNotIn(token, str(caught.exception))

    def test_token_never_enters_cli_argv_or_stdout(self):
        token = "secret-cli-boundary-token"
        args = hx_chat.build_parser().parse_args([
            "post", "--agent", "codex", "--model", "test-model", "hello",
        ])
        env = {"SLACK_BOT_TOKEN_CODEX": token, "HX_CHAT_CHANNEL": "test-channel"}
        seen_argv = []
        replies = [
            Response({"ok": True, "ts": "123.45"}),
            Response({"ok": True, "permalink": "https://slack.example/p/1"}),
        ]

        def open_request(_request, timeout):
            seen_argv.extend(sys.argv)
            return replies.pop(0)

        out = io.StringIO()
        with patch("sys.argv", ["hx", "chat", "post", "hello"]), \
             patch("urllib.request.urlopen", side_effect=open_request), \
             patch("sys.stdout", out):
            self.assertEqual(hx_chat.run(args, environ=env, hostname="example-host"), 0)
        self.assertNotIn(token, seen_argv)
        self.assertNotIn(token, out.getvalue())

    def test_api_error_code_is_shown_but_never_echoes_token(self):
        token = "secret-SLACK-token-xyz"
        with self.assertRaisesRegex(hx_chat.ChatError, "not_in_channel") as caught:
            hx_chat.slack_call(
                "chat.postMessage", {}, token,
                opener=lambda *_args, **_kwargs: Response({"ok": False, "error": "not_in_channel"}),
            )
        self.assertNotIn(token, str(caught.exception))

    def test_permalink_uses_get_with_query_and_auth_header(self):
        captured = {}

        def open_request(request, timeout):
            captured["method"] = request.get_method()
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            return Response({"ok": True, "permalink": "https://slack.example/p/1"})

        result = hx_chat.slack_call(
            "chat.getPermalink", {"channel": "test-channel", "message_ts": "1.2"},
            "secret", opener=open_request,
        )
        self.assertEqual(captured["method"], "GET")
        self.assertIn("channel=test-channel", captured["url"])
        self.assertIn("message_ts=1.2", captured["url"])
        self.assertEqual(captured["auth"], "Bearer secret")
        self.assertEqual(result["permalink"], "https://slack.example/p/1")

    def test_error_response_cannot_echo_token_as_error_code(self):
        token = "secret-SLACK-token-xyz"
        with self.assertRaises(hx_chat.ChatError) as caught:
            hx_chat.slack_call(
                "chat.postMessage", {}, token,
                opener=lambda *_args, **_kwargs: Response({"ok": False, "error": token}),
            )
        self.assertNotIn(token, str(caught.exception))

    def test_history_paginates_sorts_and_filters_recipient(self):
        calls = []
        pages = [
            {"ok": True, "messages": [
                {"ts": "3.0", "user": "U3", "text": "-> @codex hello"},
                {"ts": "2.0", "user": "U2", "text": "-> @grok hello"},
            ], "response_metadata": {"next_cursor": "next"}},
            {"ok": True, "messages": [
                {"ts": "1.0", "username": "bot", "text": "-> @codex hello"},
            ], "response_metadata": {"next_cursor": ""}},
        ]

        def call(method, payload, token):
            calls.append((method, payload, token))
            return pages.pop(0)

        messages = hx_chat.read_messages("token", "test-channel", "100", to="codex", call=call)
        self.assertEqual([m["ts"] for m in messages], ["1.0", "3.0"])
        self.assertEqual(calls[0][1], {"channel": "test-channel", "oldest": "100", "limit": 100})
        self.assertEqual(calls[1][1]["cursor"], "next")
        self.assertEqual(calls[0][2], "token")

    def test_post_refuses_empty_text(self):
        args = hx_chat.build_parser().parse_args(["post", "--agent", "codex", "--model", "m"])
        env = {"SLACK_BOT_TOKEN_CODEX": "token", "HX_CHAT_CHANNEL": "test-channel"}
        with self.assertRaisesRegex(hx_chat.ChatError, "empty message"):
            hx_chat.run(args, environ=env)

    def test_post_rejects_invalid_ticket_before_calling_slack(self):
        args = hx_chat.build_parser().parse_args([
            "post", "--agent", "codex", "--model", "m", "--ticket", "not-a-ticket", "hello",
        ])
        env = {"SLACK_BOT_TOKEN_CODEX": "token", "HX_CHAT_CHANNEL": "test-channel"}
        with self.assertRaisesRegex(hx_chat.ChatError, "--ticket must look like OPS-340"):
            hx_chat.run(args, environ=env, call=lambda *_: self.fail("Slack must not be called"))

    def test_nudge_resolves_all_vendor_panes_and_named_lead_by_pane_id(self):
        listing = subprocess.CompletedProcess([], 0, stdout=json.dumps({"result": {"agents": [
            {"agent": "codex", "name": "engineer-OPS-340", "pane_id": "pane-codex-a"},
            {"agent": "codex", "name": "qa-OPS-341", "pane_id": "pane-codex-b"},
            {"vendor": "claude", "name": "lead-OPS-340", "pane_id": "pane-claude-lead"},
        ]}}), stderr="")
        env = {"HX_CHAT_NUDGE": "1"}
        for target, expected in (
            ("codex", ["pane-codex-a", "pane-codex-b"]),
            ("claude", ["pane-claude-lead"]),
        ):
            with self.subTest(target=target):
                calls = []

                def run(argv, **_kwargs):
                    calls.append(argv)
                    return listing if argv[-2:] == ["agent", "list"] else subprocess.CompletedProcess(argv, 0)

                with patch.object(pathlib.Path, "home", return_value=pathlib.Path("/tmp/fake-home")), \
                     patch.object(pathlib.Path, "is_file", return_value=True), \
                     patch("os.access", return_value=True), \
                     patch("subprocess.run", side_effect=run):
                    hx_chat._nudge(target, "grok", env)
                prompt_calls = [call for call in calls if call[1:3] == ["agent", "prompt"]]
                self.assertEqual([call[3] for call in prompt_calls], expected)
                self.assertTrue(all("#agent-command-center" not in call[4] for call in prompt_calls))

    def test_post_prints_success_without_exposing_token_and_uses_configured_channel(self):
        args = hx_chat.build_parser().parse_args([
            "post", "--agent", "codex", "--model", "gpt-6-luna",
            "--ticket", "OPS-340", "smoke", "test",
        ])
        token = "secret-do-not-print"
        env = {
            "SLACK_BOT_TOKEN_CODEX": token,
            "HX_CHAT_CHANNEL": "team-channel-from-config",
            "HX_PERSONA": "engineer",
        }
        calls = []

        def call(method, payload, supplied_token):
            calls.append((method, payload, supplied_token))
            if method == "chat.postMessage":
                return {"ok": True, "ts": "123.45"}
            return {"ok": True, "permalink": "https://slack.example/p/12345"}

        out = io.StringIO()
        with patch("sys.stdout", out):
            result = hx_chat.run(args, environ=env, call=call, hostname="example-host")
        self.assertEqual(result, 0)
        self.assertEqual(calls[0][1], {
            "channel": "team-channel-from-config",
            "text": "[codex gpt-6-luna] engineer@example-host (OPS-340) smoke test",
        })
        self.assertEqual([c[0] for c in calls], ["chat.postMessage", "chat.getPermalink"])
        self.assertTrue(all(c[2] == token for c in calls))
        self.assertIn("ts: 123.45", out.getvalue())
        self.assertIn("permalink: https://slack.example/p/12345", out.getvalue())
        self.assertNotIn(token, out.getvalue())

    def test_token_is_not_an_cli_option_or_argument(self):
        with patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                hx_chat.build_parser().parse_args([
                    "post", "--agent", "codex", "--model", "m", "--token", "secret",
                ])

    def test_nudge_uses_mocked_herdr_and_warns_without_failing_post(self):
        args = hx_chat.build_parser().parse_args([
            "post", "--agent", "codex", "--model", "gpt-6-luna", "--to", "grok", "--nudge", "hello",
        ])
        env = {
            "SLACK_BOT_TOKEN_CODEX": "secret",
            "HX_CHAT_CHANNEL": "test-channel",
            "HX_CHAT_NUDGE": "1",
        }
        calls = []

        def call(method, payload, token):
            calls.append(method)
            if method == "chat.postMessage":
                return {"ok": True, "ts": "123.45"}
            return {"ok": True, "permalink": "https://slack.example/p/12345"}

        proc = subprocess.CompletedProcess([], 0, stdout=json.dumps({"agents": [
            {"agent": "grok", "pane_id": "pane-grok-1"},
        ]}), stderr="")
        with patch.object(pathlib.Path, "home", return_value=pathlib.Path("/tmp/fake-home")), \
             patch.object(pathlib.Path, "is_file", return_value=True), \
             patch("os.access", return_value=True), \
             patch("subprocess.run", side_effect=[proc, subprocess.CalledProcessError(1, "herdr")]) as run, \
             patch("sys.stderr", io.StringIO()) as err:
            self.assertEqual(hx_chat.run(args, environ=env, call=call, hostname="example-host"), 0)
        self.assertEqual(calls, ["chat.postMessage", "chat.getPermalink"])
        self.assertEqual(run.call_count, 2)
        self.assertIn("warning: herdr nudge failed", err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
