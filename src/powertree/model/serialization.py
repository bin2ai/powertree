"""Custom project file format (.ptproj).

A .ptproj file is versioned JSON holding the whole project: every power tree
(elements, blocks, layout state) plus the hierarchical notes vault with
embedded images. Fully self-contained and diff-friendly.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Optional

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
        "trees": [_tree_to_dict(t) for t in project.trees],
        "notes": [dataclasses.asdict(n) for n in project.notes.values()],
    }


def project_from_dict(data: dict) -> Project:
    if data.get("format") != MAGIC:
        raise ValueError("Not a PowerTree project file (missing format marker).")
    version = data.get("version", 0)
    if version > FILE_FORMAT_VERSION:
        raise ValueError(
            f"Project file version {version} is newer than this app supports "
            f"({FILE_FORMAT_VERSION}). Please update PowerTree.")
    project = Project(data.get("name", "Project"))
    project.description = data.get("description", "")
    project.author = data.get("author", "")
    project.scenarios = list(data.get("scenarios", []))
    for t_data in data.get("trees", []):
        project.trees.append(_tree_from_dict(t_data))
    note_fields = {f.name for f in dataclasses.fields(Note)}
    for n_data in data.get("notes", []):
        note = Note(**{k: v for k, v in n_data.items() if k in note_fields})
        project.notes[note.id] = note
    return project


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
