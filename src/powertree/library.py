"""Component library — save blocks as reusable parts, share them as files.

A library PART is a device-template definition (same schema the JSON user
templates use) plus the block's designer style. Parts live in a per-user
library file (%APPDATA%/PowerTree/library.json, overridable via the
POWERTREE_LIBRARY env var), are merged into the template system everywhere
(template dialog, CLI, MCP), and can be exported/imported as .json files to
share between projects and people.
"""

from __future__ import annotations

import json
import os
import re

from .model.elements import (
    PowerTree, ElementKind,
)

LIBRARY_ENV = "POWERTREE_LIBRARY"

# element fields captured into a part, per kind (instance-specific fields
# like refdes/ids/positions are intentionally excluded)
_COMMON_FIELDS = ("signal_name", "part_number", "pins", "datasheet",
                  "description")
_KIND_FIELDS = {
    ElementKind.CONVERTER: ("topology", "ratio", "seq_order",
                            "efficiency_pct", "eff_points", "vout_min",
                            "vout_typ", "vout_max", "limit_type",
                            "limit_value", "quiescent_ma"),
    ElementKind.LOAD: ("load_type", "value_typ", "value_max",
                       "resistance_ohm", "duty_cycle_pct", "v_in_min",
                       "v_in_max"),
    ElementKind.SERIES: ("series_type", "resistance_ohm", "inductance_uh",
                         "rating", "i_max", "p_max", "v_in_min", "v_in_max"),
}
_STYLE_FIELDS = ("color", "width", "height", "pin_side", "pin_order",
                 "info_text", "show_stats")


PROJECT_LIB_ENV = "POWERTREE_PROJECT_LIB"
PROJECT_LIB_NAME = "powertree_library.json"


def library_path() -> str:
    env = os.environ.get(LIBRARY_ENV)
    if env:
        return env
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "PowerTree", "library.json")


def project_library_path() -> str | None:
    """Repo-committable library next to the open project (set by the GUI /
    POWERTREE_PROJECT_LIB) — lets teams version parts with their design."""
    return os.environ.get(PROJECT_LIB_ENV) or None


def load_parts(path: str) -> list:
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def load_library() -> list:
    return load_parts(library_path())


def save_library(parts: list, path: str | None = None) -> str:
    path = path or library_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(parts, fh, indent=2, ensure_ascii=False)
    return path


def _stamp_meta(part: dict, existing: dict | None) -> None:
    """Version/author/date metadata; version bumps when overwriting."""
    import getpass
    from datetime import date
    meta = dict(part.get("meta") or {})
    prev = (existing or {}).get("meta") or {}
    meta["version"] = int(prev.get("version", 0)) + 1
    meta.setdefault("author", None)
    if not meta["author"]:
        try:
            meta["author"] = getpass.getuser()
        except Exception:
            meta["author"] = "unknown"
    meta["updated"] = date.today().isoformat()
    part["meta"] = meta


def add_part(part: dict, path: str | None = None) -> dict:
    _validate_part(part)
    parts = load_parts(path or library_path())
    existing = next((p for p in parts if p.get("key") == part["key"]), None)
    _stamp_meta(part, existing)
    parts = [p for p in parts if p.get("key") != part["key"]]
    parts.append(part)
    save_library(parts, path)
    return part


def remove_part(key: str, path: str | None = None) -> bool:
    target = path or library_path()
    parts = load_parts(target)
    kept = [p for p in parts if p.get("key") != key]
    if len(kept) < len(parts):
        save_library(kept, target)
        return True
    return False


def export_library(path: str) -> str:
    """Export the entire user library to one shareable file."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(load_library(), fh, indent=2, ensure_ascii=False)
    return path


def _validate_part(part: dict) -> None:
    for field_name in ("key", "name", "items"):
        if not part.get(field_name):
            raise ValueError(f"Library part is missing '{field_name}'.")
    for item in part["items"]:
        if item.get("kind") not in ("converter", "load", "series"):
            raise ValueError(
                f"Item '{item.get('name')}' has unsupported kind "
                f"'{item.get('kind')}' (sources cannot be part of a "
                "library part).")
        if not item.get("rail"):
            raise ValueError(f"Item '{item.get('name')}' has no rail.")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "part"


def block_to_part(tree: PowerTree, block_id: str, key: str = "",
                  name: str = "", category: str = "My Library") -> dict:
    """Capture a block (members, internal topology, external rails and the
    designer style) as a reusable library part."""
    from .ui.layout import _net_of
    block = tree.blocks[block_id]
    src = tree.source
    members = [m for m in tree.block_members(block_id)
               if src is None or m.id != src.id]
    if not members:
        raise ValueError(f"Block '{block.name}' has no members to save.")
    member_set = {m.id for m in members}

    # unique display names for '@parent' references
    names: dict = {}
    used: set = set()
    for m in members:
        n = m.name
        i = 2
        while n in used:
            n = f"{m.name} #{i}"
            i += 1
        used.add(n)
        names[m.id] = n

    # parents first so '@' references always point backwards
    ordered: list = []
    remaining = list(members)
    while remaining:
        progressed = False
        for m in list(remaining):
            parent = tree.parent_of(m)
            if parent is None or parent.id not in member_set or \
                    parent.id in {x.id for x in ordered}:
                ordered.append(m)
                remaining.remove(m)
                progressed = True
        if not progressed:       # cycle cannot happen in a tree; safety net
            ordered.extend(remaining)
            break

    rails: list = []
    items: list = []
    for m in ordered:
        parent = tree.parent_of(m)
        if parent is not None and parent.id in member_set:
            rail = "@" + names[parent.id]
        else:
            rail = _net_of(tree, parent) if parent is not None else "VIN"
            if rail not in rails:
                rails.append(rail)
        params: dict = {}
        for field_name in _COMMON_FIELDS + _KIND_FIELDS.get(m.kind, ()):
            value = getattr(m, field_name, None)
            if value not in (None, "", [], {}):
                params[field_name] = value
        items.append({"kind": m.kind, "name": names[m.id], "rail": rail,
                      "params": params})

    style = {}
    for field_name in _STYLE_FIELDS:
        value = getattr(block, field_name, None)
        if value not in (None, "", {}, []):
            style[field_name] = value

    part = {
        "key": key or _slug(name or block.name),
        "name": name or block.name,
        "category": category,
        "description": block.description or
        f"Saved from block '{block.name}' ({len(items)} elements).",
        "rails": rails,
        "items": items,
        "block_style": style,
    }
    _validate_part(part)
    return part


def instantiate_part(tree: PowerTree, part: dict, rail_map: dict,
                     block_name: str = "", refdes: str = "") -> list:
    """Place a library part into a tree (template instantiation + the saved
    block designer style)."""
    from .templates import template_from_dict, instantiate_template
    template = template_from_dict(part)
    created = instantiate_template(tree, template, rail_map,
                                   block_name=block_name or part["name"],
                                   refdes=refdes)
    if created and part.get("block_style"):
        block = tree.blocks.get(created[0].block_id)
        if block is not None:
            for field_name in _STYLE_FIELDS:
                if field_name in part["block_style"]:
                    setattr(block, field_name,
                            part["block_style"][field_name])
    return created


def export_part(part: dict, path: str) -> str:
    _validate_part(part)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(part, fh, indent=2, ensure_ascii=False)
    return path


def import_part(path: str, add_to_library: bool = True,
                on_conflict: str = "overwrite") -> list:
    """Import one part (or a list of parts) from a JSON file.
    on_conflict: 'overwrite' (version bumps), 'skip', or 'rename'
    (imported part gets a fresh '<key>_2' style key)."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    parts = data if isinstance(data, list) else [data]
    existing_keys = {p.get("key") for p in load_library()}
    imported = []
    for part in parts:
        _validate_part(part)
        if part["key"] in existing_keys:
            if on_conflict == "skip":
                continue
            if on_conflict == "rename":
                base = part["key"]
                i = 2
                while f"{base}_{i}" in existing_keys:
                    i += 1
                part = dict(part, key=f"{base}_{i}",
                            name=f"{part['name']} ({i})")
        if add_to_library:
            add_part(part)
        existing_keys.add(part["key"])
        imported.append(part)
    return imported
