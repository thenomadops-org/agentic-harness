"""Small stdlib-only Slack client for the team chat CLI."""

import argparse
import datetime as _dt
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AGENTS = ("claude", "grok", "codex")


class ChatError(Exception):
    """An actionable error with no request credentials in its message."""


def parse_since(value, now=None):
    """Return Slack's oldest timestamp for an epoch or a duration like 2h/30m."""
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return str(float(value))
    match = re.fullmatch(r"(\d+)([hm])", value)
    if not match:
        raise ValueError("--since must be an epoch or a duration such as 2h or 30m")
    amount, unit = int(match.group(1)), match.group(2)
    seconds = amount * (3600 if unit == "h" else 60)
    current = _dt.datetime.now(tz=_dt.timezone.utc).timestamp() if now is None else now
    return str(current - seconds)


def _safe_error_code(value, token=None):
    if (
        isinstance(value, str)
        and token not in value
        and re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value)
    ):
        return value
    return "unknown_error"


def slack_call(method, payload, token, opener=None):
    """Call a Slack Web API method, keeping the token only in the auth header."""
    if not token:
        raise ChatError("Slack bot token is required")
    url = "https://slack.com/api/" + method
    headers = {"Authorization": "Bearer " + token}
    if method == "chat.getPermalink":
        url += "?" + urllib.parse.urlencode(payload)
        data, http_method = None, "GET"
    else:
        headers["Content-Type"] = "application/json; charset=utf-8"
        data, http_method = json.dumps(payload).encode("utf-8"), "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=http_method)
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
            code = _safe_error_code(body.get("error", "http_error"), token)
        except Exception:
            code = "http_error"
        raise ChatError(f"Slack {method} failed: {code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ChatError(f"Slack {method} request failed ({type(exc).__name__})") from None
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ChatError(f"Slack {method} returned invalid JSON") from None
    if not isinstance(result, dict):
        raise ChatError(f"Slack {method} returned an invalid response")
    if result.get("ok") is not True:
        code = _safe_error_code(result.get("error"), token)
        raise ChatError(f"Slack {method} failed: {code}")
    return result


def _identity(args, environ):
    agent = args.agent or environ.get("HX_AGENT")
    if agent not in AGENTS:
        raise ChatError("set --agent or HX_AGENT to claude, grok, or codex")
    model = args.model or environ.get("HX_MODEL")
    if not model:
        raise ChatError("set --model or HX_MODEL")
    token_env = "SLACK_BOT_TOKEN_" + agent.upper()
    token = environ.get(token_env)
    if not token:
        raise ChatError(f"missing required environment variable {token_env}")
    persona = environ.get("HX_PERSONA") or agent
    return agent, model, token_env, token, persona


def format_message(agent, model, role, hostname, text, to=None, ticket=None):
    message = f"[{agent} {model}] {role}@{hostname}"
    if to:
        message += f" -> @{to}"
    if ticket:
        message += f" ({ticket})"
    return message + " " + text.strip()


def _response_author(message):
    bot = message.get("bot_profile") or {}
    profile = message.get("user_profile") or {}
    return (
        bot.get("name")
        or message.get("username")
        or profile.get("display_name")
        or message.get("user")
        or "unknown"
    )


def read_messages(token, channel, oldest, to=None, call=slack_call):
    """Fetch every page of channel history and return chronological messages."""
    messages, cursor, seen = [], None, set()
    while True:
        payload = {"channel": channel, "oldest": oldest, "limit": 100}
        if cursor:
            payload["cursor"] = cursor
        response = call("conversations.history", payload, token)
        messages.extend(response.get("messages", []))
        cursor = (response.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
        if cursor in seen:
            raise ChatError("Slack pagination repeated a cursor")
        seen.add(cursor)
    if to:
        needle = f"-> @{to}".casefold()
        messages = [m for m in messages if needle in str(m.get("text", "")).casefold()]
    return sorted(messages, key=lambda m: float(m.get("ts", "0")))


def _format_time(timestamp):
    try:
        return _dt.datetime.fromtimestamp(float(timestamp), tz=_dt.timezone.utc).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )
    except (TypeError, ValueError, OverflowError, OSError):
        return "unknown time"


def _nudge(target, sender, environ):
    if not target or not (environ.get("HX_CHAT_NUDGE") == "1"):
        return
    herdr = Path.home() / ".local/bin/herdr"
    if not herdr.is_file() or not os.access(herdr, os.X_OK):
        return
    prompt = f"New message in #agent-command-center from {sender}, run hx chat read --since 10m"
    try:
        listed = subprocess.run(
            [str(herdr), "agent", "list"], capture_output=True, text=True, timeout=5, check=True
        )
        data = json.loads(listed.stdout)
        rows = data.get("result", {}).get("agents", data.get("agents", []))
        if not any((row.get("agent") or row.get("name")) == target for row in rows):
            return
        subprocess.run(
            [str(herdr), "agent", "prompt", target, prompt],
            capture_output=True,
            text=True,
            timeout=8,
            check=True,
        )
    except Exception as exc:  # Nudge is best effort; Slack has already accepted the post.
        print(f"warning: herdr nudge failed ({type(exc).__name__})", file=sys.stderr)


def _add_identity_options(parser):
    parser.add_argument("--agent", choices=AGENTS)
    parser.add_argument("--model")


def build_parser():
    parser = argparse.ArgumentParser(prog="hx chat")
    actions = parser.add_subparsers(dest="action", required=True)

    post = actions.add_parser("post", help="post a channel message")
    _add_identity_options(post)
    post.add_argument("--to", choices=AGENTS)
    post.add_argument("--ticket", type=lambda v: v.upper())
    post.add_argument("--nudge", action="store_true")
    post.add_argument("text", nargs="*")

    read = actions.add_parser("read", help="read recent channel messages")
    _add_identity_options(read)
    read.add_argument("--since", required=True)
    read.add_argument("--to", choices=AGENTS)
    return parser


def run(args, environ=None, call=slack_call, hostname=None):
    environ = os.environ if environ is None else environ
    agent, model, _token_env, token, persona = _identity(args, environ)
    channel = environ.get("HX_CHAT_CHANNEL")
    if not channel or not channel.strip():
        raise ChatError("missing required environment variable HX_CHAT_CHANNEL")
    if args.action == "post":
        text = " ".join(args.text).strip()
        if not text:
            raise ChatError("refusing to post an empty message")
        if args.ticket and not re.fullmatch(r"OPS-\d+", args.ticket):
            raise ChatError("--ticket must look like OPS-340")
        message = format_message(
            agent, model, persona, hostname or socket.gethostname(), text, args.to, args.ticket
        )
        response = call(
            "chat.postMessage", {"channel": channel, "text": message}, token
        )
        ts = response.get("ts")
        if not ts:
            raise ChatError("Slack chat.postMessage succeeded without a message timestamp")
        link = call("chat.getPermalink", {"channel": channel, "message_ts": ts}, token)
        print(f"ts: {ts}\npermalink: {link.get('permalink', '(unavailable)')}")
        if args.nudge or environ.get("HX_CHAT_NUDGE") == "1":
            _nudge(args.to, agent, {**environ, "HX_CHAT_NUDGE": "1"})
        return 0

    try:
        oldest = parse_since(args.since)
    except ValueError as exc:
        raise ChatError(str(exc)) from None
    messages = read_messages(token, channel, oldest, args.to, call)
    for message in messages:
        print(f"{_format_time(message.get('ts'))}  {_response_author(message)}  {message.get('text', '')}")
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except ChatError as exc:
        print(f"hx: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
