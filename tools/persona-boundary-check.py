#!/usr/bin/env python3
"""Guard the public source against restoring configurable agent identities."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import miniyaml

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {
    "product", "engineer", "ios-engineer", "android-engineer",
    "devops", "qa", "sre", "lead",
}
FORBIDDEN = ("--theme", "--names", "org/naming/themes.yaml", "default_name")
SOURCES = (
    "README.md",
    "CLAUDE.md",
    "docs/EXTRACTION.md",
    ".claude/skills/setup-my-org/SKILL.md",
    ".claude/skills/org-update/SKILL.md",
    ".claude/skills/learn-repo/SKILL.md",
    ".claude/skills/merge-pr/SKILL.md",
    "org/roles.yaml",
    "org/templates/team-org.md.tmpl",
    "tools/setup.py",
    "tools/render.py",
)


def main():
    problems = []
    roles_path = ROOT / "org/roles.yaml"
    spec = miniyaml.load(str(roles_path))
    roles = spec.get("roles") or []
    ids = {role.get("id") for role in roles}
    if not EXPECTED.issubset(ids):
        problems.append(f"missing SDLC persona ids: {sorted(EXPECTED - ids)}")
    if ids - EXPECTED:
        problems.append(f"unexpected persona ids: {sorted(ids - EXPECTED)}")
    if any("default_name" in role for role in roles):
        problems.append("roles.yaml must not assign display names")
    if (ROOT / "org/naming/themes.yaml").exists():
        problems.append("org/naming/themes.yaml must not exist")

    for relative in SOURCES:
        path = ROOT / relative
        content = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in content:
                problems.append(f"{relative} contains retired identity selector {token!r}")

    if problems:
        print("persona-boundary-check: FAILED", file=sys.stderr)
        print("\n".join(f"  - {problem}" for problem in problems), file=sys.stderr)
        return 1
    print("persona-boundary-check: OK (role ids define all agent identities)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
