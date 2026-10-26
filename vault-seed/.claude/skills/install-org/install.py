#!/usr/bin/env python3
"""Link this vault's agents, skills and commands into ~/.claude. Stdlib only.

The situation this exists for: you cloned your vault onto a new machine and
Claude cannot see any of it. Everything the org is lives in the vault; nothing
lives in `~/.claude` except links pointing here.

    python3 install.py                 # link and verify
    python3 install.py --dry-run       # show the plan, change nothing
    python3 install.py --force         # repoint links aimed at another vault
    python3 install.py --uninstall     # remove only the links pointing here

## Why a script rather than a documented `ln -s` loop

Because it is not a loop. It has to classify what is already at each target —
correct link, wrong link, or a real file someone wrote — and those three need
different answers, only one of which is safe to automate. Getting that wrong
silently replaces work.

**A real file or directory is never replaced, even with `--force`.** `--force`
repoints symlinks; it does not delete anything that is not a link. Losing
someone's hand-written skill to an installer is not a recoverable mistake, and
no flag on this script will do it.
"""

import argparse
import os
import sys

# What gets linked, and how. Directories for skills (a skill is a folder),
# files for agents and commands.
KINDS = (
    ("agents", ".claude/agents", "*.md", "file"),
    ("skills", ".claude/skills", "*", "dir"),
    ("commands", ".claude/commands", "*.md", "file"),
)

OK, CREATE, RELINK, BLOCKED, MISSING = "ok", "create", "relink", "blocked", "missing"


def find_vault(start):
    """Walk up until something looks like a vault. Refuse to guess."""
    path = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(path, "lint_vault.py")) and \
           os.path.isdir(os.path.join(path, ".claude")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            raise SystemExit(
                "error: no vault above this script.\n"
                "       Looked for a directory containing both lint_vault.py\n"
                "       and .claude/. Run this from inside your vault."
            )
        path = parent


def sources(vault, subdir, pattern, kind):
    """Everything in the vault that should be linked out."""
    root = os.path.join(vault, subdir)
    if not os.path.isdir(root):
        return []
    found = []
    for name in sorted(os.listdir(root)):
        if name.startswith(".") or name == "README.md":
            continue
        full = os.path.join(root, name)
        if kind == "dir" and not os.path.isdir(full):
            continue
        if kind == "file" and not os.path.isfile(full):
            continue
        if pattern == "*.md" and not name.endswith(".md"):
            continue
        found.append((name, full))
    return found


def classify(target, source):
    if not os.path.lexists(target):
        return CREATE, None
    if os.path.islink(target):
        actual = os.path.realpath(target)
        if actual == os.path.realpath(source):
            return OK, actual
        if not os.path.exists(actual):
            return RELINK, f"{actual} (broken)"
        return RELINK, actual
    return BLOCKED, "a real file" if os.path.isfile(target) else "a real directory"


def plan(vault, home):
    """Every link this install would make, with what is at the target now."""
    rows = []
    for label, subdir, pattern, kind in KINDS:
        target_dir = os.path.join(home, ".claude", label)
        for name, source in sources(vault, subdir, pattern, kind):
            target = os.path.join(target_dir, name)
            state, detail = classify(target, source)
            rows.append({"label": label, "name": name, "source": source,
                         "target": target, "state": state, "detail": detail})
    return rows


def apply_row(row, force):
    """Returns (changed, message). Never removes anything that is not a link."""
    state, target, source = row["state"], row["target"], row["source"]
    if state == OK:
        return False, "already linked"
    if state == BLOCKED:
        return False, f"REFUSED — {row['detail']} is there; move it into the vault"
    if state == RELINK and not force:
        return False, f"points at {row['detail']} — use --force to repoint"

    os.makedirs(os.path.dirname(target), exist_ok=True)
    if state == RELINK:
        os.unlink(target)          # safe: classify proved it is a symlink
    try:
        os.symlink(source, target)
    except OSError as exc:
        if os.name == "nt":
            return False, (f"{exc} — on Windows, symlinks need Developer Mode "
                           "or an elevated shell")
        return False, str(exc)
    return True, "linked"


def verify(vault, home):
    """Re-read from disk. Trust the filesystem, not what we just did."""
    problems = []
    checked = 0
    for label, subdir, pattern, kind in KINDS:
        target_dir = os.path.join(home, ".claude", label)
        if not os.path.isdir(target_dir):
            continue
        for name in sorted(os.listdir(target_dir)):
            target = os.path.join(target_dir, name)
            if not os.path.islink(target):
                problems.append(f"{label}/{name}: a real {'dir' if os.path.isdir(target) else 'file'}, not a link")
                continue
            actual = os.path.realpath(target)
            if not os.path.exists(actual):
                problems.append(f"{label}/{name}: broken link -> {actual}")
            elif not actual.startswith(os.path.realpath(vault) + os.sep):
                problems.append(f"{label}/{name}: points outside this vault -> {actual}")
            else:
                checked += 1

    # An agent file that Claude cannot parse is installed and useless.
    agents_dir = os.path.join(home, ".claude", "agents")
    agents = 0
    if os.path.isdir(agents_dir):
        for name in sorted(os.listdir(agents_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(agents_dir, name)
            try:
                with open(path, encoding="utf-8") as handle:
                    head = handle.read(600)
            except OSError as exc:
                problems.append(f"agents/{name}: unreadable ({exc})")
                continue
            if not head.startswith("---") or "\nname:" not in head:
                problems.append(f"agents/{name}: no frontmatter `name:` — Claude will skip it")
            else:
                agents += 1
    return checked, agents, problems


def uninstall(vault, home, dry_run):
    removed = []
    for label, _subdir, _pattern, _kind in KINDS:
        target_dir = os.path.join(home, ".claude", label)
        if not os.path.isdir(target_dir):
            continue
        for name in sorted(os.listdir(target_dir)):
            target = os.path.join(target_dir, name)
            if not os.path.islink(target):
                continue           # not ours; never touch a real file
            if os.path.realpath(target).startswith(os.path.realpath(vault) + os.sep):
                if not dry_run:
                    os.unlink(target)
                removed.append(f"{label}/{name}")
    return removed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="repoint symlinks aimed elsewhere (never touches real files)")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--home", default=os.path.expanduser("~"),
                        help="override the home directory (for testing)")
    args = parser.parse_args(argv)

    vault = find_vault(os.path.dirname(os.path.abspath(__file__)))
    home = os.path.abspath(os.path.expanduser(args.home))
    print(f"vault: {vault}")
    print(f"home:  {home}\n")

    if args.uninstall:
        removed = uninstall(vault, home, args.dry_run)
        verb = "would remove" if args.dry_run else "removed"
        print(f"{verb} {len(removed)} link(s)")
        for entry in removed:
            print(f"  {entry}")
        print("\nReal files were not touched.")
        return 0

    rows = plan(vault, home)
    if not rows:
        print("nothing to install — .claude/agents, skills and commands are empty.")
        print("Render an org first.")
        return 1

    changed = blocked = 0
    for label in ("agents", "skills", "commands"):
        group = [r for r in rows if r["label"] == label]
        if not group:
            continue
        print(f"{label}/")
        for row in group:
            if args.dry_run:
                note = {OK: "already linked", CREATE: "would link",
                        RELINK: f"would repoint (from {row['detail']})"
                                if args.force else f"points at {row['detail']}",
                        BLOCKED: f"REFUSED — {row['detail']}"}[row["state"]]
                did = False
            else:
                did, note = apply_row(row, args.force)
            if did:
                changed += 1
            if row["state"] == BLOCKED or note.startswith("REFUSED"):
                blocked += 1
            mark = "+" if did else ("!" if row["state"] in (BLOCKED, RELINK) else " ")
            print(f"  {mark} {row['name']:<28} {note}")
        print()

    if args.dry_run:
        print("--dry-run: nothing changed")
        return 0

    checked, agents, problems = verify(vault, home)
    print(f"verify: {checked} link(s) resolve into this vault, "
          f"{agents} agent file(s) parse")
    if problems:
        print("\nPROBLEMS:")
        for problem in problems:
            print(f"  - {problem}")
        print("\nInstall did not fully succeed.")
        return 1
    if blocked:
        print(f"\n{blocked} item(s) refused — see above. Nothing was overwritten.")
        return 1

    print(f"\nInstalled. {changed} new link(s).")
    print("Start a new Claude session for it to pick up the agents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
