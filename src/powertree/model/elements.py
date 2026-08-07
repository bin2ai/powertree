"""Core data model: Project -> PowerTree -> Elements (+ Blocks, Notes).

All electrical values are stored in SI units (volts, amps, watts, ohms).
Efficiency is stored as a percentage (0..100].
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class ElementKind:
    SOURCE = "source"
    CONVERTER = "converter"
    LOAD = "load"
    SERIES = "series"
    ALL = (SOURCE, CONVERTER, LOAD, SERIES)


class LoadType:
    CURRENT = "current"
    POWER = "power"


class LimitType:
    NONE = "none"
    CURRENT = "current"
    POWER = "power"


# Bounding for series resistance so the math never breaks.
R_MIN = 1e-6
R_MAX = 1e9
EFF_MIN = 1.0    # percent
EFF_MAX = 100.0
V_EPS = 1e-9


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass
class Element:
    """Base class for every node in a power tree."""
    id: str = field(default_factory=new_id)
    kind: str = ""
    name: str = "element"
    # --- shared metadata ---
    signal_name: str = ""
    refdes: str = ""
    part_number: str = ""
    pins: str = ""              # free text: pin name/number(s)
    description: str = ""       # free-text notes on the element itself
    datasheet: str = ""         # link / path to reference document
    # --- structure ---
    parent_id: Optional[str] = None
    block_id: Optional[str] = None
    note_ids: list = field(default_factory=list)   # linked documentation notes
    # --- operating states: scenario name -> {field: value} overrides ---
    scenario_overrides: dict = field(default_factory=dict)
    # --- UI state (persisted) ---
    collapsed: bool = False
    x: Optional[float] = None   # custom layout position
    y: Optional[float] = None
    # card verbosity: None = inherit tree/app; 'minimal'|'standard'|'exhaustive'
    display_detail: Optional[str] = None

    def meta_dict(self) -> dict:
        return {
            "signal_name": self.signal_name,
            "refdes": self.refdes,
            "part_number": self.part_number,
            "pins": self.pins,
            "description": self.description,
            "datasheet": self.datasheet,
        }


@dataclass
class Source(Element):
    kind: str = ElementKind.SOURCE
    name: str = "Source"
    v_min: float = 3.0
    v_typ: float = 3.3
    v_max: float = 3.6
    limit_type: str = LimitType.NONE   # none | current | power
    limit_value: float = 0.0


@dataclass
class Converter(Element):
    kind: str = ElementKind.CONVERTER
    name: str = "Converter"
    topology: str = "buck"             # buck | boost | buck-boost | ldo | isolated | generic
    efficiency_pct: float = 90.0
    vout_min: float = 1.71
    vout_typ: float = 1.8
    vout_max: float = 1.89
    limit_type: str = LimitType.NONE   # optional output limit
    limit_value: float = 0.0
    quiescent_ma: float = 0.0          # own operating current drawn from input

    @property
    def efficiency(self) -> float:
        return clamp(self.efficiency_pct, EFF_MIN, EFF_MAX) / 100.0


@dataclass
class Load(Element):
    kind: str = ElementKind.LOAD
    name: str = "Load"
    load_type: str = LoadType.CURRENT   # current | power  (resistive not supported yet)
    value_typ: float = 0.010            # A or W depending on load_type
    value_max: Optional[float] = None   # optional peak value
    # Allowed input-voltage operating window (for margin analysis); optional.
    v_in_min: Optional[float] = None
    v_in_max: Optional[float] = None


class SeriesType:
    """What the series element physically is. DC math always uses the
    resistance (DCR for ferrites/inductors); inductance is carried for
    documentation and AC awareness."""
    RESISTOR = "resistor"
    FERRITE_BEAD = "ferrite_bead"
    INDUCTOR = "inductor"
    FUSE = "fuse"
    CABLE = "cable"
    CONNECTOR = "connector"
    SWITCH = "switch"
    ALL = (RESISTOR, FERRITE_BEAD, INDUCTOR, FUSE, CABLE, CONNECTOR, SWITCH)
    LABELS = {RESISTOR: "R", FERRITE_BEAD: "FB", INDUCTOR: "L", FUSE: "F",
              CABLE: "CBL", CONNECTOR: "CON", SWITCH: "SW"}


@dataclass
class SeriesElement(Element):
    kind: str = ElementKind.SERIES
    name: str = "Series R"
    series_type: str = SeriesType.RESISTOR
    resistance_ohm: float = 0.010       # DCR for ferrite beads / inductors
    inductance_uh: float = 0.0          # informational (DC solver ignores it)
    rating: str = ""                    # free text, e.g. '600R@100MHz'
    # optional electrical checks (margin analysis flags breaches):
    v_in_min: Optional[float] = None    # allowed input-voltage window
    v_in_max: Optional[float] = None
    i_max: Optional[float] = None       # continuous current rating (A)
    p_max: Optional[float] = None       # dissipation rating (W)

    @property
    def resistance(self) -> float:
        return clamp(self.resistance_ohm, R_MIN, R_MAX)


@dataclass
class Block:
    """Visual/organizational grouping of elements (e.g. one IC with Icc + Iq loads)."""
    id: str = field(default_factory=new_id)
    name: str = "Block"
    description: str = ""
    color: str = "#7c5cff"
    collapsed: bool = False


@dataclass
class Note:
    """Hierarchical markdown note; may embed images and link to elements."""
    id: str = field(default_factory=new_id)
    parent_id: Optional[str] = None
    title: str = "New note"
    body_md: str = ""
    images: dict = field(default_factory=dict)     # filename -> base64 png/jpg
    linked_element_ids: list = field(default_factory=list)
    order: int = 0


ELEMENT_CLASSES = {
    ElementKind.SOURCE: Source,
    ElementKind.CONVERTER: Converter,
    ElementKind.LOAD: Load,
    ElementKind.SERIES: SeriesElement,
}


class PowerTree:
    """A single power tree: exactly one Source root plus child elements."""

    def __init__(self, name: str = "Power Tree", tree_id: Optional[str] = None):
        self.id = tree_id or new_id()
        self.name = name
        self.description = ""
        self.orientation = "TD"          # TD | LR | custom
        self.detail_default = ""         # '' = inherit app setting
        self.elements: dict[str, Element] = {}
        self.blocks: dict[str, Block] = {}

    # ---- structure queries -------------------------------------------------
    @property
    def source(self) -> Optional[Source]:
        for el in self.elements.values():
            if el.kind == ElementKind.SOURCE:
                return el
        return None

    def children_of(self, element_id: Optional[str]) -> list[Element]:
        kids = [e for e in self.elements.values() if e.parent_id == element_id]
        # series first, then grouped by block so block members sit adjacent
        kids.sort(key=lambda e: (e.kind != ElementKind.SERIES,
                                 e.block_id or "￿", e.name.lower(), e.id))
        return kids

    def descendants_of(self, element_id: str) -> list[Element]:
        out = []
        stack = [element_id]
        while stack:
            for child in self.children_of(stack.pop()):
                out.append(child)
                stack.append(child.id)
        return out

    def parent_of(self, element: Element) -> Optional[Element]:
        return self.elements.get(element.parent_id) if element.parent_id else None

    def block_members(self, block_id: str) -> list[Element]:
        return [e for e in self.elements.values() if e.block_id == block_id]

    # ---- mutations ---------------------------------------------------------
    def can_parent(self, parent: Optional[Element]) -> bool:
        """Loads are leaves; everything else may host children."""
        return parent is not None and parent.kind in (
            ElementKind.SOURCE, ElementKind.CONVERTER, ElementKind.SERIES)

    def add_element(self, element: Element, parent_id: Optional[str] = None) -> Element:
        if element.kind == ElementKind.SOURCE:
            if self.source is not None:
                raise ValueError("A power tree may contain only one source.")
            element.parent_id = None
        else:
            parent = self.elements.get(parent_id or "")
            if not self.can_parent(parent):
                raise ValueError(
                    f"Cannot attach a {element.kind} under "
                    f"{parent.kind if parent else 'nothing'} — pick a source, "
                    "converter or series element as the parent.")
            element.parent_id = parent.id
        self.elements[element.id] = element
        return element

    def remove_element(self, element_id: str) -> None:
        for d in self.descendants_of(element_id):
            self.elements.pop(d.id, None)
        self.elements.pop(element_id, None)

    def move_element(self, element_id: str, new_parent_id: str) -> None:
        el = self.elements[element_id]
        if el.kind == ElementKind.SOURCE:
            raise ValueError("The source is the root and cannot be moved.")
        if new_parent_id == element_id or any(
                d.id == new_parent_id for d in self.descendants_of(element_id)):
            raise ValueError("Cannot move an element under its own subtree.")
        parent = self.elements.get(new_parent_id)
        if not self.can_parent(parent):
            raise ValueError("New parent must be a source, converter or series element.")
        el.parent_id = new_parent_id

    def duplicate_subtree(self, element_id: str,
                          new_parent_id: Optional[str] = None) -> Element:
        """Deep-copy an element and its descendants (fresh ids); attaches to
        `new_parent_id` or the original's parent. Sources cannot be copied."""
        import copy as _copy
        root = self.elements[element_id]
        if root.kind == ElementKind.SOURCE:
            raise ValueError("A tree has exactly one source — duplicate its "
                             "children instead.")
        parent_id = new_parent_id or root.parent_id

        def clone(el: Element, parent: Optional[str]) -> Element:
            dup = _copy.deepcopy(el)
            dup.id = new_id()
            dup.parent_id = parent
            dup.x = dup.y = None
            self.elements[dup.id] = dup
            for child in [c for c in self.elements.values()
                          if c.parent_id == el.id and c.id != dup.id]:
                if child.id in originals:
                    clone(child, dup.id)
            return dup

        originals = {root.id} | {d.id for d in self.descendants_of(root.id)}
        dup_root = clone(root, parent_id)
        dup_root.name = f"{root.name} (copy)"
        return dup_root

    def add_block(self, name: str = "Block") -> Block:
        block = Block(name=name)
        self.blocks[block.id] = block
        return block

    def remove_block(self, block_id: str) -> None:
        for el in self.block_members(block_id):
            el.block_id = None
        self.blocks.pop(block_id, None)


class Project:
    """Top-level container: many power trees plus a hierarchical notes vault."""

    def __init__(self, name: str = "New Project"):
        self.name = name
        self.description = ""
        self.author = ""
        self.trees: list[PowerTree] = []
        self.notes: dict[str, Note] = {}
        self.scenarios: list[str] = []      # named operating states
        # design policy: flag rails loaded above this % of their limit
        # (industry practice ~80). 0 disables the check.
        self.derating_pct: float = 80.0
        self.file_path: Optional[str] = None

    def new_tree(self, name: Optional[str] = None) -> PowerTree:
        tree = PowerTree(name or f"Power Tree {len(self.trees) + 1}")
        self.trees.append(tree)
        return tree

    def tree_by_id(self, tree_id: str) -> Optional[PowerTree]:
        for t in self.trees:
            if t.id == tree_id:
                return t
        return None

    def remove_tree(self, tree_id: str) -> None:
        self.trees = [t for t in self.trees if t.id != tree_id]

    # ---- notes -------------------------------------------------------------
    def note_children(self, parent_id: Optional[str]) -> list[Note]:
        kids = [n for n in self.notes.values() if n.parent_id == parent_id]
        kids.sort(key=lambda n: (n.order, n.title.lower(), n.id))
        return kids

    def add_note(self, title: str = "New note", parent_id: Optional[str] = None) -> Note:
        note = Note(title=title, parent_id=parent_id,
                    order=len(self.note_children(parent_id)))
        self.notes[note.id] = note
        return note

    def remove_note(self, note_id: str) -> None:
        for child in self.note_children(note_id):
            self.remove_note(child.id)
        self.notes.pop(note_id, None)

    def notes_for_element(self, element_id: str) -> list[Note]:
        return [n for n in self.notes.values() if element_id in n.linked_element_ids]
