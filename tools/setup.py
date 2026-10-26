"""Create a vault, render role personas into it, and record the choices. Stdlib only.

The one-time step. `setup-my-org` drives the conversation and calls this with
the answers. The one question asked here is where tasks run: when
`--execution` is not given and both stdin and stdout are terminals, setup asks
whether all tasks run on the user's own machines (`local`) or in the cloud
(`cloud`). Empty input, and a run whose input or output is not a terminal,
pick `local`, so it stays usable from a script and does not block when output
is captured.

    python3 tools/setup.py --vault ~/my-vault --principal owner \\
        --packs core,engineering --tracker github-issues

Refuses to run twice. One fork holds one org — see ADR-0002 — so an existing
`Team/Team-ORG.md` means this is an update, and updates go through
`org update`, which preserves Souls and memory.
"""

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import miniyaml  # noqa: E402
import render  # noqa: E402
import vendors  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(ROOT, "vault-seed")
CONFIG_NAME = os.path.join(".claude", "org.config.json")

TRACKERS = ("github-issues", "jira", "none")
EXECUTION = ("local", "cloud")
DEFAULT_EXECUTION = "local"


def _is_terminal(stream):
    return hasattr(stream, "isatty") and stream.isatty()


def ask_execution(choice=None, stdin=None, stdout=None):
    """Where all tasks run: the user's own machines (local) or the cloud.

    An explicit choice wins. Otherwise ask, but only when both streams are
    terminals, so a captured prompt cannot block on a waiting read. Empty
    input, end of input and non-interactive runs all pick the user's own
    machines.
    """
    if choice:
        return choice
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    if not (_is_terminal(stdin) and _is_terminal(stdout)):
        return DEFAULT_EXECUTION
    while True:
        stdout.write("Run all tasks on your own machines or in the cloud? "
                     "[local/cloud] (default: local): ")
        stdout.flush()
        line = stdin.readline()
        answer = line.strip().lower()
        if not answer:
            return DEFAULT_EXECUTION
        if answer in EXECUTION:
            return answer
        stdout.write("Please answer local or cloud.\n")


def seed_vault(vault):
    """Copy the seed in. Never clobbers a file that already exists."""
    copied, skipped = 0, 0
    for root, dirs, files in os.walk(SEED):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            source = os.path.join(root, name)
            target = os.path.join(vault, os.path.relpath(source, SEED))
            if os.path.exists(target):
                skipped += 1
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
            copied += 1
    return copied, skipped


def copy_skills(vault):
    """Portable skills live in this repo; the vault needs its own copy.

    Not symlinks into the OS repo: the vault has to stand alone on a machine
    that never cloned this repository. `org update` refreshes them.

    `setup-my-org` is deliberately excluded — it runs once, from here, and an
    org that already exists has no use for it.
    """
    # Repo-local skills stay in .claude/skills; the workforce skills moved to
    # plugin/skills (AOS-283, spec F1). A vault stands alone, so it gets both.
    source_roots = [os.path.join(ROOT, ".claude", "skills"),
                    os.path.join(ROOT, "plugin", "skills")]
    target_root = os.path.join(vault, ".claude", "skills")
    copied = skipped = 0
    for source_root in source_roots:
        if not os.path.isdir(source_root):
            continue
        for name in sorted(os.listdir(source_root)):
            if name in ("setup-my-org",) or name.startswith("."):
                continue
            source = os.path.join(source_root, name)
            target = os.path.join(target_root, name)
            if not os.path.isdir(source):
                continue
            if os.path.exists(target):
                skipped += 1
                continue
            shutil.copytree(source, target)
            copied += 1
    return copied, skipped


def copy_adapter(vault, kind):
    """The chosen tracker adapter goes into the vault so agents can read it."""
    source = os.path.join(ROOT, "adapters", kind)
    if not os.path.isdir(source):
        return 0
    target = os.path.join(vault, ".claude", "adapter")
    os.makedirs(target, exist_ok=True)
    count = 0
    for name in sorted(os.listdir(source)):
        src = os.path.join(source, name)
        dst = os.path.join(target, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            count += 1
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault", required=True)
    parser.add_argument("--principal", required=True)
    parser.add_argument("--packs", default="core")
    parser.add_argument("--posture", default="balanced",
                        choices=["frugal", "balanced", "max"])
    parser.add_argument("--tracker", default="github-issues", choices=TRACKERS)
    parser.add_argument("--tracker-project", default="",
                        help="repo (github-issues) or project key (jira)")
    parser.add_argument("--execution", default=None, choices=EXECUTION,
                        help="where all tasks run: local (your own machines, "
                             "the default) or cloud; asked when input and "
                             "output are both terminals and this is omitted")
    parser.add_argument("--today", default="")
    parser.add_argument("--force-reseed", action="store_true",
                        help="re-copy seed files, still never clobbering")
    args = parser.parse_args(argv)

    vault = os.path.abspath(os.path.expanduser(args.vault)).rstrip("/")

    existing = os.path.join(vault, "Team", "Team-ORG.md")
    if os.path.exists(existing) and not args.force_reseed:
        print(f"error: an org already exists at {vault}", file=sys.stderr)
        print("", file=sys.stderr)
        print("One fork holds one org (ADR-0002). To change this one, edit",
              file=sys.stderr)
        print("org/roles.yaml and run `org update` — it re-renders the generated",
              file=sys.stderr)
        print("files and leaves Souls, memory and the operating agreement alone.",
              file=sys.stderr)
        print("", file=sys.stderr)
        print("For a genuinely different team, fork the base repo again and set",
              file=sys.stderr)
        print("up a second vault.", file=sys.stderr)
        return 1

    execution = ask_execution(args.execution)

    print(f"vault:     {vault}")
    print(f"principal: {args.principal}")
    print(f"tracker:   {args.tracker}"
          + (f" ({args.tracker_project})" if args.tracker_project else ""))
    print(f"execution: {execution}")
    print()

    os.makedirs(vault, exist_ok=True)
    copied, skipped = seed_vault(vault)
    print(f"seed: {copied} file(s) copied"
          + (f", {skipped} left alone (already present)" if skipped else ""))

    skills_copied, skills_skipped = copy_skills(vault)
    print(f"skills: {skills_copied} copied"
          + (f", {skills_skipped} already present" if skills_skipped else ""))

    adapter_files = copy_adapter(vault, args.tracker)
    print(f"adapter: {args.tracker} ({adapter_files} file(s))")

    # Render straight into the vault. render.py validates everything before it
    # writes, so a bad answer fails without leaving half a team behind.
    argv_render = [
        "--principal", args.principal,
        "--packs", args.packs,
        "--vault", vault,
        "--posture", args.posture,
        "--out", vault,
        "--today", args.today,
    ]
    print()
    code = render.main(argv_render)
    if code != 0:
        return code

    config = {
        "version": 1,
        "principal": args.principal,
        "vault": vault,
        "packs": [p.strip() for p in args.packs.split(",") if p.strip()],
        "posture": args.posture,
        "tracker": {"kind": args.tracker, "project": args.tracker_project},
        "execution": execution,
        "created": args.today or "unknown",
        "note": "Written by setup. `org update` reads this to re-render "
                "consistently. Editing it does not change the org — edit "
                "org/roles.yaml and re-run org update.",
    }
    config_path = os.path.join(vault, CONFIG_NAME)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"config: {os.path.relpath(config_path, vault)}")
    vendors.bind_shared_memory(vault)
    print("memory: one shared store")

    print()
    print("Next:")
    print(f"  cd {vault}")
    print("  python3 .claude/skills/install-org/install.py")
    print("  python3 lint_vault.py")
    print()
    print("Then start a NEW Claude session named <persona>-<TICKET> and ask")
    print("it to state its role id and reporting line.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (render.OrgError, miniyaml.YamlSubsetError, vendors.VendorError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
