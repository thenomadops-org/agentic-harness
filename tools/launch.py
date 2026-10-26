#!/usr/bin/env python3
"""Start a planned persona session. Stdlib only.

    python3 tools/launch.py <persona> <TICKET> "<goal>" --vault <dir> \\
        [--usage vendor=frac ...] [--builder <vendor>] [--dry-run]

The installed vendors are the catalog commands found on PATH. The plan comes
from vendors.plan_session, including the rule that QA uses another vendor
when more than one is installed. This prints the plan, opens a pane whose
shell starts in the vault, and runs that herdr command. herdr addresses a
pane by id, so the pane slot of the planned argv is the id just created.
herdr joins the command tail and sends that line through a shell, so each
element of the tail is shell-quoted first. A canonical terminal line holds
4095 bytes and discards the rest, so a longer element is stored in a
temporary file and the shell reads it back. The vendor still receives the
full argument. The pane id is not quoted: herdr reads it itself. The plan
is built for this vault. A vendor that takes a definition path is given the
vault persona file. A vendor that takes developer instructions is given
that same file as one config override. Nothing is written under the home
directory. A dry run prints the plan and does not run herdr.
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vendors  # noqa: E402


def vendors_on_path(path=None, vendors_path=None):
    """Return catalog ids whose command is executable on PATH, in catalog order."""
    catalog = vendors.load_vendors(vendors_path)
    search = os.environ.get("PATH", "") if path is None else path
    found = []
    for record in catalog["vendors"]:
        if shutil.which(record["command"], path=search):
            found.append(record["id"])
    return found


def parse_usage(items):
    """Turn repeated vendor=fraction arguments into the planner's usage map."""
    if not items:
        return None
    usage = {}
    for item in items:
        if item.count("=") != 1:
            raise vendors.VendorError(f"usage must be vendor=fraction, got {item!r}")
        vendor_id, raw = item.split("=", 1)
        try:
            value = float(raw)
        except ValueError as exc:
            raise vendors.VendorError(
                f"usage must be vendor=fraction, got {item!r}"
            ) from exc
        usage[vendor_id] = value
    return usage


def format_plan(plan, vault):
    return "\n".join([
        f"persona: {plan['persona']}",
        f"ticket: {plan['ticket']}",
        f"pane: {plan['pane']}",
        f"vendor: {plan['vendor']}",
        f"model: {plan['model']}",
        f"cwd: {vault}",
        "argv: " + shlex.join(plan["argv"]),
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start a planned persona session")
    parser.add_argument("persona")
    parser.add_argument("ticket")
    parser.add_argument("goal")
    parser.add_argument("--vault", required=True)
    parser.add_argument(
        "--usage", action="append", default=[],
        help="remaining fraction for one vendor, as vendor=0.5; repeat for each",
    )
    parser.add_argument(
        "--builder", default=None,
        help="vendor that built the change; required for QA when more than one vendor is installed",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    vault = os.path.realpath(os.path.abspath(os.path.expanduser(args.vault)))
    if not os.path.isdir(vault):
        print(f"error: vault is not a directory: {args.vault}", file=sys.stderr)
        return 2

    try:
        installed = vendors_on_path()
        kwargs = {}
        if args.builder:
            kwargs["builder_vendor"] = args.builder
        plan = vendors.plan_session(
            args.persona, args.ticket, installed,
            goal=args.goal, usage=parse_usage(args.usage), vault=vault, **kwargs,
        )
    except vendors.VendorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(format_plan(plan, vault))
    if args.dry_run:
        return 0

    # pane run has no directory flag, and it addresses a pane by id. A label
    # is not an id. Open the pane in the vault, name it, then run the planned
    # command against that id. Nothing is written under the home directory.
    opened, pane_id = _open_pane(vault, plan["pane"])
    if opened != 0:
        return opened
    argv = list(plan["argv"])
    if argv[:3] != ["herdr", "pane", "run"] or len(argv) < 4:
        print("error: planned argv is not a herdr pane run", file=sys.stderr)
        return 1
    argv[3] = pane_id
    # The pane shell word-splits this tail. Quote every element so a goal
    # that contains spaces or quotes stays one argument. A line past the
    # terminal's 4095-byte limit is cut and the vendor never sees the rest.
    try:
        argv[4:] = _pane_shell_tail(argv[4:])
    except vendors.VendorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"pane_id: {pane_id}")
    completed = subprocess.run(argv, cwd=vault, check=False)
    return completed.returncode


# One canonical-mode line is 4095 bytes plus the newline that executes it.
_PANE_SHELL_LIMIT = 4095
_SAFE_TEMP_PATH = re.compile(r"\A/[A-Za-z0-9_./-]+\Z")


def _pane_shell_tail(parts):
    """Quote a pane command so the typed line fits in a terminal buffer.

    The shell expands a staged word before it starts the vendor, so the
    vendor receives the original argument.
    """
    quoted = [shlex.quote(part) for part in parts]
    originals = list(parts)
    while _joined_bytes(quoted) > _PANE_SHELL_LIMIT:
        index = max(range(len(quoted)), key=lambda i: len(quoted[i].encode()))
        staged = _stage_shell_word(originals[index])
        if len(staged.encode()) >= len(quoted[index].encode()):
            break
        quoted[index] = staged
    return quoted


def _joined_bytes(quoted):
    if not quoted:
        return 0
    return sum(len(part.encode()) for part in quoted) + len(quoted) - 1


def _stage_shell_word(text):
    """Return a short shell word that expands to text."""
    handle = tempfile.NamedTemporaryFile(
        prefix="pane-arg-", delete=False,
    )
    try:
        handle.write(text.encode("utf-8"))
    finally:
        handle.close()
    os.chmod(handle.name, 0o600)
    if _SAFE_TEMP_PATH.fullmatch(handle.name) is None:
        os.unlink(handle.name)
        raise vendors.VendorError("temporary argument path cannot be passed to the shell")
    # Absolute path: the pane PATH may not include cat, and the substitution
    # has to expand before the vendor starts.
    return '"$(/bin/cat ' + handle.name + ')"'


def _open_pane(vault, pane):
    """Open a pane whose shell cwd is the vault, and name it pane.

    Returns (exit code, pane id). The id is None when the pane was not opened.
    """
    completed = subprocess.run(
        [
            "herdr", "workspace", "create",
            "--cwd", vault, "--label", pane, "--no-focus",
        ],
        cwd=vault, check=False, capture_output=True, text=True,
    )
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        return completed.returncode, None
    try:
        payload = json.loads(completed.stdout)
        pane_id = payload["result"]["root_pane"]["pane_id"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("error: herdr workspace create did not return a pane id", file=sys.stderr)
        return 1, None
    if not isinstance(pane_id, str) or not pane_id:
        print("error: herdr workspace create did not return a pane id", file=sys.stderr)
        return 1, None
    renamed = subprocess.run(
        ["herdr", "pane", "rename", pane_id, pane],
        cwd=vault, check=False,
    )
    if renamed.returncode != 0:
        return renamed.returncode, None
    return 0, pane_id


if __name__ == "__main__":
    raise SystemExit(main())
