#!/usr/bin/env python3
"""Check the workforce plugin's shape (portable-workforce spec F1).

    python3 plugin/check_plugin.py [repo-root]

Exit 0 when the plugin is well formed, 1 on any finding, 2 when an input the
check needs is missing. Every counter must be non-zero: a check that found no
agents or no skills has looked at nothing, and says so rather than passing.

What it enforces:
  - plugin.json has a name and a version; the root marketplace lists a plugin
    of that name whose source is the plugin directory;
  - every skill and agent has name and description frontmatter;
  - hooks/ and lessons/ exist.

The daemon copy of the role agents (tools/markdown-backend/roleagents) was
removed in OPS-333. This check no longer compares plugin/agents to it.

Pinned gap: frontmatter is read as a leading block of `key: value` lines, not
parsed as YAML; a multi-line value is not understood. The real runtime check is
`claude plugin validate --strict plugin`, which CI cannot assume is installed.
"""
import json
import pathlib
import sys


def frontmatter_keys(text):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    keys = set()
    for line in lines[1:]:
        if line.strip() == "---":
            return keys
        if ":" in line and not line.startswith((" ", "\t", "-")):
            keys.add(line.split(":", 1)[0].strip())
    return None  # never closed


def check(root):
    root = pathlib.Path(root)
    plugin = root / "plugin"
    findings = []
    census = {"agents": 0, "skills": 0}

    manifest = plugin / ".claude-plugin" / "plugin.json"
    market = root / ".claude-plugin" / "marketplace.json"
    for need in (manifest, market):
        if not need.exists():
            print(f"missing input: {need}", file=sys.stderr)
            return 2, census
    try:
        pj = json.loads(manifest.read_text(encoding="utf-8"))
        mj = json.loads(market.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return 1, {"agents": 0, "skills": 0, "error": str(e)}

    if not pj.get("name") or not pj.get("version"):
        findings.append("plugin.json needs a name and a version")
    entries = [p for p in mj.get("plugins", []) if p.get("name") == pj.get("name")]
    if not entries:
        findings.append(f"marketplace.json lists no plugin named {pj.get('name')!r}")
    for e in entries:
        src = e.get("source")
        if not isinstance(src, str) or (root / src).resolve() != plugin.resolve():
            findings.append(f"marketplace source {src!r} does not point at plugin/")

    shipped = {p.name: p for p in sorted((plugin / "agents").glob("*.md"))} if (plugin / "agents").is_dir() else {}
    census["agents"] = len(shipped)
    for name, p in shipped.items():
        keys = frontmatter_keys(p.read_text(encoding="utf-8"))
        if keys is None or not {"name", "description"} <= keys:
            findings.append(f"agents/{name}: frontmatter needs name and description")

    skills = sorted(d for d in (plugin / "skills").iterdir() if d.is_dir()) if (plugin / "skills").is_dir() else []
    census["skills"] = len(skills)
    for d in skills:
        f = d / "SKILL.md"
        keys = frontmatter_keys(f.read_text(encoding="utf-8")) if f.exists() else None
        if keys is None or not {"name", "description"} <= keys:
            findings.append(f"skills/{d.name}: SKILL.md needs name and description frontmatter")

    for d in ("hooks", "lessons"):
        if not (plugin / d).is_dir():
            findings.append(f"plugin/{d}/ is missing")
    for k, v in census.items():
        if v == 0:
            findings.append(f"census: zero {k} examined; the check looked at nothing")

    for f in findings:
        print("FAIL:", f)
    return (1 if findings else 0), census


if __name__ == "__main__":
    code, census = check(sys.argv[1] if len(sys.argv) > 1 else ".")
    if code == 0:
        print(f"plugin ok: {census}")
    sys.exit(code)
