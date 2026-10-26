#!/usr/bin/env python3
"""Write one docs/memory/ entry for /retro, with its index line, and validate.

    python3 new_entry.py --dir docs/memory --name n.md --title T --summary S
        --role R [--links a.md,b.md] (--body TEXT | --body-file F) [--dry-run]

Validates the whole directory with ../onboard-project/validate.py afterwards;
on failure the entry and the index change are rolled back and the findings
printed. Exit 0, 1 (rejected), 2 (directory missing).
"""
import argparse
import importlib.util
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("validate", HERE.parent / "onboard-project" / "validate.py")
validate = importlib.util.module_from_spec(_s)
_s.loader.exec_module(validate)

PRIVATE = re.compile(r"\.ts\.net|Bearer\s+\S|/home/[a-z]+|\b(?:10|192\.168)\.\d+\.\d+(?:\.\d+)?\b")


def quote(v):
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(title, summary, role, links, body):
    fm = ["---", f"title: {quote(title)}", f"summary: {quote(summary)}", f"role: {quote(role)}",
          "links: [" + ", ".join(links) + "]", "---"]
    return "\n".join(fm) + "\n" + body.strip() + "\n"


def write_entry(d, name, title, summary, role, links, body, dry_run=False):
    """Return (code, findings)."""
    d = pathlib.Path(d)
    if not d.is_dir():
        return 2, [f"missing input: {d}"]
    entry, readme = d / name, d / "README.md"
    if entry.exists():
        return 1, [f"{name}: already exists; one lesson per file, edit it instead"]
    if not body.strip():
        return 1, ["body: the evidence is required"]
    if PRIVATE.search(" ".join([title, summary, body])):
        return 1, ["entry names a private host, address, token or home path"]
    before = readme.read_text(encoding="utf-8") if readme.exists() else None
    entry.write_text(render(title, summary, role, links, body), encoding="utf-8")
    line = f"- [{name}]({name}): {summary}\n"
    text = before if before is not None else "# Project memory\n\n## Index\n\n"
    readme.write_text(text + ("" if text.endswith("\n") else "\n") + line, encoding="utf-8")
    errs = validate.check_memory_dir(d)
    if errs or dry_run:
        entry.unlink()
        if before is None:
            readme.unlink()
        else:
            readme.write_text(before, encoding="utf-8")
    return (1, errs) if errs else (0, [])


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="docs/memory")
    ap.add_argument("--name", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--role", required=True)
    ap.add_argument("--links", default="")
    ap.add_argument("--body", default="")
    ap.add_argument("--body-file")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    body = pathlib.Path(a.body_file).read_text(encoding="utf-8") if a.body_file else a.body
    links = [x.strip() for x in a.links.split(",") if x.strip()]
    code, errs = write_entry(a.dir, a.name, a.title, a.summary, a.role, links, body, a.dry_run)
    for e in errs:
        print("FAIL:", e, file=sys.stderr if code == 2 else sys.stdout)
    if code == 0:
        print(("dry run ok: " if a.dry_run else "wrote ") + f"{a.dir}/{a.name}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
