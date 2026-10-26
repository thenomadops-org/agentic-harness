"""Owner-authorized lead assignment and pane handoff commands."""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

VENDORS = ("claude", "grok", "codex")
ROOT = Path(__file__).resolve().parents[1]


class LeadError(Exception):
    """An actionable lead-state or herdr error."""


def state_path(environ=None):
    environ = os.environ if environ is None else environ
    return Path(environ.get("HX_STATE_DIR", ROOT / "state")) / "lead.md"


def routing_path(environ=None):
    environ = os.environ if environ is None else environ
    return Path(environ.get("HX_ROUTING_FILE", ROOT / "org/routing.yaml"))


def _quoted_owner_statement(value):
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        return False
    pairs = (("\"", "\""), ("'", "'"), ("“", "”"), ("‘", "’"))
    return any(value.startswith(left) and value.endswith(right)
               and len(value) > len(left) + len(right)
               for left, right in pairs)


def _read_assignment(path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LeadError(f"lead assignment unavailable: {exc.strerror}") from None
    required = ("Holder:", "Recorded at:", "Owner statement:")
    if any(label not in text for label in required):
        raise LeadError(f"invalid lead assignment file: {path}")
    return text


def lock_lead(holder, quote, environ=None, now=None):
    if holder not in VENDORS:
        raise LeadError("holder must be claude, grok, or codex")
    if not _quoted_owner_statement(quote):
        raise LeadError("refusing lead assignment without a quoted owner statement")
    recorded = now or datetime.datetime.now(datetime.timezone.utc)
    if recorded.tzinfo is None:
        raise LeadError("assignment time must include a timezone")
    timestamp = recorded.astimezone(datetime.timezone.utc).replace(microsecond=0)
    timestamp_text = timestamp.isoformat().replace("+00:00", "Z")
    text = (
        "# Lead assignment\n\n"
        f"- Holder: `{holder}`\n"
        f"- Recorded at: `{timestamp_text}`\n"
        "- Named by: Chris\n"
        f"- Owner statement: {quote}\n"
    )
    config = routing_path(environ)
    try:
        routing_text = config.read_text(encoding="utf-8")
    except OSError as exc:
        raise LeadError(f"routing config unavailable: {exc.strerror}") from None
    updated, count = re.subn(
        r"(?m)^lead_vendor: [a-z0-9_-]+$", f"lead_vendor: {holder}", routing_text,
    )
    if count != 1:
        raise LeadError("routing config must have exactly one lead_vendor entry")
    path = state_path(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
    config_temp = config.with_name(config.name + ".tmp")
    config_temp.write_text(updated, encoding="utf-8")
    os.replace(config_temp, config)
    return path


def _herdr_path(environ=None):
    environ = os.environ if environ is None else environ
    configured = environ.get("HX_HERDR")
    if configured:
        return configured
    return str(Path.home() / ".local/bin/herdr")


def _matching_panes(target, herdr):
    listed = subprocess.run(
        [herdr, "agent", "list"], capture_output=True, text=True,
        timeout=5, check=True,
    )
    try:
        result = json.loads(listed.stdout)
    except json.JSONDecodeError:
        raise LeadError("herdr agent list returned invalid JSON") from None
    rows = result.get("result", {}).get("agents", result.get("agents", []))
    if not isinstance(rows, list):
        raise LeadError("herdr agent list returned no agent list")
    panes = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        vendor = row.get("vendor") or row.get("vendor_id") or row.get("agent")
        pane_id = row.get("pane_id")
        if vendor == target and isinstance(pane_id, str) and pane_id and pane_id not in panes:
            panes.append(pane_id)
    return panes


def _herdr_available(path):
    return Path(path).is_file() and os.access(path, os.X_OK)


def main(argv=None, environ=None):
    environ = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(prog="hx lead")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("brief", help="print the recorded lead assignment")
    handoff = actions.add_parser("handoff", help="send the lead brief to a vendor pane")
    handoff.add_argument("--to", choices=VENDORS, required=True)
    handoff.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        text = _read_assignment(state_path(environ))
        if args.action == "brief":
            print(text, end="")
            return 0
        herdr = _herdr_path(environ)
        if not _herdr_available(herdr):
            raise LeadError("herdr is not available at ~/.local/bin/herdr")
        panes = _matching_panes(args.to, herdr)
        if not panes:
            raise LeadError(f"no {args.to} pane found on this tower")
        if len(panes) != 1:
            raise LeadError(
                f"multiple {args.to} panes found; handoff requires one unambiguous pane"
            )
        pane_id = panes[0]
        prompt = (
            "Lead handoff brief follows. This delegates work context only; it does not "
            "transfer the lead role. Read and preserve the assignment state.\n\n" + text
        )
        if args.dry_run:
            print(f"would hand off lead brief to pane {pane_id}:\n{prompt}", end="")
            return 0
        subprocess.run(
            [herdr, "agent", "prompt", pane_id, prompt], capture_output=True,
            text=True, timeout=8, check=True,
        )
        print(f"lead brief sent to pane {pane_id}; holder unchanged")
        return 0
    except (LeadError, OSError, subprocess.SubprocessError) as exc:
        print(f"hx lead: {exc}", file=sys.stderr)
        return 1


def lock_main(argv=None, environ=None):
    environ = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(prog="hx lock lead")
    parser.add_argument("--holder", choices=VENDORS, required=True)
    parser.add_argument(
        "--quote",
        help="owner's exact statement, enclosed in matching quotation marks",
    )
    args = parser.parse_args(argv)
    try:
        path = lock_lead(args.holder, args.quote, environ=environ)
    except (LeadError, OSError) as exc:
        print(f"hx lock lead: {exc}", file=sys.stderr)
        return 1
    print(f"lead holder {args.holder} recorded in {path}")
    return 0
