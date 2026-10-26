"""A deliberately small YAML reader — stdlib only.

Agentic-OS cannot assume PyYAML. Modern distributions ship an
externally-managed Python (PEP 668), so `pip install pyyaml` fails on a clean
machine, and asking someone to build a virtualenv before their org exists is a
bad first impression.

The alternative to a dependency is a hand-rolled parser, and hand-rolled YAML
parsers are a well-known source of quiet wrongness — they accept something they
half-understand and hand back a structure that is subtly not what the file said.

So this one is built the other way round. It supports a **documented subset**
and **raises on everything else**, with a line number. It will refuse files that
real YAML would happily read. That is the point: a loud refusal is recoverable,
a silent misparse in an org chart is not.

## Supported

    key: value                 scalars: str, int, float, bool, null
    key:                       nested block map (indented)
    key:                       block sequence (indented `- `)
      - item
    key: [a, b, c]             flow sequence, scalars only
    key: {a: 1, b: "two"}      flow map, scalars only
    - key: value               sequence of maps
      other: value
    "quoted: strings"          single or double quotes
    # comments                 whole-line and trailing

## Refused, by design

    &anchors / *aliases        aliasing hides structure
    | and > block scalars      multi-line text belongs in a template
    --- document markers       one document per file
    tabs for indentation       ambiguous width
    nested flow collections    [[1,2]] or {a: [1]}
    duplicate keys in a map    almost always a mistake

Every refusal names the line.
"""

__all__ = ["load", "loads", "YamlSubsetError"]


class YamlSubsetError(ValueError):
    """Raised for anything outside the supported subset."""

    def __init__(self, message, lineno=None, line=None):
        self.lineno = lineno
        self.line = line
        if lineno is not None:
            message = f"line {lineno}: {message}"
            if line is not None:
                message += f"\n    {line.rstrip()}"
        super().__init__(message)


class _Line:
    __slots__ = ("indent", "text", "lineno", "raw")

    def __init__(self, indent, text, lineno, raw):
        self.indent = indent
        self.text = text
        self.lineno = lineno
        self.raw = raw

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"_Line({self.indent}, {self.text!r}, {self.lineno})"


def loads(text):
    """Parse a YAML-subset string into Python data."""
    lines = _tokenize(text)
    if not lines:
        return None
    value, index = _parse_block(lines, 0, lines[0].indent)
    if index != len(lines):
        raise YamlSubsetError(
            "unexpected content after the document ended "
            "(check for inconsistent indentation)",
            lines[index].lineno,
            lines[index].raw,
        )
    return value


def load(path):
    """Parse a YAML-subset file into Python data."""
    with open(path, "r", encoding="utf-8") as handle:
        try:
            return loads(handle.read())
        except YamlSubsetError as exc:
            raise YamlSubsetError(f"{path}: {exc}") from None


# --------------------------------------------------------------- tokenize ---


def _tokenize(text):
    """Strip comments and blank lines; return significant lines with indents."""
    out = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlSubsetError("tab in indentation; use spaces", number, raw)

        stripped = _strip_comment(raw, number)
        if not stripped.strip():
            continue

        content = stripped.strip()
        if content.startswith("---") or content.startswith("..."):
            raise YamlSubsetError(
                "document markers are not supported; use one document per file",
                number,
                raw,
            )
        for token, why in (
            ("&", "anchors are not supported"),
            ("*", "aliases are not supported"),
        ):
            if content.lstrip("- ").startswith(token):
                raise YamlSubsetError(why, number, raw)
        if content.endswith("|") or content.endswith(">"):
            raise YamlSubsetError(
                "block scalars (| and >) are not supported; "
                "put multi-line text in a template file",
                number,
                raw,
            )

        indent = len(stripped) - len(stripped.lstrip(" "))
        out.append(_Line(indent, content, number, raw))
    return out


def _strip_comment(raw, lineno):
    """Remove a trailing comment, respecting quotes."""
    quote = None
    for position, char in enumerate(raw):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#":
            # A '#' only starts a comment at line start or after whitespace.
            if position == 0 or raw[position - 1] in " \t":
                return raw[:position]
    if quote:
        raise YamlSubsetError("unterminated quoted string", lineno, raw)
    return raw


# ------------------------------------------------------------------ parse ---


def _parse_block(lines, index, indent):
    """Parse a block (map or sequence) at `indent`. Return (value, next_index)."""
    if lines[index].text.startswith("- ") or lines[index].text == "-":
        return _parse_sequence(lines, index, indent)
    return _parse_map(lines, index, indent)


def _parse_map(lines, index, indent):
    result = {}
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise YamlSubsetError(
                f"unexpected indent (expected {indent}, got {line.indent})",
                line.lineno,
                line.raw,
            )
        if line.text.startswith("- "):
            raise YamlSubsetError(
                "sequence item where a mapping key was expected",
                line.lineno,
                line.raw,
            )

        key, rest = _split_key(line)
        if key in result:
            raise YamlSubsetError(f"duplicate key {key!r}", line.lineno, line.raw)

        if rest:
            result[key] = _parse_scalar_or_flow(rest, line)
            index += 1
            continue

        # Value is a nested block on the following lines, or empty.
        if index + 1 < len(lines) and lines[index + 1].indent > indent:
            result[key], index = _parse_block(
                lines, index + 1, lines[index + 1].indent
            )
        else:
            result[key] = None
            index += 1
    return result, index


def _parse_sequence(lines, index, indent):
    result = []
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise YamlSubsetError(
                f"unexpected indent in sequence (expected {indent}, "
                f"got {line.indent})",
                line.lineno,
                line.raw,
            )
        if not (line.text.startswith("- ") or line.text == "-"):
            break

        item = line.text[2:].strip() if line.text != "-" else ""

        if not item:
            # `-` alone: the item is the indented block beneath it.
            if index + 1 >= len(lines) or lines[index + 1].indent <= indent:
                raise YamlSubsetError(
                    "empty sequence item", line.lineno, line.raw
                )
            value, index = _parse_block(lines, index + 1, lines[index + 1].indent)
            result.append(value)
            continue

        if _looks_like_key(item):
            # A map that begins on the dash line. Its remaining keys are
            # indented to where this item's text starts.
            item_indent = line.indent + 2
            synthetic = _Line(item_indent, item, line.lineno, line.raw)
            block = [synthetic]
            index += 1
            while index < len(lines) and lines[index].indent >= item_indent:
                if lines[index].indent > item_indent and not _is_continuation(
                    lines, index, item_indent
                ):
                    raise YamlSubsetError(
                        "unexpected indent inside sequence item",
                        lines[index].lineno,
                        lines[index].raw,
                    )
                block.append(lines[index])
                index += 1
            value, consumed = _parse_map(block, 0, item_indent)
            if consumed != len(block):
                leftover = block[consumed]
                raise YamlSubsetError(
                    "could not parse sequence item", leftover.lineno, leftover.raw
                )
            result.append(value)
            continue

        result.append(_parse_scalar_or_flow(item, line))
        index += 1
    return result, index


def _is_continuation(lines, index, item_indent):
    """True when a deeper line belongs to a nested block inside a list item."""
    for back in range(index - 1, -1, -1):
        if lines[back].indent <= item_indent:
            return lines[back].indent == item_indent
    return False


def _looks_like_key(text):
    """Does this sequence item open a mapping (`key: ...`) rather than a scalar?"""
    if text[0] in "\"'":
        return False
    if text.startswith("[") or text.startswith("{"):
        return False
    head = text.split(":", 1)
    if len(head) < 2:
        return False
    # `key: value` needs a space after the colon; `12:30` is a scalar.
    return head[1] == "" or head[1].startswith(" ")


def _split_key(line):
    text = line.text
    if text[0] in "\"'":
        quote = text[0]
        end = text.find(quote, 1)
        if end == -1:
            raise YamlSubsetError("unterminated key", line.lineno, line.raw)
        key = text[1:end]
        rest = text[end + 1 :].lstrip()
        if not rest.startswith(":"):
            raise YamlSubsetError("expected ':' after key", line.lineno, line.raw)
        return key, rest[1:].strip()

    if ":" not in text:
        raise YamlSubsetError(
            "expected 'key: value' or 'key:'", line.lineno, line.raw
        )
    key, _, rest = text.partition(":")
    rest = rest.strip()
    key = key.strip()
    if not key:
        raise YamlSubsetError("empty key", line.lineno, line.raw)
    return key, rest


# ---------------------------------------------------------------- scalars ---


def _parse_scalar_or_flow(text, line):
    if text.startswith("["):
        if not text.endswith("]"):
            raise YamlSubsetError(
                "flow sequence must open and close on one line",
                line.lineno,
                line.raw,
            )
        return [
            _scalar(item, line) for item in _split_flow(text[1:-1], line)
        ]
    if text.startswith("{"):
        if not text.endswith("}"):
            raise YamlSubsetError(
                "flow map must open and close on one line", line.lineno, line.raw
            )
        result = {}
        for pair in _split_flow(text[1:-1], line):
            key, sep, value = pair.partition(":")
            if not sep:
                raise YamlSubsetError(
                    f"flow map entry {pair!r} is not 'key: value'",
                    line.lineno,
                    line.raw,
                )
            key = _scalar(key.strip(), line)
            if key in result:
                raise YamlSubsetError(
                    f"duplicate key {key!r} in flow map", line.lineno, line.raw
                )
            result[key] = _scalar(value.strip(), line)
        return result
    return _scalar(text, line)


def _split_flow(body, line):
    """Split a flow collection on commas, respecting quotes. Reject nesting."""
    items, current, quote = [], [], None
    for char in body:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            current.append(char)
        elif char in "[]{}":
            raise YamlSubsetError(
                "nested flow collections are not supported", line.lineno, line.raw
            )
        elif char == ",":
            items.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if quote:
        raise YamlSubsetError("unterminated quoted string", line.lineno, line.raw)
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return [item for item in items if item]


_BOOL = {"true": True, "false": False, "yes": True, "no": False,
         "on": True, "off": False}
_NULL = {"null", "~", ""}


def _scalar(text, line):
    if not text:
        return None
    # Anchors and aliases live in VALUE position (`a: &x 1`), so checking the
    # start of the line misses them entirely. Found by the refusal test.
    if text[0] == "&":
        raise YamlSubsetError("anchors are not supported", line.lineno, line.raw)
    if text[0] == "*":
        raise YamlSubsetError("aliases are not supported", line.lineno, line.raw)
    if text[0] in "\"'":
        quote = text[0]
        if len(text) < 2 or text[-1] != quote:
            raise YamlSubsetError("unterminated quoted string", line.lineno, line.raw)
        return text[1:-1]

    lowered = text.lower()
    if lowered in _NULL:
        return None
    if lowered in _BOOL:
        return _BOOL[lowered]

    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


# ------------------------------------------------------------- self-check ---

if __name__ == "__main__":  # pragma: no cover
    import sys

    if len(sys.argv) < 2:
        print("usage: miniyaml.py <file.yaml> [...]", file=sys.stderr)
        raise SystemExit(2)
    for path in sys.argv[1:]:
        data = load(path)
        kind = type(data).__name__
        size = len(data) if hasattr(data, "__len__") else "-"
        print(f"ok  {path}  ({kind}, {size} top-level)")
