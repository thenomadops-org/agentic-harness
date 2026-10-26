#!/usr/bin/env python3
"""Validate a project's `.agentic-os.yaml` (spec F3) and its docs/memory/ (spec F4).

    python3 validate.py [project PATH]     default PATH: ./.agentic-os.yaml
    python3 validate.py memory [DIR]       default DIR: ./docs/memory

Exit 0 valid, 1 invalid (every finding printed), 2 the input is missing.
The shapes are written out in SCHEMA.md; this file is what enforces them.
Stdlib only: the YAML reader is the vendored miniyaml.py (a documented subset
that refuses what it does not understand).
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import miniyaml  # noqa: E402

PROJECT_KEYS = {"board_project", "roles", "test", "build", "staging", "production"}
STAGING_KEYS = {"deploy", "url", "check"}
PRODUCTION_KEYS = {"commands", "same_environment_as_staging"}
SLUG = re.compile(r"^[a-z][a-z0-9-]*$")
URL = re.compile(r"^https?://[^\s/]+\S*$")
ENV_REF = re.compile(r"^env:[A-Z][A-Z0-9_]*$")
ENTRY_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*\.md$")
MEMORY_KEYS = ("title", "summary", "role", "links")


def _text(value):
    return isinstance(value, str) and value.strip() != ""


def _unknown(where, d, allowed):
    return [f"{where}: unknown key {k!r}" for k in d if k not in allowed]


def check_project_text(text):
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlSubsetError as e:
        return [f"not readable: {e}"]
    if not isinstance(data, dict):
        return ["the file must be a map of keys"]
    errs = _unknown("file", data, PROJECT_KEYS)
    for k in sorted(PROJECT_KEYS - set(data)):
        errs.append(f"{k}: required")
    if "board_project" in data and not (_text(data["board_project"]) and " " not in str(data["board_project"])):
        errs.append("board_project: must be a non-empty key with no spaces")
    if "roles" in data:
        roles = data["roles"]
        if not isinstance(roles, list) or not roles:
            errs.append("roles: must be a non-empty list")
        else:
            bad = [r for r in roles if not (isinstance(r, str) and SLUG.match(r))]
            if bad:
                errs.append(f"roles: each role must be a lowercase slug, got {bad!r}")
            if len(set(map(str, roles))) != len(roles):
                errs.append("roles: duplicates")
    for k in ("test", "build"):
        if k in data and not _text(data[k]):
            errs.append(f"{k}: must be a non-empty command")
    if "staging" in data:
        errs += _check_staging(data["staging"])
    if "production" in data:
        errs += _check_production(data["production"])
    return errs


def _check_staging(s):
    if not isinstance(s, dict):
        return ["staging: must be a map with deploy, url and check"]
    errs = _unknown("staging", s, STAGING_KEYS)
    for k in ("deploy", "check"):
        if k not in s:
            errs.append(f"staging.{k}: required")
        elif not _text(s[k]):
            errs.append(f"staging.{k}: must be non-empty text")
    if "url" not in s:
        errs.append("staging.url: required")
    elif not (isinstance(s["url"], str) and (URL.match(s["url"]) or ENV_REF.match(s["url"]))):
        errs.append("staging.url: must be an http(s) URL, or env:NAME naming the variable that holds it")
    return errs


def _check_production(p):
    if not isinstance(p, dict):
        return ["production: must be a map with commands and same_environment_as_staging"]
    errs = _unknown("production", p, PRODUCTION_KEYS)
    cmds = p.get("commands")
    if "commands" not in p:
        errs.append("production.commands: required")
    elif not isinstance(cmds, list) or not cmds or not all(_text(c) for c in cmds):
        errs.append("production.commands: must be a non-empty list of non-empty strings")
    elif len(set(cmds)) != len(cmds):
        errs.append("production.commands: duplicates")
    if "same_environment_as_staging" not in p:
        errs.append("production.same_environment_as_staging: required")
    elif not isinstance(p["same_environment_as_staging"], bool):
        errs.append("production.same_environment_as_staging: must be true or false")
    return errs


def run_project(path):
    path = pathlib.Path(path)
    if not path.is_file():
        return 2, f"missing input: {path}"
    errs = check_project_text(path.read_text(encoding="utf-8"))
    return (1, "\n".join(f"FAIL: {e}" for e in errs)) if errs else (0, f"{path}: ok")


def _split_frontmatter(text):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, None


def check_memory_dir(d):
    d = pathlib.Path(d)
    readme = d / "README.md"
    errs = []
    entries = sorted(p for p in d.glob("*.md") if p.name != "README.md")
    names = {p.name for p in entries}
    for p in entries:
        n = p.name
        if not ENTRY_NAME.match(n):
            errs.append(f"{n}: filename must be lowercase words joined by hyphens, ending .md")
        head, _ = _split_frontmatter(p.read_text(encoding="utf-8"))
        if head is None:
            errs.append(f"{n}: needs frontmatter between --- lines")
            continue
        try:
            fm = miniyaml.loads(head)
        except miniyaml.YamlSubsetError as e:
            errs.append(f"{n}: frontmatter not readable: {e}")
            continue
        if not isinstance(fm, dict):
            errs.append(f"{n}: frontmatter must be a map")
            continue
        for k in MEMORY_KEYS:
            if k not in fm:
                errs.append(f"{n}: frontmatter key {k!r} required")
        for k in ("title", "summary", "role"):
            if k in fm and not _text(fm[k]):
                errs.append(f"{n}: {k} must be non-empty text")
        errs += [f"{n}: unknown frontmatter key {k!r}" for k in fm if k not in MEMORY_KEYS]
        if "links" in fm:
            if not isinstance(fm["links"], list) or not all(isinstance(x, str) for x in fm["links"]):
                errs.append(f"{n}: links must be a list of entry filenames (may be empty)")
            else:
                errs += [f"{n}: link {x!r} names no entry in this directory" for x in fm["links"] if x not in names]
    if not readme.is_file():
        errs.append("README.md: the index is required")
    else:
        indexed = set(re.findall(r"\]\(([^)\s#]+\.md)\)", readme.read_text(encoding="utf-8")))
        errs += [f"{n}: not in the README.md index" for n in sorted(names - indexed)]
        errs += [f"README.md: index names {n} but no such entry exists" for n in sorted(indexed - names - {"README.md"})]
    return errs


def run_memory(d):
    d = pathlib.Path(d)
    if not d.is_dir():
        return 2, f"missing input: {d}"
    errs = check_memory_dir(d)
    return (1, "\n".join(f"FAIL: {e}" for e in errs)) if errs else (0, f"{d}: ok")


def main(argv):
    args = argv[1:]
    mode = "project"
    if args and args[0] in ("project", "memory"):
        mode, args = args[0], args[1:]
    if mode == "memory":
        code, out = run_memory(args[0] if args else "docs/memory")
    else:
        code, out = run_project(args[0] if args else ".agentic-os.yaml")
    print(out, file=sys.stderr if code == 2 else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
