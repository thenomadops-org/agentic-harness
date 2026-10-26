"""Proof that the YAML subset reader refuses what it claims to refuse.

A strict parser nobody has tried to break is just a lenient parser with a
confident docstring. This suite exists because the first version silently
accepted `a: &x 1` — the anchor check looked at the start of the line, and
anchors live in value position.

Run: python3 tools/test_miniyaml.py
Exit code is non-zero on failure, so it is usable as a gate.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from miniyaml import YamlSubsetError, load, loads  # noqa: E402

MUST_REFUSE = [
    ("anchor in value", "a: &x 1\nb: 2\n"),
    ("alias in value", "a: 1\nb: *x\n"),
    ("alias in sequence", "a:\n  - *x\n"),
    ("block scalar |", "a: |\n  hello\n"),
    ("block scalar >", "a: >\n  hello\n"),
    ("document marker", "---\na: 1\n"),
    ("tab indentation", "a:\n\tb: 1\n"),
    ("duplicate key", "a: 1\na: 2\n"),
    ("duplicate flow key", "a: {x: 1, x: 2}\n"),
    ("nested flow sequence", "a: [[1, 2]]\n"),
    ("nested flow map", "a: [{b: 1}]\n"),
    ("inconsistent indent", "a: 1\n   b: 2\n"),
    ("unterminated quote", 'a: "oops\n'),
    ("sequence where map expected", "a: 1\n- b\n"),
    ("empty sequence item", "a:\n  -\n"),
]

MUST_PARSE = [
    ("scalar types", "a: 1\nb: true\nc: null\nd: 1.5\ne: hi\n",
     {"a": 1, "b": True, "c": None, "d": 1.5, "e": "hi"}),
    ("quoted colon", 'a: "x: y"\n', {"a": "x: y"}),
    ("quoted booleans stay strings", 'a: "true"\nb: "null"\n',
     {"a": "true", "b": "null"}),
    ("flow sequence", "a: [x, y, z]\n", {"a": ["x", "y", "z"]}),
    ("flow map", "a: {b: 1, c: two}\n", {"a": {"b": 1, "c": "two"}}),
    ("sequence of maps", "r:\n  - id: a\n    n: 1\n  - id: b\n    n: 2\n",
     {"r": [{"id": "a", "n": 1}, {"id": "b", "n": 2}]}),
    ("nested block in item", "r:\n  - id: a\n    sub:\n      - one\n      - two\n",
     {"r": [{"id": "a", "sub": ["one", "two"]}]}),
    ("regex value", 'p: "^[A-Z][a-z]{1,11}$"\n', {"p": "^[A-Z][a-z]{1,11}$"}),
    ("trailing comment", "a: 1  # why\n", {"a": 1}),
    ("hash inside quotes", 'a: "not # a comment"\n', {"a": "not # a comment"}),
    ("empty value", "a:\nb: 1\n", {"a": None, "b": 1}),
]


def main():
    failures = []

    for name, source in MUST_REFUSE:
        try:
            loads(source)
        except YamlSubsetError:
            print(f"  ok      refuse  {name}")
        except Exception as exc:  # noqa: BLE001 - any other error is wrong
            failures.append(f"{name}: raised {type(exc).__name__}, want YamlSubsetError")
            print(f"  FAIL    refuse  {name}: {type(exc).__name__}")
        else:
            failures.append(f"{name}: accepted, should have been refused")
            print(f"  FAIL    refuse  {name}: accepted")

    for name, source, expected in MUST_PARSE:
        try:
            actual = loads(source)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: rejected valid input ({exc})")
            print(f"  FAIL    parse   {name}: {exc}")
            continue
        if actual != expected:
            failures.append(f"{name}: got {actual!r}, want {expected!r}")
            print(f"  FAIL    parse   {name}: got {actual!r}")
        else:
            print(f"  ok      parse   {name}")

    # The files this project actually ships must round-trip.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for relative in ("org/roles.yaml",):
        path = os.path.join(here, relative)
        if not os.path.exists(path):
            failures.append(f"{relative}: missing")
            print(f"  FAIL    real    {relative}: missing")
            continue
        try:
            data = load(path)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{relative}: {exc}")
            print(f"  FAIL    real    {relative}: {exc}")
            continue
        if not isinstance(data, dict) or not data:
            failures.append(f"{relative}: parsed to {type(data).__name__}")
            print(f"  FAIL    real    {relative}: not a non-empty mapping")
        else:
            print(f"  ok      real    {relative} ({len(data)} top-level keys)")

    print()
    if failures:
        print(f"FAILED — {len(failures)} problem(s)")
        for line in failures:
            print(f"  - {line}")
        return 1
    total = len(MUST_REFUSE) + len(MUST_PARSE) + 2
    print(f"PASS — {total} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
