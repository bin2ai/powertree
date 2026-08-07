"""Pure-Python flowchart layout (no Qt dependency).

Tidy-tree layout with variable node sizes, TD / LR orientation, collapse
support and orthogonal (90-degree) edge routing. Guarantees no overlapping
nodes: each subtree is allotted its full extent along the breadth axis.

Coordinates are the CENTER of each node.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model.elements import PowerTree, Element, ElementKind

NODE_W = 200.0
NODE_H = 96.0
SRC_H = 104.0
SERIES_H = 72.0
H_GAP = 46.0      # gap along breadth axis
V_GAP = 78.0      # gap along depth axis
BLOCK_PAD = 18.0  # extra clearance for nodes that belong to a block


def node_size(el: Element) -> tuple:
    if el.kind == ElementKind.SOURCE:
        return NODE_W, SRC_H
    if el.kind == ElementKind.SERIES:
        return NODE_W * 0.88, SERIES_H
    return NODE_W, NODE_H


@dataclass
class LayoutResult:
    positions: dict = field(default_factory=dict)   # id -> (cx, cy)
    sizes: dict = field(default_factory=dict)       # id -> (w, h)
    edges: list = field(default_factory=list)       # (parent_id, child_id, [pts])
    visible: set = field(default_factory=set)
    hidden_counts: dict = field(default_factory=dict)  # id -> hidden descendants
    bounds: tuple = (0.0, 0.0, 0.0, 0.0)            # x, y, w, h


def compute_layout(tree: PowerTree, orientation: str = "TD",
                   respect_custom: bool = True) -> LayoutResult:
    """orientation: 'TD' (top-down), 'LR' (left-right) or 'custom'.

    In 'custom' mode nodes keep their stored (x, y) if present; nodes without a
    stored position fall back to an automatic TD layout so nothing stacks up.
    """
    out = LayoutResult()
    src = tree.source
    if src is None:
        return out

    # visible set honouring collapse
    def collect(el: Element):
        out.visible.add(el.id)
        out.sizes[el.id] = node_size(el)
        kids = tree.children_of(el.id)
        if el.collapsed:
            out.hidden_counts[el.id] = len(tree.descendants_of(el.id))
            return
        for c in kids:
            collect(c)

    collect(src)

    base = "LR" if orientation == "LR" else "TD"
    _tidy_layout(tree, src, base, out)

    if orientation == "custom" and respect_custom:
        for el_id in out.visible:
            el = tree.elements[el_id]
            if el.x is not None and el.y is not None:
                out.positions[el_id] = (el.x, el.y)

    _route_edges(tree, base if orientation != "custom" else "TD", out)
    _compute_bounds(out)
    return out


def _breadth_extent(el_id: str, tree: PowerTree, out: LayoutResult, horiz: bool,
                    cache: dict) -> float:
    """Total extent of a subtree along the breadth axis."""
    if el_id in cache:
        return cache[el_id]
    el = tree.elements[el_id]
    w, h = out.sizes[el_id]
    own = (h if horiz else w) + (BLOCK_PAD * 2 if el.block_id else 0.0)
    kids = [c for c in tree.children_of(el_id) if c.id in out.visible] \
        if not el.collapsed else []
    if not kids:
        cache[el_id] = own + H_GAP
        return cache[el_id]
    kid_total = sum(_breadth_extent(c.id, tree, out, horiz, cache) for c in kids)
    cache[el_id] = max(own + H_GAP, kid_total)
    return cache[el_id]


def _tidy_layout(tree: PowerTree, src: Element, base: str, out: LayoutResult) -> None:
    horiz = (base == "LR")
    cache: dict = {}

    # depth positions: cumulative max node depth-size per level
    levels: dict[int, float] = {}

    def scan_depth(el: Element, depth: int):
        w, h = out.sizes[el.id]
        d = w if horiz else h
        levels[depth] = max(levels.get(depth, 0.0), d)
        if not el.collapsed:
            for c in tree.children_of(el.id):
                if c.id in out.visible:
                    scan_depth(c, depth + 1)

    scan_depth(src, 0)
    depth_center: dict[int, float] = {}
    cursor = 0.0
    for depth in sorted(levels):
        depth_center[depth] = cursor + levels[depth] / 2
        cursor += levels[depth] + V_GAP

    def place(el: Element, depth: int, breadth_lo: float):
        extent = _breadth_extent(el.id, tree, out, horiz, cache)
        center_b = breadth_lo + extent / 2
        center_d = depth_center[depth]
        out.positions[el.id] = (center_d, center_b) if horiz else (center_b, center_d)
        if not el.collapsed:
            b = breadth_lo
            kids = [c for c in tree.children_of(el.id) if c.id in out.visible]
            for c in kids:
                ce = _breadth_extent(c.id, tree, out, horiz, cache)
                place(c, depth + 1, b)
                b += ce

    place(src, 0, 0.0)


def _route_edges(tree: PowerTree, base: str, out: LayoutResult) -> None:
    """Orthogonal parent->child edges: exit, midway bus, entry (all 90 deg)."""
    horiz = (base == "LR")
    for el_id in out.visible:
        el = tree.elements[el_id]
        if el.parent_id and el.parent_id in out.visible:
            px, py = out.positions[el.parent_id]
            pw, ph = out.sizes[el.parent_id]
            cx, cy = out.positions[el_id]
            cw, ch = out.sizes[el_id]
            if horiz:
                start = (px + pw / 2, py)
                end = (cx - cw / 2, cy)
                mid = (start[0] + end[0]) / 2
                pts = [start, (mid, start[1]), (mid, end[1]), end]
            else:
                start = (px, py + ph / 2)
                end = (cx, cy - ch / 2)
                mid = (start[1] + end[1]) / 2
                pts = [start, (start[0], mid), (end[0], mid), end]
            # drop degenerate middle points for straight runs
            clean = [pts[0]]
            for p in pts[1:]:
                if abs(p[0] - clean[-1][0]) > 0.5 or abs(p[1] - clean[-1][1]) > 0.5:
                    clean.append(p)
            if len(clean) < 2:
                clean = [start, end]
            out.edges.append((el.parent_id, el_id, clean))


def _compute_bounds(out: LayoutResult) -> None:
    if not out.positions:
        return
    xs, ys, xe, ye = [], [], [], []
    for el_id, (cx, cy) in out.positions.items():
        w, h = out.sizes[el_id]
        xs.append(cx - w / 2)
        ys.append(cy - h / 2)
        xe.append(cx + w / 2)
        ye.append(cy + h / 2)
    x0, y0 = min(xs), min(ys)
    out.bounds = (x0, y0, max(xe) - x0, max(ye) - y0)


def block_rects(tree: PowerTree, out: LayoutResult, pad: float = 14.0) -> dict:
    """Bounding rectangle per block around its visible members."""
    rects = {}
    for bid in tree.blocks:
        members = [e for e in tree.block_members(bid) if e.id in out.visible]
        if not members:
            continue
        xs, ys, xe, ye = [], [], [], []
        for el in members:
            cx, cy = out.positions[el.id]
            w, h = out.sizes[el.id]
            xs.append(cx - w / 2)
            ys.append(cy - h / 2)
            xe.append(cx + w / 2)
            ye.append(cy + h / 2)
        rects[bid] = (min(xs) - pad, min(ys) - pad - 20,
                      (max(xe) - min(xs)) + pad * 2, (max(ye) - min(ys)) + pad * 2 + 20)
    return rects
