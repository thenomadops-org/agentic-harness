"""Re-render an existing org from roles.yaml. Stdlib only.

The counterpart to setup. Setup runs once; this runs whenever `roles.yaml`
changes, whenever a skill is improved upstream, or after pulling the base repo.

    python3 tools/update.py --vault ~/vault
    python3 tools/update.py --vault ~/vault --dry-run

Reads the principal, packs, posture and tracker from
`<vault>/.claude/org.config.json`. Legacy naming settings are removed after a
successful render; role ids now define every persona.

## What is safe, and why that is the whole design

Regenerated: `Team-ORG.md`, every `*-Role.md`, every agent definition.
**Preserved: every Soul, every Memory index, the Operating Agreement.**

A Role file describes what the org decided. A Soul describes who someone became
over months of work. Regenerating the first is correct; regenerating the second
destroys the only thing that made it worth having — so this never writes over a
Soul that exists, and the lint fails if one still looks generated after real
work has happened.

Orphaned Team directories stay in place and get reported, because authored
Souls and memory belong to the user. Legacy agent definitions are moved out of
Claude's active agent directory into `.claude/retired-agents/` with their
contents preserved, so named agents cannot remain live after migration.
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
import vendors  # noqa: E402

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


def obsolete_agents(vault, seats):
    """Return active agent files not generated for the current role seats."""
    agents = os.path.join(vault, ".claude", "agents")
    if not os.path.isdir(agents):
        return []
    expected = {f"{seat['name'].lower()}.md" for seat in seats}
    return sorted(
        os.path.join(agents, name) for name in os.listdir(agents)
        if name.endswith(".md") and name not in expected
        and os.path.isfile(os.path.join(agents, name))
    )


def retired_agent_path(vault, source):
    """Choose a non-active backup path without overwriting existing content."""
    archive = os.path.join(vault, ".claude", "retired-agents")
    name = os.path.basename(source)
    candidate = os.path.join(archive, name)
    stem, suffix = os.path.splitext(name)
    index = 1
    while os.path.lexists(candidate):
        candidate = os.path.join(archive, f"{stem}-{index}{suffix}")
        index += 1
    return candidate


def retire_obsolete_agents(vault, seats, dry_run=False):
    """Move legacy agent definitions out of the active directory, keeping backups."""
    retired = []
    for source in obsolete_agents(vault, seats):
        backup = retired_agent_path(vault, source)
        if not dry_run:
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.move(source, backup)
        retired.append((os.path.relpath(source, vault), os.path.relpath(backup, vault)))
    return retired


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

    # Work out the seats before touching anything, so a broken roles.yaml
    # fails here rather than halfway through.
    spec = miniyaml.load(render.ROLES)
    render.validate_roles(spec)
    known_packs = set(spec["packs"])
    packs = [pack for pack in config["packs"] if pack in known_packs]
    if not packs:
        packs = [name for name, detail in spec["packs"].items()
                 if (detail or {}).get("required")]
    print(f"packs:     {','.join(packs)} · posture {config['posture']}")
    print(f"(from {os.path.relpath(config_path, vault)} — edit it to change these)\n")
    roles = render.select_roles(spec, packs)
    personas = render.persona_ids(roles)
    options = {"principal": config["principal"], "vault": vault,
               "posture": config["posture"],
               "today": args.today or config.get("created", "")}
    seats = render.build_seats(spec, roles, personas, options)

    stale = orphaned_seats(vault, seats)
    old_agents = obsolete_agents(vault, seats)

    if args.dry_run:
        print(f"would re-render {len(seats)} persona(s):")
        for seat in seats:
            print(f"  {seat['name']:<16} {seat['title']}")
        print("\nregenerated: Team-ORG.md, *-Role.md, .claude/agents/*")
        print("preserved:   *-Soul.md, *-Memory.md, Team-Operating-Agreement.md")
        if stale:
            print(f"\norphaned Team directories ({len(stale)}) — reported, never removed:")
            for name in stale:
                print(f"  Team/{name}")
            print("  Copy any authored Soul or memory content into the matching current persona directory before removing an orphan.")
        if old_agents:
            print(f"\nwould retire {len(old_agents)} legacy named agent file(s) with backups:")
            for source in old_agents:
                print(f"  {os.path.relpath(source, vault)} -> {os.path.relpath(retired_agent_path(vault, source), vault)}")
        print("\n--dry-run: nothing changed")
        return 0

    render.render_org(seats, options, vault, spec)
    retired_agents = retire_obsolete_agents(vault, seats)
    print(f"re-rendered {len(seats)} seat(s)")
    print("  regenerated: Team-ORG.md, *-Role.md, .claude/agents/*")
    print("  preserved:   *-Soul.md, *-Memory.md, Team-Operating-Agreement.md")
    if retired_agents:
        print(f"  retired legacy named agent file(s) with backups ({len(retired_agents)}):")
        for source, backup in retired_agents:
            print(f"    {source} -> {backup}")

    # Old generated seats are reported as orphans, never removed. Keep all
    # other settings and user-authored fields while dropping retired selectors.
    migrated = dict(config)
    migrated.pop("theme", None)
    migrated.pop("names", None)
    if migrated.get("packs") != packs:
        migrated["packs"] = packs
    if migrated != config:
        temp_path = config_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(migrated, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, config_path)
        print("migrated legacy persona settings; other config values preserved")

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
        print("  Left in place deliberately so authored Soul and memory content")
        print("  survives the persona migration. Copy authored Soul or memory content")
        print("  into the matching current persona directory before removing an orphan.")

    vendors.bind_shared_memory(vault)
    print("memory: one shared store")

    print("\nNext:")
    print(f"  cd {vault} && python3 .claude/skills/install-org/install.py")
    print("  python3 lint_vault.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (render.OrgError, miniyaml.YamlSubsetError, vendors.VendorError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
