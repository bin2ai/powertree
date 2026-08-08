"""Pure-Python flowchart layout (no Qt dependency).

Tidy-tree layout with variable node sizes, TD / LR orientation, collapse
support and orthogonal (90-degree) edge routing. Guarantees no overlapping
nodes: each subtree is allotted its full extent along the breadth axis.

Render graph: the layout operates on RENDER NODES — normally one per visible
element, but a block whose `collapsed` flag is set becomes a single summary
node ("blk:<id>"): its members are hidden, external children re-attach under
the summary node, and every distinct feeding rail becomes a labeled INPUT
pin (extra feeds beyond the primary parent are routed as cross-edges);
rails leaving the block become labeled OUTPUT pins.

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

BLOCK_PREFIX = "blk:"
GRID_PREFIX = "grid:"
BLOCK_NODE_H = 122.0
PIN_STUB = 10.0    # visual pin stub length (edges land on the pin)
GRID_GAP = 14.0    # spacing between cards inside a rail grid
GRID_PAD = 12.0    # grid container padding
GRID_HEADER = 20.0  # rail label strip at the top of a grid container

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


def block_node_size(block, n_in: int, n_out: int,
                    extra_lines: int = 0) -> tuple:
    """Auto size (grows with pin count and custom info lines), overridable
    per block from the Block Designer."""
    w = max(240.0, 62.0 * max(n_in, n_out, 1) + 40.0)
    h = BLOCK_NODE_H + 13.0 * extra_lines
    if block is not None:
        if block.width:
            w = max(160.0, float(block.width))
        if block.height:
            h = max(90.0, float(block.height))
    return w, h


@dataclass
class BlockNodeInfo:
    """A collapsed block rendered as one node."""
    block_id: str
    member_ids: list = field(default_factory=list)
    # ordered pins: inputs = [(net_label, feeding_render_id)],
    #               outputs = [(net_label, member_element_id)]
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    # designer-resolved geometry:
    #   pin_geom[(dir, key)] = (side, index_on_side, count_on_side)
    #   pins_by_side[side] = [(dir, net)] in display order
    pin_geom: dict = field(default_factory=dict)
    pins_by_side: dict = field(default_factory=dict)


def _resolve_pin_geometry(block, info: "BlockNodeInfo", horiz: bool) -> None:
    """Assign each pin a card side (designer override or orientation default)
    and an index among the pins sharing that side."""
    default_in = "left" if horiz else "top"
    default_out = "right" if horiz else "bottom"
    by_side: dict = {}
    ordered = []
    for direction, pins, default in (("in", info.inputs, default_in),
                                     ("out", info.outputs, default_out)):
        for net, key in pins:
            side = (block.pin_side or {}).get(net, default)
            if side not in ("top", "bottom", "left", "right"):
                side = default
            ordered.append((direction, net, key, side))
    for direction, net, key, side in ordered:
        by_side.setdefault(side, []).append((direction, net, key))
    info.pin_geom = {}
    info.pins_by_side = {}
    for side, pins in by_side.items():
        info.pins_by_side[side] = [(d, n) for d, n, _k in pins]
        for i, (direction, net, key) in enumerate(pins):
            info.pin_geom[(direction, key)] = (side, i, len(pins))


def _apply_pin_order(block, pins: list, direction: str) -> list:
    """Reorder (net, key) pins by the designer's saved order; unknown nets
    keep their sorted position at the end."""
    wanted = (block.pin_order or {}).get(direction) or []
    rank = {net: i for i, net in enumerate(wanted)}
    return sorted(pins, key=lambda t: (rank.get(t[0], len(rank) + 1), t[0]))


@dataclass
class GridGroupInfo:
    """Many leaf loads on one rail wrapped into a compact grid (kills the
    endless-ribbon problem on wide fan-outs)."""
    parent_rid: str
    member_ids: list = field(default_factory=list)
    net: str = ""
    cols: int = 1
    rows: int = 1


@dataclass
class LayoutResult:
    positions: dict = field(default_factory=dict)   # rid -> (cx, cy)
    sizes: dict = field(default_factory=dict)       # rid -> (w, h)
    edges: list = field(default_factory=list)       # (src_rid, dst_rid, [pts], label)
    junctions: list = field(default_factory=list)   # (x, y) branch-node dots
    visible: set = field(default_factory=set)       # visible ELEMENT ids (rendered as cards)
    render_nodes: set = field(default_factory=set)  # all render node ids
    block_nodes: dict = field(default_factory=dict)  # rid -> BlockNodeInfo
    grid_groups: dict = field(default_factory=dict)  # rid -> GridGroupInfo
    hidden_counts: dict = field(default_factory=dict)  # rid -> hidden descendants
    bounds: tuple = (0.0, 0.0, 0.0, 0.0)            # x, y, w, h
    details: dict = field(default_factory=dict)     # rid -> resolved detail

    def pin_point(self, rid: str, direction: str, key: str) -> tuple:
        """Coordinates where a pin meets the card edge. direction: 'in'|'out';
        key: feeding render id (in) or member element id (out). Honors the
        Block Designer's per-pin side assignment."""
        cx, cy = self.positions[rid]
        w, h = self.sizes[rid]
        info = self.block_nodes[rid]
        side, i, n = info.pin_geom.get(
            (direction, key), ("top" if direction == "in" else "bottom", 0, 1))
        frac = (i + 1) / (n + 1)
        if side == "top":
            return (cx - w / 2 + w * frac, cy - h / 2)
        if side == "bottom":
            return (cx - w / 2 + w * frac, cy + h / 2)
        if side == "left":
            return (cx - w / 2, cy - h / 2 + h * frac)
        return (cx + w / 2, cy - h / 2 + h * frac)


def _net_of(tree: PowerTree, el: Element) -> str:
    """Named output rail of an element (walking up when unnamed)."""
    cur = el
    while cur is not None:
        if cur.kind in (ElementKind.SOURCE, ElementKind.CONVERTER,
                        ElementKind.SERIES) and cur.signal_name:
            return cur.signal_name
        cur = tree.parent_of(cur)
    return el.name


def compute_layout(tree: PowerTree, orientation: str = "TD",
                   respect_custom: bool = True,
                   detail_default: str = "standard",
                   grid_threshold: int = 7) -> LayoutResult:
    """orientation: 'TD' (top-down), 'LR' (left-right) or 'custom'."""
    from ..settings import resolve_detail
    out = LayoutResult()
    src = tree.source
    if src is None:
        return out

    # ---- 1. visible elements (element-level collapse chains) --------------
    visible_elements: set = set()

    def collect(el: Element):
        visible_elements.add(el.id)
        if el.collapsed:
            return
        for c in tree.children_of(el.id):
            collect(c)

    collect(src)

    # ---- 2. collapsed blocks -> render-node mapping -----------------------
    member_block: dict = {}
    for bid, block in tree.blocks.items():
        if not block.collapsed:
            continue
        members = [m for m in tree.block_members(bid)
                   if m.id in visible_elements and m.id != src.id]
        if not members:
            continue
        rid = BLOCK_PREFIX + bid
        info = BlockNodeInfo(block_id=bid,
                             member_ids=[m.id for m in members])
        out.block_nodes[rid] = info
        for m in members:
            member_block[m.id] = rid

    def render_id(el_id: str) -> str:
        return member_block.get(el_id, el_id)

    # ---- 3. render graph: child_map + cross edges -------------------------
    child_map: dict = {}
    parent_of: dict = {}
    cross: list = []            # (parent_rid, child_rid) extra feeds

    def link(pr: str, cr: str):
        if pr == cr:
            return
        if cr in parent_of:
            if parent_of[cr] != pr and (pr, cr) not in cross \
                    and cr not in child_map.get(pr, []):
                cross.append((pr, cr))
            return
        parent_of[cr] = pr
        child_map.setdefault(pr, []).append(cr)

    def walk(el: Element):
        for c in tree.children_of(el.id):
            if c.id not in visible_elements:
                continue
            link(render_id(el.id), render_id(c.id))
            walk(c)

    root_rid = render_id(src.id)
    parent_of[root_rid] = None
    walk(src)
    out.render_nodes = {root_rid} | set(parent_of)

    # ---- 4. block pin lists ----------------------------------------------
    for rid, info in out.block_nodes.items():
        if rid not in out.render_nodes:
            continue
        member_set = set(info.member_ids)
        seen_in: dict = {}
        seen_out: dict = {}
        for mid in info.member_ids:
            m = tree.elements[mid]
            parent = tree.parent_of(m)
            if parent is not None and parent.id not in member_set and \
                    parent.id in visible_elements:
                pr = render_id(parent.id)
                net = _net_of(tree, parent)
                seen_in.setdefault(pr, net)
            for c in tree.children_of(mid):
                if c.id in member_set or c.id not in visible_elements:
                    continue
                net = m.signal_name or _net_of(tree, m)
                seen_out.setdefault(mid, net)
        block = tree.blocks[info.block_id]
        info.inputs = _apply_pin_order(
            block, sorted(((net, pr) for pr, net in seen_in.items()),
                          key=lambda t: t[0]), "in")
        info.outputs = _apply_pin_order(
            block, sorted(((net, mid) for mid, net in seen_out.items()),
                          key=lambda t: t[0]), "out")
        _resolve_pin_geometry(block, info, orientation == "LR")

    # ---- 5. sizes / details / hidden counts -------------------------------
    for rid in out.render_nodes:
        if rid.startswith(BLOCK_PREFIX):
            info = out.block_nodes[rid]
            block = tree.blocks[info.block_id]
            extra = len([ln for ln in (block.info_text or "").splitlines()
                         if ln.strip()])
            out.sizes[rid] = block_node_size(block, len(info.inputs),
                                             len(info.outputs), extra)
            hidden = set(info.member_ids)
            for mid in info.member_ids:
                hidden |= {d.id for d in tree.descendants_of(mid)
                           if render_id(d.id) == rid or
                           d.id not in visible_elements}
            out.hidden_counts[rid] = len(hidden)
        else:
            el = tree.elements[rid]
            detail = resolve_detail(detail_default, tree, el)
            out.details[rid] = detail
            out.sizes[rid] = node_size(el, detail)
            out.visible.add(rid)
            if el.collapsed:
                out.hidden_counts[rid] = len(tree.descendants_of(rid))

    # ---- 5b. companion tucking must be known before grids -----------------
    _early_attached: set = set()
    for pr, kids in child_map.items():
        for rid in kids:
            if rid.startswith(BLOCK_PREFIX) or rid.startswith(GRID_PREFIX):
                continue
            el = tree.elements[rid]
            if el.kind == ElementKind.CONVERTER and el.block_id and \
                    el.block_id in tree.blocks and \
                    not tree.blocks[el.block_id].collapsed:
                for s in kids:
                    if s != rid and not s.startswith(BLOCK_PREFIX) and \
                            not s.startswith(GRID_PREFIX) and \
                            tree.elements[s].kind == ElementKind.LOAD and \
                            tree.elements[s].block_id == el.block_id:
                        _early_attached.add(s)

    # ---- 5c. leaf-grid wrapping: many loads on one rail -> compact grid ---
    import math as _math
    if grid_threshold and grid_threshold > 0 and orientation != "custom":
        for pr in list(child_map):
            kids = child_map[pr]
            gridable = [c for c in kids
                        if not c.startswith(BLOCK_PREFIX)
                        and tree.elements[c].kind == ElementKind.LOAD
                        and c not in child_map           # leaf loads only
                        and c not in _early_attached]    # keep Iq companions
            if len(gridable) < grid_threshold:
                continue
            # group by block so cluster outlines stay contiguous in the grid
            gridable.sort(key=lambda c: (tree.elements[c].block_id or "￿",
                                         tree.elements[c].name.lower()))
            grid_rid = GRID_PREFIX + pr
            cell_w = max(out.sizes[c][0] for c in gridable)
            cell_h = max(out.sizes[c][1] for c in gridable)
            n = len(gridable)
            cols = max(2, int(_math.ceil(_math.sqrt(n * cell_h / cell_w))))
            cols = min(cols, n)
            rows = int(_math.ceil(n / cols))
            gw = cols * cell_w + (cols - 1) * GRID_GAP + 2 * GRID_PAD
            gh = rows * cell_h + (rows - 1) * GRID_GAP + 2 * GRID_PAD \
                + GRID_HEADER
            parent_el = tree.elements.get(pr)
            net = _net_of(tree, parent_el) if parent_el is not None else ""
            out.grid_groups[grid_rid] = GridGroupInfo(
                parent_rid=pr, member_ids=list(gridable), net=net,
                cols=cols, rows=rows)
            out.sizes[grid_rid] = (gw, gh)
            child_map[pr] = [c for c in kids if c not in gridable]
            child_map[pr].append(grid_rid)
            parent_of[grid_rid] = pr
            out.render_nodes.add(grid_rid)
            for c in gridable:
                out.render_nodes.discard(c)   # positioned inside the grid
                parent_of.pop(c, None)

    # ---- 6. companion tucking (converter + same-block Iq load) ------------
    attached: dict = {}
    attached_ids: set = set()
    for pr, kids in child_map.items():
        for rid in kids:
            if rid.startswith(BLOCK_PREFIX) or rid.startswith(GRID_PREFIX):
                continue
            el = tree.elements[rid]
            if el.kind == ElementKind.CONVERTER and el.block_id and \
                    tree.blocks.get(el.block_id, None) is not None and \
                    not tree.blocks[el.block_id].collapsed:
                mates = [s for s in kids
                         if s != rid and not s.startswith(BLOCK_PREFIX)
                         and not s.startswith(GRID_PREFIX)
                         and tree.elements[s].kind == ElementKind.LOAD
                         and tree.elements[s].block_id == el.block_id
                         and s not in attached_ids]
                if mates:
                    attached[rid] = mates
                    attached_ids |= set(mates)

    # ---- 7. tidy layout over the render graph -----------------------------
    base = "LR" if orientation == "LR" else "TD"
    horiz = (base == "LR")
    cache: dict = {}

    def breadth_of(rid: str) -> float:
        w, h = out.sizes[rid]
        return h if horiz else w

    def kids_of(rid: str) -> list:
        return [c for c in child_map.get(rid, []) if c not in attached_ids]

    def in_block(rid: str) -> bool:
        if rid.startswith(BLOCK_PREFIX) or rid.startswith(GRID_PREFIX):
            return False
        return tree.elements[rid].block_id is not None

    def extent(rid: str) -> float:
        if rid in cache:
            return cache[rid]
        own = breadth_of(rid) + (BLOCK_PAD * 2 if in_block(rid) else 0.0)
        for mate in attached.get(rid, []):
            own += ATTACH_GAP + breadth_of(mate)
        kid_total = sum(extent(c) for c in kids_of(rid))
        cache[rid] = max(own + H_GAP, kid_total)
        return cache[rid]

    levels: dict = {}

    def scan_depth(rid: str, depth: int):
        w, h = out.sizes[rid]
        d = w if horiz else h
        levels[depth] = max(levels.get(depth, 0.0), d)
        for mate in attached.get(rid, []):
            mw, mh = out.sizes[mate]
            levels[depth] = max(levels[depth], mw if horiz else mh)
        for c in kids_of(rid):
            scan_depth(c, depth + 1)

    scan_depth(root_rid, 0)
    depth_center: dict = {}
    cursor = 0.0
    for depth in sorted(levels):
        depth_center[depth] = cursor + levels[depth] / 2
        cursor += levels[depth] + V_GAP

    def set_pos(rid: str, depth: int, center_b: float):
        center_d = depth_center[depth]
        out.positions[rid] = ((center_d, center_b) if horiz
                              else (center_b, center_d))

    def place(rid: str, depth: int, breadth_lo: float):
        ext = extent(rid)
        mates = attached.get(rid, [])
        row = breadth_of(rid) + sum(ATTACH_GAP + breadth_of(m) for m in mates)
        row_lo = breadth_lo + ext / 2 - row / 2
        set_pos(rid, depth, row_lo + breadth_of(rid) / 2)
        b = row_lo + breadth_of(rid)
        for mate in mates:
            b += ATTACH_GAP
            set_pos(mate, depth, b + breadth_of(mate) / 2)
            b += breadth_of(mate)
        cb = breadth_lo
        for c in kids_of(rid):
            ce = extent(c)
            place(c, depth + 1, cb)
            cb += ce

    place(root_rid, 0, 0.0)

    # position grid members inside their containers (row-major)
    for grid_rid, ginfo in out.grid_groups.items():
        gw, gh = out.sizes[grid_rid]
        gx, gy = out.positions[grid_rid]
        cell_w = max(out.sizes[c][0] for c in ginfo.member_ids)
        cell_h = max(out.sizes[c][1] for c in ginfo.member_ids)
        x0 = gx - gw / 2 + GRID_PAD
        y0 = gy - gh / 2 + GRID_HEADER + GRID_PAD
        for i, mid in enumerate(ginfo.member_ids):
            row, col = divmod(i, ginfo.cols)
            mw, mh = out.sizes[mid]
            cx = x0 + col * (cell_w + GRID_GAP) + cell_w / 2
            cy = y0 + row * (cell_h + GRID_GAP) + cell_h / 2
            out.positions[mid] = (cx, cy)
            out.render_nodes.add(mid)     # drawn as normal cards

    # ---- 8. custom positions ---------------------------------------------
    if orientation == "custom" and respect_custom:
        for rid in out.render_nodes:
            if rid.startswith(BLOCK_PREFIX):
                block = tree.blocks[out.block_nodes[rid].block_id]
                if block.x is not None and block.y is not None:
                    out.positions[rid] = (block.x, block.y)
            else:
                el = tree.elements[rid]
                if el.x is not None and el.y is not None:
                    out.positions[rid] = (el.x, el.y)

    # ---- 9. routing --------------------------------------------------------
    _route_edges(tree, base, out, child_map, cross, member_block, horiz)
    _compute_bounds(out)
    return out


def _edge_endpoints(tree: PowerTree, out: LayoutResult, pr: str, cr: str,
                    member_block: dict, horiz: bool):
    """(start, end, label) — pin-aware for block nodes."""
    px, py = out.positions[pr]
    pw, ph = out.sizes[pr]
    cx, cy = out.positions[cr]
    cw, ch = out.sizes[cr]
    label = ""
    # start: parent exit
    if pr.startswith(BLOCK_PREFIX):
        info = out.block_nodes[pr]
        # which member feeds cr? cr's tree-parent (or an ancestor) is a member
        member_id = None
        if cr.startswith(GRID_PREFIX):
            ginfo = out.grid_groups[cr]
            probe = tree.elements.get(ginfo.member_ids[0]) \
                if ginfo.member_ids else None
        elif cr.startswith(BLOCK_PREFIX):
            probe = None
        else:
            probe = tree.elements.get(cr)
        if probe is not None:
            p = tree.parent_of(probe)
            while p is not None:
                if p.id in info.member_ids:
                    member_id = p.id
                    break
                p = tree.parent_of(p)
        else:                      # blk -> blk: find member feeding any child member
            cinfo = out.block_nodes[cr]
            for mid in cinfo.member_ids:
                p = tree.parent_of(tree.elements[mid])
                while p is not None:
                    if p.id in info.member_ids:
                        member_id = p.id
                        break
                    p = tree.parent_of(p)
                if member_id:
                    break
        for net, mid in info.outputs:
            if mid == member_id:
                label = net
                break
        start = out.pin_point(pr, "out", member_id)
    else:
        el = tree.elements[pr]
        if el.kind == ElementKind.CONVERTER:
            label = el.signal_name or ""
        elif el.kind == ElementKind.SOURCE:
            label = el.signal_name or ""
        elif el.kind == ElementKind.SERIES:
            label = el.signal_name or ""
        start = (px + pw / 2, py) if horiz else (px, py + ph / 2)
    # end: child entry
    if cr.startswith(BLOCK_PREFIX):
        cinfo = out.block_nodes[cr]
        for net, feeder in cinfo.inputs:
            if feeder == pr:
                if not label:
                    label = net
                break
        end = out.pin_point(cr, "in", pr)
    else:
        end = (cx - cw / 2, cy) if horiz else (cx, cy - ch / 2)
    return start, end, label


def _route_edges(tree: PowerTree, base: str, out: LayoutResult,
                 child_map: dict, cross: list, member_block: dict,
                 horiz: bool) -> None:
    """Bus-style orthogonal routing with junction dots; edges land on block
    pins when an endpoint is a collapsed-block node."""

    def route(start, end):
        if horiz:
            bus = (start[0] + end[0]) / 2
            pts = [start, (bus, start[1]), (bus, end[1]), end]
        else:
            bus = (start[1] + end[1]) / 2
            pts = [start, (start[0], bus), (end[0], bus), end]
        clean = [pts[0]]
        for p in pts[1:]:
            if abs(p[0] - clean[-1][0]) > 0.5 or abs(p[1] - clean[-1][1]) > 0.5:
                clean.append(p)
        return clean if len(clean) >= 2 else [start, end]

    for pr, kids in child_map.items():
        groups: dict = {}
        for cr in kids:
            start, end, label = _edge_endpoints(tree, out, pr, cr,
                                                member_block, horiz)
            groups.setdefault(start, []).append((cr, end, label))
        for start, entries in groups.items():
            for cr, end, label in entries:
                out.edges.append((pr, cr, route(start, end), label))
            if len(entries) > 1:
                if horiz:
                    bus = (start[0] + min(e[1][0] for e in entries)) / 2
                    trunk = (bus, start[1])
                    branch = [(bus, e[1][1]) for e in entries]
                else:
                    bus = (start[1] + min(e[1][1] for e in entries)) / 2
                    trunk = (start[0], bus)
                    branch = [(e[1][0], bus) for e in entries]
                out.junctions.append(trunk)
                for bp in branch:
                    if abs(bp[0] - trunk[0]) > 0.5 or \
                            abs(bp[1] - trunk[1]) > 0.5:
                        out.junctions.append(bp)

    for pr, cr in cross:
        start, end, label = _edge_endpoints(tree, out, pr, cr,
                                            member_block, horiz)
        out.edges.append((pr, cr, route(start, end), label))


def _compute_bounds(out: LayoutResult) -> None:
    if not out.positions:
        return
    xs, ys, xe, ye = [], [], [], []
    for rid, (cx, cy) in out.positions.items():
        w, h = out.sizes[rid]
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
    contiguous cluster of members (collapsed blocks render as summary nodes
    instead and are skipped here)."""
    result: dict = {}
    for bid, block in tree.blocks.items():
        if block.collapsed:
            continue
        members = [e for e in tree.block_members(bid)
                   if e.id in out.visible and e.id in out.positions]
        if not members:
            continue
        rects = {e.id: _member_rect(out, e.id) for e in members}
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


def block_pins(tree: PowerTree, block_id: str) -> tuple:
    """(input_nets, output_nets) the block's summary node exposes —
    used by the Block Designer to list pins without a full layout pass."""
    src = tree.source
    members = [m for m in tree.block_members(block_id)
               if src is None or m.id != src.id]
    member_set = {m.id for m in members}
    ins, outs = [], []
    for m in members:
        parent = tree.parent_of(m)
        if parent is not None and parent.id not in member_set:
            net = _net_of(tree, parent)
            if net not in ins:
                ins.append(net)
        if any(c.id not in member_set for c in tree.children_of(m.id)):
            net = m.signal_name or _net_of(tree, m)
            if net not in outs:
                outs.append(net)
    return sorted(ins), sorted(outs)
