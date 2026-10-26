"""A very small mustache-shaped template renderer — stdlib only.

Same reasoning as `miniyaml`: no dependency is available on a clean machine, so
the choice is between a tiny renderer and a large one vendored badly.

## The rule that matters

**An unknown variable is a hard error.** Mustache's default is to render
nothing, which is exactly wrong here: a typo in `{{principal_name}}` would
produce an agent definition that reads fine, ships, and quietly tells an agent
it reports to no one. Templates that generate identities need to fail loudly.

## Supported

    {{name}}            substitute; missing key raises
    {{#key}}...{{/key}} section — list: repeat per item
                                  dict: render once with keys in scope
                                  truthy scalar: render once
                                  falsy/absent: skip
    {{^key}}...{{/key}} inverted section — render only when falsy or absent
    {{.}}               the current item, inside a list section
    {{! comment }}      dropped

Nothing else. No partials, no lambdas, no dotted paths — if a template needs
those, the shape of the data is wrong.
"""

import re

__all__ = ["render", "TemplateError"]

_TOKEN = re.compile(r"\{\{([#^/!]?)\s*([^}]*?)\s*\}\}")


class TemplateError(ValueError):
    """Raised for a malformed template or a missing variable."""


class _Section:
    __slots__ = ("key", "inverted", "children")

    def __init__(self, key, inverted):
        self.key = key
        self.inverted = inverted
        self.children = []


def _parse(source):
    root = _Section(None, False)
    stack = [root]
    position = 0

    for match in _TOKEN.finditer(source):
        literal = source[position : match.start()]
        if literal:
            stack[-1].children.append(literal)
        position = match.end()

        sigil, key = match.group(1), match.group(2)

        if sigil == "!":
            continue
        if sigil in ("#", "^"):
            section = _Section(key, sigil == "^")
            stack[-1].children.append(section)
            stack.append(section)
            continue
        if sigil == "/":
            if len(stack) == 1:
                raise TemplateError(f"closing {{{{/{key}}}}} with no open section")
            open_section = stack.pop()
            if open_section.key != key:
                raise TemplateError(
                    f"section mismatch: opened {{{{#{open_section.key}}}}}, "
                    f"closed {{{{/{key}}}}}"
                )
            continue

        if not key:
            raise TemplateError("empty {{ }} placeholder")
        stack[-1].children.append(("var", key))

    tail = source[position:]
    if tail:
        stack[-1].children.append(tail)

    if len(stack) != 1:
        unclosed = ", ".join(s.key for s in stack[1:])
        raise TemplateError(f"unclosed section(s): {unclosed}")
    return root


def _lookup(stack, key):
    """Innermost-first lookup across the context stack. Raises if absent."""
    if key == ".":
        for frame in reversed(stack):
            if isinstance(frame, dict) and "." in frame:
                return frame["."]
        raise TemplateError("{{.}} used outside a list section")
    for frame in reversed(stack):
        if isinstance(frame, dict) and key in frame:
            return frame[key]
    raise TemplateError(
        f"unknown variable {{{{{key}}}}} — templates fail loudly on purpose; "
        f"add it to the context or guard it with {{{{#{key}}}}}"
    )


def _present(stack, key):
    """Is `key` defined anywhere in scope? Sections may test absent keys."""
    if key == ".":
        return True
    return any(isinstance(f, dict) and key in f for f in stack)


def _stringify(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        raise TemplateError(
            "cannot substitute a list directly; use {{#key}}{{.}}{{/key}}"
        )
    if isinstance(value, dict):
        raise TemplateError("cannot substitute a mapping directly")
    return str(value)


def _render_nodes(nodes, stack, out):
    for node in nodes:
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, tuple):
            out.append(_stringify(_lookup(stack, node[1])))
        else:
            _render_section(node, stack, out)


def _render_section(section, stack, out):
    value = _lookup(stack, section.key) if _present(stack, section.key) else None

    if section.inverted:
        if not value:
            _render_nodes(section.children, stack, out)
        return

    if not value:
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            frame = dict(item) if isinstance(item, dict) else {}
            frame["."] = item
            _render_nodes(section.children, stack + [frame], out)
        return
    if isinstance(value, dict):
        _render_nodes(section.children, stack + [value], out)
        return
    _render_nodes(section.children, stack + [{".": value}], out)


def render(source, context):
    """Render `source` with `context`. Raises TemplateError on any gap."""
    out = []
    _render_nodes(_parse(source).children, [context], out)
    return "".join(out)


def render_file(path, context):
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    try:
        return render(source, context)
    except TemplateError as exc:
        raise TemplateError(f"{path}: {exc}") from None


def variables(source):
    """Every variable and section name a template references. For validation."""
    return {match.group(2) for match in _TOKEN.finditer(source)
            if match.group(1) not in ("!", "/") and match.group(2)}
