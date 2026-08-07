"""Pure-Python flowchart layout (no Qt dependency).

Tidy-tree layout with variable node sizes, TD / LR orientation, collapse
support and orthogonal (90-degree) edge routing. Guarantees no overlapping
nodes: each subtree is allotted its full extent along the breadth axis.

Block-aware refinements:
  - a leaf load that shares a block with a sibling converter (the
    "regulator = converter + its own Iq" pattern) is tucked directly beside
    that converter instead of being pushed to the edge of the row;
  - block outlines are drawn per contiguous CLUSTER of members, so a block
    whose members live on different rails never sprawls across the canvas.

Coordinates are the CENTER of each node.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model.elements import PowerTree, Element, ElementKind

NODE_W = 200.0
H_GAP = 46.0      # gap along breadth axis
V_GAP = 78.0      # gap along depth axis
BLOCK_PAD = 18.0  # extra clearance for nodes that belong to a block
ATTACH_GAP = 18.0  # gap between a converter and its tucked companion loads
CLUSTER_DIST = 90.0  # members closer than this merge into one block cluster

# card heights per display-detail level
_HEIGHTS = {
    "minimal": {"node": 62.0, "src": 70.0, "series": 52.0},
    "standard": {"node": 96.0, "src": 104.0, "series": 72.0},
    "exhaustive": {"node": 138.0, "src": 146.0, "series": 106.0},
}


def node_size(el: Element, detail: str = "standard") -> tuple:
    h = _HEIGHTS.get(detail, _HEIGHTS["standard"])
    if el.kind == ElementKind.SOURCE:
        return NODE_W, h["src"]
    if el.kind == ElementKind.SERIES:
        return NODE_W * 0.88, h["series"]
    return NODE_W, h["node"]


@dataclass
class LayoutResult:
    positions: dict = field(default_factory=dict)   # id -> (cx, cy)
    sizes: dict = field(default_factory=dict)       # id -> (w, h)
    edges: list = field(default_factory=list)       # (parent_id, child_id, [pts])
    junctions: list = field(default_factory=list)   # (x, y) branch-node dots
    visible: set = field(default_factory=set)
    hidden_counts: dict = field(default_factory=dict)  # id -> hidden descendants
    bounds: tuple = (0.0, 0.0, 0.0, 0.0)            # x, y, w, h
    details: dict = field(default_factory=dict)     # id -> resolved detail


def _companion_map(tree: PowerTree, visible: set) -> dict:
    """conv_id -> [leaf loads sharing the converter's block AND parent]."""
    attached: dict[str, list] = {}
    for el in tree.elements.values():
        if el.id not in visible or el.parent_id is None:
            continue
        siblings = tree.children_of(el.parent_id)
        if el.kind == ElementKind.CONVERTER and el.block_id:
            mates = [s for s in siblings
                     if s.id != el.id and s.id in visible
                     and s.kind == ElementKind.LOAD
                     and s.block_id == el.block_id]
            if mates:
                attached[el.id] = mates
    return attached


def compute_layout(tree: PowerTree, orientation: str = "TD",
                   respect_custom: bool = True,
                   detail_default: str = "standard") -> LayoutResult:
    """orientation: 'TD' (top-down), 'LR' (left-right) or 'custom'.

    In 'custom' mode nodes keep their stored (x, y) if present; nodes without
    a stored position fall back to an automatic TD layout so nothing stacks.
    detail_default cascades app -> tree -> element (see settings.resolve_detail).
    """
    from ..settings import resolve_detail
    out = LayoutResult()
    src = tree.source
    if src is None:
        return out

    # visible set honouring collapse
    def collect(el: Element):
        out.visible.add(el.id)
        detail = resolve_detail(detail_default, tree, el)
        out.details[el.id] = detail
        out.sizes[el.id] = node_size(el, detail)
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


def _tidy_layout(tree: PowerTree, src: Element, base: str,
                 out: LayoutResult) -> None:
    horiz = (base == "LR")
    attached = _companion_map(tree, out.visible)
    attached_ids = {m.id for mates in attached.values() for m in mates}
    cache: dict = {}

    def breadth_of(el_id: str) -> float:
        w, h = out.sizes[el_id]
        return h if horiz else w

    def kids_of(el: Element) -> list:
        if el.collapsed:
            return []
        return [c for c in tree.children_of(el.id)
                if c.id in out.visible and c.id not in attached_ids]

    def extent(el_id: str) -> float:
        if el_id in cache:
            return cache[el_id]
        el = tree.elements[el_id]
        own = breadth_of(el_id) + (BLOCK_PAD * 2 if el.block_id else 0.0)
        for mate in attached.get(el_id, []):
            own += ATTACH_GAP + breadth_of(mate.id)
        kids = kids_of(el)
        kid_total = sum(extent(c.id) for c in kids)
        cache[el_id] = max(own + H_GAP, kid_total)
        return cache[el_id]

    # depth positions: cumulative max node depth-size per level
    levels: dict[int, float] = {}

    def scan_depth(el: Element, depth: int):
        w, h = out.sizes[el.id]
        d = w if horiz else h
        levels[depth] = max(levels.get(depth, 0.0), d)
        for mate in attached.get(el.id, []):
            mw, mh = out.sizes[mate.id]
            levels[depth] = max(levels[depth], mw if horiz else mh)
        for c in kids_of(el):
            scan_depth(c, depth + 1)

    scan_depth(src, 0)
    depth_center: dict[int, float] = {}
    cursor = 0.0
    for depth in sorted(levels):
        depth_center[depth] = cursor + levels[depth] / 2
        cursor += levels[depth] + V_GAP

    def set_pos(el_id: str, depth: int, center_b: float):
        center_d = depth_center[depth]
        out.positions[el_id] = ((center_d, center_b) if horiz
                                else (center_b, center_d))

    def place(el: Element, depth: int, breadth_lo: float):
        ext = extent(el.id)
        mates = attached.get(el.id, [])
        row = breadth_of(el.id) + sum(ATTACH_GAP + breadth_of(m.id)
                                      for m in mates)
        row_lo = breadth_lo + ext / 2 - row / 2
        set_pos(el.id, depth, row_lo + breadth_of(el.id) / 2)
        b = row_lo + breadth_of(el.id)
        for mate in mates:
            b += ATTACH_GAP
            set_pos(mate.id, depth, b + breadth_of(mate.id) / 2)
            b += breadth_of(mate.id)
        cb = breadth_lo
        for c in kids_of(el):
            ce = extent(c.id)
            place(c, depth + 1, cb)
            cb += ce

    place(src, 0, 0.0)


def _route_edges(tree: PowerTree, base: str, out: LayoutResult) -> None:
    """Bus-style orthogonal routing: the parent's feed drops to a mid-level
    bus, fans out horizontally, then enters each child — with junction dots
    at every T so branched rails read like a schematic."""
    horiz = (base == "LR")
    children_by_parent: dict = {}
    for el_id in out.visible:
        el = tree.elements[el_id]
        if el.parent_id and el.parent_id in out.visible:
            children_by_parent.setdefault(el.parent_id, []).append(el_id)

    for pid, kids in children_by_parent.items():
        px, py = out.positions[pid]
        pw, ph = out.sizes[pid]
        # shared bus level: midway between parent exit and nearest child entry
        if horiz:
            start_d = px + pw / 2
            entries = [out.positions[c][0] - out.sizes[c][0] / 2 for c in kids]
            bus = (start_d + min(entries)) / 2
        else:
            start_d = py + ph / 2
            entries = [out.positions[c][1] - out.sizes[c][1] / 2 for c in kids]
            bus = (start_d + min(entries)) / 2
        branch_points = []
        for c in kids:
            cx, cy = out.positions[c]
            cw, ch = out.sizes[c]
            if horiz:
                start = (start_d, py)
                end = (cx - cw / 2, cy)
                pts = [start, (bus, py), (bus, cy), end]
                branch_points.append((bus, cy))
            else:
                start = (px, start_d)
                end = (cx, cy - ch / 2)
                pts = [start, (px, bus), (cx, bus), end]
                branch_points.append((cx, bus))
            clean = [pts[0]]
            for p in pts[1:]:
                if abs(p[0] - clean[-1][0]) > 0.5 or \
                        abs(p[1] - clean[-1][1]) > 0.5:
                    clean.append(p)
            if len(clean) < 2:
                clean = [start, end]
            out.edges.append((pid, c, clean))
        # junction dots only where the rail actually branches
        if len(kids) > 1:
            trunk = (bus, py) if horiz else (px, bus)
            out.junctions.append(trunk)
            for bp in branch_points:
                if abs(bp[0] - trunk[0]) > 0.5 or abs(bp[1] - trunk[1]) > 0.5:
                    out.junctions.append(bp)


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


def _member_rect(out: LayoutResult, el_id: str) -> tuple:
    cx, cy = out.positions[el_id]
    w, h = out.sizes[el_id]
    return (cx - w / 2, cy - h / 2, w, h)


def _rects_close(a: tuple, b: tuple, dist: float) -> bool:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    gap_x = max(bx0 - (ax0 + aw), ax0 - (bx0 + bw), 0.0)
    gap_y = max(by0 - (ay0 + ah), ay0 - (by0 + bh), 0.0)
    return gap_x <= dist and gap_y <= dist


def block_clusters(tree: PowerTree, out: LayoutResult, pad: float = 14.0) -> dict:
    """block_id -> [(rect, member_ids, is_primary)] — one outline per
    contiguous cluster of members, primary = largest cluster (labelled with
    the aggregate power)."""
    result: dict = {}
    for bid in tree.blocks:
        members = [e for e in tree.block_members(bid) if e.id in out.visible]
        if not members:
            continue
        rects = {e.id: _member_rect(out, e.id) for e in members}
        # union-find by proximity
        parent = {e.id: e.id for e in members}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        ids = list(rects)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if _rects_close(rects[a], rects[b], CLUSTER_DIST):
                    parent[find(a)] = find(b)
        clusters: dict = {}
        for el_id in ids:
            clusters.setdefault(find(el_id), []).append(el_id)
        entries = []
        for group in clusters.values():
            xs = [rects[i][0] for i in group]
            ys = [rects[i][1] for i in group]
            xe = [rects[i][0] + rects[i][2] for i in group]
            ye = [rects[i][1] + rects[i][3] for i in group]
            rect = (min(xs) - pad, min(ys) - pad - 20,
                    (max(xe) - min(xs)) + pad * 2,
                    (max(ye) - min(ys)) + pad * 2 + 20)
            entries.append([rect, group, False])
        entries.sort(key=lambda e: -len(e[1]))
        if entries:
            entries[0][2] = True
        result[bid] = [tuple(e) for e in entries]
    return result


def block_rects(tree: PowerTree, out: LayoutResult, pad: float = 14.0) -> dict:
    """Backwards-compatible single-rect view (primary cluster only)."""
    return {bid: entries[0][0]
            for bid, entries in block_clusters(tree, out, pad).items()}
