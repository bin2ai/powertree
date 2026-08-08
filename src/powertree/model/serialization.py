"""Custom project file format (.ptproj).

A .ptproj file is versioned JSON holding the whole project: every power tree
(elements, blocks, layout state) plus the hierarchical notes vault with
embedded images. Fully self-contained and diff-friendly.
"""

from __future__ import annotations

import dataclasses
import json

from .. import FILE_FORMAT_VERSION
from .elements import (
    Project, PowerTree, Block, Note, ELEMENT_CLASSES, Element,
)

MAGIC = "powertree-project"


def _element_to_dict(el: Element) -> dict:
    data = dataclasses.asdict(el)
    # drop empty per-state buckets the GUI may have created while browsing
    overrides = data.get("scenario_overrides") or {}
    data["scenario_overrides"] = {k: v for k, v in overrides.items() if v}
    return data


def _element_from_dict(data: dict) -> Element:
    kind = data.get("kind", "")
    cls = ELEMENT_CLASSES.get(kind)
    if cls is None:
        raise ValueError(f"Unknown element kind in file: {kind!r}")
    fields = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in fields})


def _tree_to_dict(tree: PowerTree) -> dict:
    return {
        "id": tree.id,
        "name": tree.name,
        "description": tree.description,
        "orientation": tree.orientation,
        "detail_default": tree.detail_default,
        "elements": [_element_to_dict(e) for e in tree.elements.values()],
        "blocks": [dataclasses.asdict(b) for b in tree.blocks.values()],
    }


def _tree_from_dict(data: dict) -> PowerTree:
    tree = PowerTree(data.get("name", "Power Tree"), tree_id=data.get("id"))
    tree.description = data.get("description", "")
    tree.orientation = data.get("orientation", "TD")
    tree.detail_default = data.get("detail_default", "")
    for el_data in data.get("elements", []):
        el = _element_from_dict(el_data)
        tree.elements[el.id] = el
    for b_data in data.get("blocks", []):
        fields = {f.name for f in dataclasses.fields(Block)}
        block = Block(**{k: v for k, v in b_data.items() if k in fields})
        tree.blocks[block.id] = block
    return tree


def project_to_dict(project: Project) -> dict:
    return {
        "format": MAGIC,
        "version": FILE_FORMAT_VERSION,
        "name": project.name,
        "description": project.description,
        "author": project.author,
        "scenarios": list(project.scenarios),
        "derating_pct": project.derating_pct,
        "waivers": list(project.waivers),
        "logo_b64": project.logo_b64,
        "trees": [_tree_to_dict(t) for t in project.trees],
        "notes": [dataclasses.asdict(n) for n in project.notes.values()],
    }


# ---------------------------------------------------------------------------
# schema migrations: MIGRATIONS[n] upgrades a version-n payload to n+1.
# Older files are upgraded step-by-step on load; saving always writes the
# current FILE_FORMAT_VERSION.
# ---------------------------------------------------------------------------
MIGRATIONS: dict = {
    # 0 -> 1: pre-release files without an explicit version field
    0: lambda data: data,
}


def migrate(data: dict) -> dict:
    version = data.get("version", 0)
    while version < FILE_FORMAT_VERSION:
        upgrade = MIGRATIONS.get(version)
        if upgrade is None:
            raise ValueError(
                f"No migration path from project version {version}.")
        data = upgrade(data)
        version += 1
        data["version"] = version
    return data


def project_from_dict(data: dict) -> Project:
    if data.get("format") != MAGIC:
        raise ValueError("Not a PowerTree project file (missing format marker).")
    version = data.get("version", 0)
    if version > FILE_FORMAT_VERSION:
        raise ValueError(
            f"Project file version {version} is newer than this app supports "
            f"({FILE_FORMAT_VERSION}). Please update PowerTree.")
    if version < FILE_FORMAT_VERSION:
        data = migrate(data)
    project = Project(data.get("name", "Project"))
    project.description = data.get("description", "")
    project.author = data.get("author", "")
    project.scenarios = list(data.get("scenarios", []))
    project.derating_pct = float(data.get("derating_pct", 80.0))
    project.waivers = list(data.get("waivers", []))
    project.logo_b64 = data.get("logo_b64", "")
    for t_data in data.get("trees", []):
        project.trees.append(_tree_from_dict(t_data))
    note_fields = {f.name for f in dataclasses.fields(Note)}
    for n_data in data.get("notes", []):
        note = Note(**{k: v for k, v in n_data.items() if k in note_fields})
        project.notes[note.id] = note
    return project


SUBTREE_KEY = "powertree_subtree"


def subtree_to_dicts(tree: PowerTree, element_id: str) -> list:
    """Serialize an element and its descendants (parent-first order) for
    clipboard copy/paste across trees, projects and app instances."""
    root = tree.elements[element_id]
    out = [_element_to_dict(root)]
    for d in tree.descendants_of(element_id):
        out.append(_element_to_dict(d))
    return out


def dicts_to_subtree(tree: PowerTree, dicts: list, parent_id: str):
    """Recreate a copied subtree under parent_id with fresh ids. Returns the
    new root element. Raises ValueError on invalid content/attachment."""
    from .elements import new_id
    if not dicts:
        raise ValueError("Clipboard holds no elements.")
    id_map: dict = {}
    created = []
    try:
        for i, data in enumerate(dicts):
            el = _element_from_dict(data)
            old_id = el.id
            el.id = new_id()
            el.x = el.y = None
            el.block_id = None       # blocks don't travel with a subtree
            id_map[old_id] = el.id
            target_parent = parent_id if i == 0 \
                else id_map.get(el.parent_id)
            if i > 0 and target_parent is None:
                raise ValueError("Clipboard subtree is inconsistent.")
            tree.add_element(el, parent_id=target_parent)
            created.append(el)
    except ValueError:
        for el in created:            # atomic: roll back partial paste
            tree.elements.pop(el.id, None)
        raise
    return created[0]


def save_project(project: Project, path: str) -> None:
    payload = json.dumps(project_to_dict(project), indent=2, ensure_ascii=False)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(payload)
    project.file_path = path


def load_project(path: str) -> Project:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    project = project_from_dict(data)
    project.file_path = path
    return project
