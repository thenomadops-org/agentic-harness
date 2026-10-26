"""Render an org from `roles.yaml`. Stdlib only.

Reads the role tree, picks the roles in the chosen packs, expands pooled roles
into persona seats, and writes one set of files per seat plus the org-wide
documents.

    python3 tools/render.py \\
        --principal owner \\
        --packs core,engineering --vault ~/my-vault --out ./out

Validation runs before anything is written, so a bad org fails without leaving
half a team on disk.
"""

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import miniyaml  # noqa: E402
import minitemplate  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLES = os.path.join(ROOT, "org", "roles.yaml")
TEMPLATES = os.path.join(ROOT, "org", "templates")

PER_SEAT = {
    # Under .claude/ so it matches the layout `install-org` symlinks from, and
    # so the lint treats it as config rather than a wiki page nothing links to.
    "agent.md.tmpl": ".claude/agents/{name_lower}.md",
    "soul.md.tmpl": "Team/{name}-{dir_suffix}/{name}-Soul.md",
    "role.md.tmpl": "Team/{name}-{dir_suffix}/{name}-Role.md",
    "memory.md.tmpl": "Team/{name}-{dir_suffix}/{name}-Memory.md",
}
ORG_WIDE = {
    "team-org.md.tmpl": "Team/Team-ORG.md",
    "operating-agreement.md.tmpl": "Team/Team-Operating-Agreement.md",
}

# Re-rendered by `org update`, so a hand-edit here is silently reverted. The
# lint compares these against a manifest and fails on drift.
#
# Deliberately absent: Soul (becomes a person, must never be overwritten),
# Memory (the agent owns it), and the Operating Agreement (a starting point
# meant to be amended in place). Regenerating those would erase the thing that
# makes them worth having.
GENERATED = ("agent.md.tmpl", "role.md.tmpl", "team-org.md.tmpl")
PRESERVE_IF_PRESENT = ("soul.md.tmpl", "memory.md.tmpl",
                       "operating-agreement.md.tmpl")


class OrgError(ValueError):
    pass


# ------------------------------------------------------------- validation ---


def validate_roles(spec):
    """Structural checks. Every failure is listed, not just the first."""
    problems = []
    roles = spec.get("roles") or []
    if not roles:
        raise OrgError("roles.yaml defines no roles")

    ids = [r.get("id") for r in roles]
    by_id = {r.get("id"): r for r in roles}

    for role in roles:
        if not role.get("id"):
            problems.append("a role has no id")
        for field in ("title", "dir_suffix", "pack", "tier", "reports_to"):
            if not role.get(field):
                problems.append(f"{role.get('id')}: missing {field}")

    for rid in ids:
        if ids.count(rid) > 1:
            problems.append(f"duplicate role id {rid!r}")

    packs = set(spec.get("packs") or {})
    tiers = set(spec.get("tiers") or [])
    for role in roles:
        if role.get("pack") not in packs:
            problems.append(f"{role['id']}: unknown pack {role.get('pack')!r}")
        if role.get("tier") not in tiers:
            problems.append(f"{role['id']}: unknown tier {role.get('tier')!r}")
        parent = role.get("reports_to")
        if parent != "principal" and parent not in by_id:
            problems.append(f"{role['id']}: reports_to {parent!r} does not exist")
        for managed in role.get("manages") or []:
            if managed not in by_id:
                problems.append(f"{role['id']}: manages {managed!r} which does not exist")
            elif by_id[managed].get("reports_to") != role["id"]:
                problems.append(
                    f"{role['id']} manages {managed}, but {managed} reports to "
                    f"{by_id[managed].get('reports_to')}"
                )
        if parent != "principal":
            if role["id"] not in (by_id.get(parent, {}).get("manages") or []):
                problems.append(
                    f"{role['id']} reports to {parent}, but {parent} does not list it"
                )

    # Cycle detection.
    for role in roles:
        seen, node = set(), role["id"]
        while node and node != "principal":
            if node in seen:
                problems.append(f"reporting cycle through {role['id']}")
                break
            seen.add(node)
            node = by_id.get(node, {}).get("reports_to")

    for posture, mapping in (spec.get("budget_postures") or {}).items():
        missing = tiers - set(mapping or {})
        if missing:
            problems.append(f"budget posture {posture!r} has no model for {sorted(missing)}")

    if problems:
        raise OrgError("roles.yaml is invalid:\n  - " + "\n  - ".join(problems))
    return by_id


# ------------------------------------------------------------------ seats ---


def select_roles(spec, packs):
    known = set(spec["packs"])
    unknown = set(packs) - known
    if unknown:
        raise OrgError(f"unknown pack(s): {sorted(unknown)}; known: {sorted(known)}")
    required = {n for n, p in spec["packs"].items() if (p or {}).get("required")}
    chosen = set(packs) | required
    roles = [r for r in spec["roles"] if r["pack"] in chosen]

    # A kept role may not report to a dropped one.
    kept = {r["id"] for r in roles}
    for role in roles:
        parent = role["reports_to"]
        if parent != "principal" and parent not in kept:
            raise OrgError(
                f"{role['id']} (pack {role['pack']}) reports to {parent}, which is "
                f"in a pack you did not select — add that pack or drop this one"
            )
    return roles


def persona_ids(roles):
    """Return role ids, adding stable numeric suffixes for pooled roles."""
    personas = []
    for role in roles:
        count = int(role.get("instances") or 1)
        personas.extend(
            role["id"] if count == 1 else f"{role['id']}-{index + 1}"
            for index in range(count)
        )
    return personas


def build_seats(spec, roles, names, options):
    by_id = {r["id"]: r for r in spec["roles"]}
    posture = (spec.get("budget_postures") or {}).get(options["posture"])
    if posture is None:
        raise OrgError(
            f"unknown posture {options['posture']!r}; known: "
            f"{sorted(spec.get('budget_postures') or {})}"
        )

    # role_id -> persona ids holding it (a pool has several)
    holders, cursor = {}, 0
    for role in roles:
        count = int(role.get("instances") or 1)
        holders[role["id"]] = names[cursor : cursor + count]
        cursor += count

    kept = {r["id"] for r in roles}
    seats = []
    cursor = 0
    for role in roles:
        count = int(role.get("instances") or 1)
        for index in range(count):
            name = names[cursor]
            cursor += 1
            parent = role["reports_to"]
            parent_name = (
                options["principal"] if parent == "principal"
                else holders.get(parent, [parent])[0]
            )
            reports = []
            for managed in role.get("manages") or []:
                if managed in kept:
                    reports.extend(
                        {"name": n, "title": by_id[managed]["title"]}
                        for n in holders.get(managed, [])
                    )
            leans = role.get("leans") or []
            dotted = role.get("dotted_line_to")
            seats.append({
                "role_id": role["id"],
                "name": str(name),
                "name_lower": str(name).lower(),
                "title": role["title"],
                "dir_suffix": role["dir_suffix"],
                "pack": role["pack"],
                "kind": role.get("kind", "line"),
                "is_staff": role.get("kind") == "staff",
                "tier": role["tier"],
                "model": posture[role["tier"]],
                "reports_to": parent,
                "reports_to_name": parent_name,
                "reports_to_principal": parent == "principal",
                "manages": reports,
                "has_reports": bool(reports),
                "leans": leans[index] if index < len(leans) else None,
                "owns": role.get("owns") or [],
                "summary": _sentence((role.get("owns") or ["general support"])[0]),
                "use_when": role.get("use_when") or f"{role['title'].lower()} work",
                "authority": role.get("authority") or [],
                "cannot": role.get("cannot") or [],
                "escalates_when": role.get("escalates_when") or [],
                "notes": role.get("notes") or [],
                "hats": role.get("hats") or [],
                "hard_limits": role.get("hard_limits") or [],
                "fails_by": role.get("fails_by"),
                "dotted_line_to": dotted,
                "dotted_line_to_name": holders.get(dotted, [dotted])[0] if dotted else None,
                "principal_name": options["principal"],
                "principal_title": (spec.get("principal") or {}).get(
                    "default_title", "owner"),
                "vault_path": options["vault"],
                "chief_of_staff_name": holders.get("chief-of-staff", [None])[0]
                or options["principal"],
                "today": options["today"],
            })
    return seats


# --------------------------------------------------------------- rendering ---


def render_org(seats, options, out_dir, spec):
    written, generated = [], {}

    def emit(template, relative, body):
        target = os.path.join(out_dir, relative)
        if template in PRESERVE_IF_PRESENT and os.path.exists(target):
            # Authored after the first write. Overwriting would erase a Soul
            # that became a person, or a memory index the agent owns.
            return False
        _write(target, body)
        written.append(target)
        if template in GENERATED:
            generated[relative] = hashlib.sha256(
                body.encode("utf-8")).hexdigest()
        return True

    for template, pattern in PER_SEAT.items():
        path = os.path.join(TEMPLATES, template)
        if not os.path.exists(path):
            raise OrgError(f"missing template: {path}")
        for seat in seats:
            emit(template, pattern.format(**seat),
                 minitemplate.render_file(path, seat))

    org_context = {
        "principal_name": options["principal"],
        "principal_title": (spec.get("principal") or {}).get("default_title", "owner"),
        "principal_decides": (spec.get("principal") or {}).get("decides") or [],
        "vault_path": options["vault"],
        "today": options["today"],
        "posture": options["posture"],
        "seats": seats,
        "seat_count": len(seats),
        "staff": [s for s in seats if s["is_staff"]],
        "chart": _chart(seats, options["principal"]),
    }
    for template, target in ORG_WIDE.items():
        path = os.path.join(TEMPLATES, template)
        if not os.path.exists(path):
            raise OrgError(f"missing template: {path}")
        emit(template, target, minitemplate.render_file(path, org_context))

    manifest = os.path.join(out_dir, ".claude", "generated.json")
    _write(manifest, json.dumps(
        {"rendered": options["today"] or "unknown",
        "note": "Checked by lint_vault.py. A hand-edit to any file listed "
                 "here is reverted by the next `org update` — change "
                 "roles.yaml instead.",
         "files": generated},
        indent=2, sort_keys=True) + "\n")
    written.append(manifest)
    return written


def _chart(seats, principal):
    """An ASCII reporting tree, drawn from the seats actually generated."""
    children = {}
    for seat in seats:
        children.setdefault(seat["reports_to"], []).append(seat)

    lines = [f"{principal} — owner / CEO"]

    def walk(parent_key, prefix):
        kids = children.get(parent_key, [])
        for index, seat in enumerate(kids):
            last = index == len(kids) - 1
            elbow = "└── " if last else "├── "
            staff = " (staff)" if seat["is_staff"] else ""
            dotted = (
                f"  ·  dotted line to {seat['dotted_line_to_name']}"
                if seat["dotted_line_to_name"] else ""
            )
            lines.append(f"{prefix}{elbow}{seat['name']} — {seat['title']}{staff}{dotted}")
            walk(seat["role_id"], prefix + ("    " if last else "│   "))

    walk("principal", "")
    return "\n".join(lines)


def _sentence(text):
    """Terminate a fragment so it reads as a sentence when inlined."""
    text = str(text).strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _write(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)


# --------------------------------------------------------------------- cli ---


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render an org from roles.yaml")
    parser.add_argument("--principal", required=True, help="the human's name")
    parser.add_argument("--packs", default="core",
                        help="comma-separated packs; required packs are always added")
    parser.add_argument("--vault", required=True, help="path to the vault")
    parser.add_argument("--posture", default="balanced",
                        choices=["frugal", "balanced", "max"])
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--today", default="", help="date stamp for generated files")
    parser.add_argument("--plan", action="store_true",
                        help="print the org and write nothing")
    args = parser.parse_args(argv)

    spec = miniyaml.load(ROLES)
    validate_roles(spec)

    roles = select_roles(spec, [p.strip() for p in args.packs.split(",") if p.strip()])
    names = persona_ids(roles)

    options = {
        "principal": args.principal,
        "vault": os.path.expanduser(args.vault).rstrip("/"),
        "posture": args.posture,
        "today": args.today,
    }
    seats = build_seats(spec, roles, names, options)

    print(_chart(seats, args.principal))
    print()
    print(f"{len(seats)} personas · posture {args.posture}")
    for seat in seats:
        print(f"  {seat['name']:<16} {seat['title']:<34} {seat['model']}")

    if args.plan:
        print("\n--plan: nothing written")
        return 0

    written = render_org(seats, options, args.out, spec)
    print(f"\nwrote {len(written)} files to {args.out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OrgError, miniyaml.YamlSubsetError, minitemplate.TemplateError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
