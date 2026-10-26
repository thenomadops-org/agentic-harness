"""Re-render an existing org from roles.yaml. Stdlib only.

The counterpart to setup. Setup runs once; this runs whenever `roles.yaml`
changes, whenever a skill is improved upstream, or after pulling the base repo.

    python3 tools/update.py --vault ~/vault
    python3 tools/update.py --vault ~/vault --dry-run

Reads the answers back from `<vault>/.claude/org.config.json`, so an update
cannot silently change the theme, packs or posture. To change those, edit that
file deliberately and say so.

## What is safe, and why that is the whole design

Regenerated: `Team-ORG.md`, every `*-Role.md`, every agent definition.
**Preserved: every Soul, every Memory index, the Operating Agreement.**

A Role file describes what the org decided. A Soul describes who someone became
over months of work. Regenerating the first is correct; regenerating the second
destroys the only thing that made it worth having — so this never writes over a
Soul that exists, and the lint fails if one still looks generated after real
work has happened.

Nothing is ever deleted. A role removed from `roles.yaml` leaves its files in
place and gets reported, because "this person no longer exists" is a decision
with a memory attached, not a cleanup task.
"""

import argparse
import filecmp
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import miniyaml  # noqa: E402
import render  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(ROOT, "vault-seed")


def load_config(vault):
    path = os.path.join(vault, ".claude", "org.config.json")
    if not os.path.exists(path):
        raise SystemExit(
            f"error: no org at {vault} — {path} is missing.\n"
            "       Run setup first; update only refreshes an existing org."
        )
    with open(path, encoding="utf-8") as handle:
        return json.load(handle), path


def refresh_tree(source_root, target_root, dry_run, label):
    """Copy source over target where content differs. Never deletes."""
    added, updated = [], []
    if not os.path.isdir(source_root):
        return added, updated
    for root, dirs, files in os.walk(source_root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            source = os.path.join(root, name)
            relative = os.path.relpath(source, source_root)
            target = os.path.join(target_root, relative)
            if not os.path.exists(target):
                added.append(f"{label}/{relative}")
                if not dry_run:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copy2(source, target)
            elif not filecmp.cmp(source, target, shallow=False):
                updated.append(f"{label}/{relative}")
                if not dry_run:
                    shutil.copy2(source, target)
    return added, updated


def orphaned_seats(vault, seats):
    """Team directories with no matching seat. Reported, never removed."""
    team = os.path.join(vault, "Team")
    if not os.path.isdir(team):
        return []
    expected = {f"{s['name']}-{s['dir_suffix']}" for s in seats}
    return sorted(
        name for name in os.listdir(team)
        if os.path.isdir(os.path.join(team, name)) and name not in expected
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--today", default="")
    args = parser.parse_args(argv)

    vault = os.path.abspath(os.path.expanduser(args.vault)).rstrip("/")
    config, config_path = load_config(vault)

    print(f"vault:     {vault}")
    print(f"principal: {config['principal']}")
    print(f"theme:     {config['theme']} · packs {','.join(config['packs'])} "
          f"· posture {config['posture']}")
    print(f"(from {os.path.relpath(config_path, vault)} — edit it to change these)\n")

    # Work out the seats before touching anything, so a broken roles.yaml
    # fails here rather than halfway through.
    spec = miniyaml.load(render.ROLES)
    themes = miniyaml.load(render.THEMES)
    render.validate_roles(spec)
    roles = render.select_roles(spec, config["packs"])
    names = render.assign_names(roles, config["theme"], themes)
    render.check_names(names, config["principal"], themes,
                       strict_pattern=(config["theme"] != "role_ids"))
    options = {"principal": config["principal"], "vault": vault,
               "posture": config["posture"], "theme": config["theme"],
               "today": args.today or config.get("created", "")}
    seats = render.build_seats(spec, roles, names, options)

    stale = orphaned_seats(vault, seats)

    if args.dry_run:
        print(f"would re-render {len(seats)} seat(s):")
        for seat in seats:
            print(f"  {seat['name']:<16} {seat['title']}")
        print("\nregenerated: Team-ORG.md, *-Role.md, .claude/agents/*")
        print("preserved:   *-Soul.md, *-Memory.md, Team-Operating-Agreement.md")
        if stale:
            print(f"\norphaned Team directories ({len(stale)}) — reported, never removed:")
            for name in stale:
                print(f"  Team/{name}")
        print("\n--dry-run: nothing changed")
        return 0

    render.render_org(seats, options, vault, spec)
    print(f"re-rendered {len(seats)} seat(s)")
    print("  regenerated: Team-ORG.md, *-Role.md, .claude/agents/*")
    print("  preserved:   *-Soul.md, *-Memory.md, Team-Operating-Agreement.md")

    # Skills and seed assets improve upstream; an org should be able to take
    # those without a re-setup.
    added, updated = [], []
    for root in (os.path.join(ROOT, ".claude", "skills"),
                 os.path.join(ROOT, "plugin", "skills")):  # AOS-283: moved here
        a, u = refresh_tree(root, os.path.join(vault, ".claude", "skills"),
                            args.dry_run, "skills")
        added += a
        updated += u
    added = [a for a in added if "/setup-my-org/" not in a]
    updated = [u for u in updated if "/setup-my-org/" not in u]
    print(f"\nskills: {len(added)} added, {len(updated)} updated")
    for entry in (added + updated)[:8]:
        print(f"  {entry}")

    kind = (config.get("tracker") or {}).get("kind", "none")
    source = os.path.join(ROOT, "adapters", kind)
    if os.path.isdir(source):
        a, u = refresh_tree(source, os.path.join(vault, ".claude", "adapter"),
                            args.dry_run, "adapter")
        if a or u:
            print(f"adapter ({kind}): refreshed")

    for name in ("lint_vault.py", "check_links.py"):
        source = os.path.join(SEED, name)
        target = os.path.join(vault, name)
        if os.path.exists(source) and (
                not os.path.exists(target)
                or not filecmp.cmp(source, target, shallow=False)):
            shutil.copy2(source, target)
            print(f"tooling: {name} updated")

    if stale:
        print(f"\norphaned Team directories ({len(stale)}):")
        for name in stale:
            print(f"  Team/{name}")
        print("  Left in place deliberately. A person who no longer exists still")
        print("  has a Soul someone wrote and a memory they built. Delete only")
        print("  when you mean it.")

    print("\nNext:")
    print(f"  cd {vault} && python3 .claude/skills/install-org/install.py")
    print("  python3 lint_vault.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (render.OrgError, miniyaml.YamlSubsetError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
