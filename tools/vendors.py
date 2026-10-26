"""Plan a persona session for any vendor CLI, and bind one shared memory store.

The CLIs and their models live in org/vendors.yaml. Which persona uses which
vendor lives in org/routing.yaml. Adding a vendor is a new record in those
files. This module does not start a process; the caller passes a runner.

    python3 -c 'import sys; sys.path.insert(0, "tools"); import vendors; ...'
"""

import os
import shutil

import miniyaml
import render


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDORS_PATH = os.path.join(ROOT, "org", "vendors.yaml")
ROUTING_PATH = os.path.join(ROOT, "org", "routing.yaml")

POSTURES = ("frugal", "balanced", "max")
TIERS = ("lead", "specialist", "ic")


class VendorError(ValueError):
    """The vendor catalog or a routing decision cannot be applied."""


def load_vendors(path=None):
    """Return the vendor catalog document."""
    document = miniyaml.load(path or VENDORS_PATH)
    _validate_vendors(document)
    return document


def load_routing(path=None):
    """Return the routing document."""
    document = miniyaml.load(path or ROUTING_PATH)
    _validate_routing(document, None)
    return document


def plan_session(persona, ticket, installed, goal="", usage=None,
                 builder_vendor=None, posture="balanced", vendors_path=None,
                 routing_path=None, roles_path=None):
    """Choose a vendor and model and return the herdr argv. Do not run it."""
    catalog = load_vendors(vendors_path)
    routing = load_routing(routing_path)
    _validate_routing(routing, catalog)
    index = _index(catalog)
    vendor_ids = [record["id"] for record in catalog["vendors"]]
    installed_ids = _installed(installed, index)
    _check_usage(usage)
    role = _role_for(persona, _roles_spec(roles_path))
    route = _route_for(role["id"], routing)
    if route == "qa" and len(installed_ids) > 1 and not builder_vendor:
        raise VendorError(
            "qa requires the builder vendor when more than one vendor is installed"
        )
    if builder_vendor is not None and builder_vendor not in index:
        raise VendorError(f"unknown builder vendor {builder_vendor!r}")

    order = _preference(route, routing, vendor_ids)
    if route == "qa" and len(installed_ids) > 1:
        order = [vendor_id for vendor_id in order if vendor_id != builder_vendor]
    chosen = [vendor_id for vendor_id in order if vendor_id in installed_ids]
    if not chosen:
        raise VendorError("no installed vendor can take this session")

    floor = routing["usage_rebalance_below"]
    assigned = chosen[0]
    rebalanced = False
    below_floor = False
    # A missing reading is not evidence. Stay put when the assigned vendor has
    # no usage number, and only move to a vendor whose reading is above the floor.
    if _exhausted(usage, assigned, floor):
        alternative = next(
            (
                vendor_id for vendor_id in chosen
                if vendor_id != assigned and _known_above(usage, vendor_id, floor)
            ),
            None,
        )
        if alternative is None:
            below_floor = True
        else:
            assigned = alternative
            rebalanced = True

    record = index[assigned]
    model = _model(record, posture, role["tier"])
    pane = _pane(persona, ticket)
    return {
        "persona": persona,
        "ticket": ticket,
        "pane": pane,
        "vendor": assigned,
        "model": model,
        "tier": role["tier"],
        "route": route,
        "posture": posture,
        "rebalanced": rebalanced,
        "below_floor": below_floor,
        "argv": _argv(record, persona, pane, model, goal),
    }


def launch_persona(persona, ticket, installed, goal="", runner=None, **kwargs):
    """Plan a session and hand its argv to runner. There is no default runner."""
    plan = plan_session(persona, ticket, installed, goal=goal, **kwargs)
    if runner is None:
        raise VendorError("refusing to start a session without a runner")
    runner(plan["argv"])
    return plan


def bind_shared_memory(vault, vendors_path=None, routing_path=None):
    """Point every vendor memory path at one directory. Never copy.

    An existing real directory is moved into the store. Byte-identical files
    collapse to one. When two legacy directories hold different bytes at the
    same relative path, both are kept: the later copy is renamed, and the
    rename is printed. A file already in the store with different bytes is
    refused and left where it is.
    """
    catalog = load_vendors(vendors_path)
    routing = load_routing(routing_path)
    _validate_routing(routing, catalog)
    store_rel = routing["memory_store"]
    store = _vault_path(vault, store_rel)
    os.makedirs(store, exist_ok=True)

    claimed = {}
    reports = []
    actions = []
    for record in catalog["vendors"]:
        link_rel = record["memory_link"]
        if os.path.normpath(link_rel) == os.path.normpath(store_rel):
            continue
        link = _vault_path(vault, link_rel)
        action = _plan_link(link, store, claimed, record["id"], reports)
        if action is not None:
            actions.append(action)
    for action in actions:
        _apply_link(action, store)
    for line in reports:
        print(line)
    return store


def _validate_vendors(document):
    if not isinstance(document, dict) or document.get("version") != 1:
        raise VendorError("vendor catalog must be version 1")
    records = document.get("vendors")
    if not isinstance(records, list) or not records:
        raise VendorError("vendor catalog needs a vendors list")
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise VendorError("each vendor must be a record")
        ident = record.get("id")
        if not isinstance(ident, str) or not ident or ident in seen:
            raise VendorError(f"invalid vendor id {ident!r}")
        seen.add(ident)
        for key in ("command", "model_flag", "memory_link"):
            if not isinstance(record.get(key), str) or not record[key]:
                raise VendorError(f"{ident} needs a {key}")
        for flag in ("agent_flag", "session_flag"):
            value = record.get(flag)
            if value is not None and not isinstance(value, str):
                raise VendorError(f"{ident} {flag} must be a string or null")
        models = record.get("models")
        if not isinstance(models, dict):
            raise VendorError(f"{ident} needs models")
        for posture in POSTURES:
            row = models.get(posture)
            if not isinstance(row, dict):
                raise VendorError(f"{ident} needs {posture} models")
            for tier in TIERS:
                model = row.get(tier)
                if not isinstance(model, str) or not model:
                    raise VendorError(f"{ident} needs a {posture} {tier} model")


def _validate_routing(document, catalog):
    if not isinstance(document, dict) or document.get("version") != 1:
        raise VendorError("routing config must be version 1")
    floor = document.get("usage_rebalance_below")
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not 0 <= floor <= 1:
        raise VendorError("usage_rebalance_below must be a fraction from 0 to 1")
    if not isinstance(document.get("memory_store"), str) or not document["memory_store"]:
        raise VendorError("routing needs memory_store")
    if not isinstance(document.get("qa_persona"), str) or not document["qa_persona"]:
        raise VendorError("routing needs qa_persona")
    for key in ("build_vendors", "qa_vendors", "build_personas"):
        values = document.get(key)
        if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
            raise VendorError(f"routing {key} must be a list of names")
    if not isinstance(document.get("lead_vendor"), str) or not document["lead_vendor"]:
        raise VendorError("routing needs lead_vendor")
    if catalog is None:
        return
    known = {record["id"] for record in catalog["vendors"]}
    named = [document["lead_vendor"], *document["build_vendors"], *document["qa_vendors"]]
    unknown = [vendor_id for vendor_id in named if vendor_id not in known]
    if unknown:
        raise VendorError(f"routing names unknown vendor(s): {unknown}")


def _index(catalog):
    return {record["id"]: record for record in catalog["vendors"]}


def _installed(installed, index):
    if isinstance(installed, (str, bytes)) or not isinstance(installed, (list, tuple)):
        raise VendorError("installed vendors must be a list of ids")
    unknown = [vendor_id for vendor_id in installed if vendor_id not in index]
    if unknown:
        raise VendorError(f"unknown installed vendor(s): {unknown}")
    return list(installed)


def _check_usage(usage):
    if usage is None:
        return
    if not isinstance(usage, dict):
        raise VendorError("usage must be a map of vendor to remaining fraction")
    for vendor_id, value in usage.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise VendorError(f"usage for {vendor_id} must be a fraction from 0 to 1")


def _roles_spec(path):
    return miniyaml.load(path or render.ROLES)


def _role_for(persona, spec):
    _token(persona, "persona")
    roles = render.select_roles(spec, list(spec["packs"]))
    for role in roles:
        count = int(role.get("instances") or 1)
        names = (
            [role["id"]] if count == 1
            else [f"{role['id']}-{index + 1}" for index in range(count)]
        )
        if persona in names:
            return role
    known = render.persona_ids(roles)
    raise VendorError(f"unknown persona {persona!r}; known: {known}")


def _route_for(role_id, routing):
    if role_id == routing["qa_persona"]:
        return "qa"
    if role_id in routing["build_personas"]:
        return "build"
    return "lead"


def _preference(route, routing, vendor_ids):
    if route == "build":
        preferred = list(routing["build_vendors"])
    elif route == "qa":
        preferred = list(routing["qa_vendors"])
    else:
        preferred = [routing["lead_vendor"]]
    return preferred + [vendor_id for vendor_id in vendor_ids if vendor_id not in preferred]


def _exhausted(usage, vendor_id, floor):
    if not usage or vendor_id not in usage:
        return False
    return float(usage[vendor_id]) <= floor


def _known_above(usage, vendor_id, floor):
    if not usage or vendor_id not in usage:
        return False
    return float(usage[vendor_id]) > floor


def _model(record, posture, tier):
    if posture not in POSTURES:
        raise VendorError(f"unknown posture {posture!r}")
    return record["models"][posture][tier]


def _pane(persona, ticket):
    _token(ticket, "ticket")
    return f"{persona}-{ticket}"


def _token(value, label):
    if not isinstance(value, str) or not value or any(char.isspace() for char in value) or "/" in value:
        raise VendorError(f"{label} must be a single path-free token")
    return value


def _argv(record, persona, pane, model, goal):
    argv = ["herdr", "pane", "run", pane, record["command"], record["model_flag"], model]
    if record.get("agent_flag"):
        argv.extend([record["agent_flag"], persona])
    if record.get("session_flag"):
        argv.extend([record["session_flag"], pane])
    if goal:
        argv.append(goal)
    return argv


def _vault_path(vault, relative):
    if not isinstance(relative, str) or not relative or os.path.isabs(relative):
        raise VendorError(f"memory path must be vault-relative, got {relative!r}")
    parts = os.path.normpath(relative).split(os.sep)
    if ".." in parts:
        raise VendorError(f"memory path escapes the vault: {relative}")
    return os.path.join(vault, os.path.normpath(relative))


def _plan_link(link, store, claimed, vendor_id, reports):
    """Return a pending link, or None when the path already shares the store.

    claimed maps a store-relative path to the source file that will occupy it.
    Planning sees every legacy directory before any move, so two sources that
    share a name cannot overwrite each other.
    """
    if os.path.islink(link):
        if os.path.realpath(link) != os.path.realpath(store):
            raise VendorError(f"{os.path.basename(link)} already points somewhere else")
        return None
    if not os.path.exists(link):
        return {"link": link, "moves": [], "deletes": [], "replace_dir": False}
    if not os.path.isdir(link):
        raise VendorError(f"{link} exists and is not a directory")
    moves, deletes = [], []
    for dirpath, _dirnames, filenames in os.walk(link):
        for name in filenames:
            src = os.path.join(dirpath, name)
            rel = os.path.relpath(src, link)
            if rel in claimed:
                if _same_bytes(src, claimed[rel]):
                    deletes.append(src)
                    continue
                renamed = _renamed_relative(rel, vendor_id, claimed, store)
                reports.append(
                    f"memory: kept both copies of {rel}; "
                    f"renamed the {vendor_id} copy to {renamed}"
                )
                claimed[renamed] = src
                moves.append((src, os.path.join(store, renamed)))
                continue
            dst = os.path.join(store, rel)
            if os.path.lexists(dst):
                if os.path.isfile(src) and os.path.isfile(dst) and _same_bytes(src, dst):
                    deletes.append(src)
                    continue
                raise VendorError(
                    f"shared memory already has {rel} and {link} has different contents"
                )
            claimed[rel] = src
            moves.append((src, dst))
    return {"link": link, "moves": moves, "deletes": deletes, "replace_dir": True}


def _renamed_relative(rel, vendor_id, claimed, store):
    """Pick a free store-relative path for a second copy of rel."""
    directory, name = os.path.split(rel)
    stem, ext = os.path.splitext(name)
    number = 0
    while number < 1000:
        label = vendor_id if number == 0 else f"{vendor_id}-{number + 1}"
        filename = f"{stem}-{label}{ext}"
        candidate = os.path.join(directory, filename) if directory else filename
        if candidate not in claimed and not os.path.lexists(os.path.join(store, candidate)):
            return candidate
        number += 1
    raise VendorError(f"no free name for {rel}")


def _apply_link(action, store):
    link = action["link"]
    if action["replace_dir"]:
        for src, dst in action["moves"]:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
        for src in action["deletes"]:
            os.remove(src)
        shutil.rmtree(link)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    os.symlink(os.path.relpath(store, os.path.dirname(link)), link)


def _same_bytes(left, right):
    with open(left, "rb") as left_handle, open(right, "rb") as right_handle:
        return left_handle.read() == right_handle.read()
