"""Interactive flowchart canvas (QGraphicsScene/View) + headless HD renderer.

Visual language:
  - Source     amber   (rounded card, double border)
  - Converter  blue    (card with efficiency + pass-through output rail)
  - Load       green   (card)
  - Series     slate   (slim card)
  - Blocks     tinted containers drawn behind their member nodes
  - Edges      orthogonal 90-degree segments with arrowheads, labelled by rail

Every card shows its live power figures; warning/error badges appear from the
margin analysis. Layout modes: top-down, left-right, custom (drag to place).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QImage,
    QFontMetricsF, QLinearGradient,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsView,
    QStyleOptionGraphicsItem, QGraphicsPathItem,
)

from ..model.elements import PowerTree, Element, ElementKind, LoadType, LimitType
from ..model.calc import TreeResults, block_power, fmt_si
from . import layout as L


_PALETTES = {
    "dark": dict(
        bg="#101319", grid="#161b24", card="#1a2030", card_edge="#2c3650",
        text="#e8ecf5", text_dim="#98a3b8", edge="#5b6b8c",
        edge_text="#8fa0c0", select="#7c5cff", highlight="#22d3ee",
        error="#f43f5e", warn="#fbbf24",
        source="#f59e0b", converter="#3b82f6", load="#10b981",
        series="#94a3b8", legend_bg=(16, 19, 25, 235)),
    # printable: white background, ink-friendly colors
    "print": dict(
        bg="#ffffff", grid="#f0f2f7", card="#f7f8fc", card_edge="#aab4c8",
        text="#16202e", text_dim="#5a6778", edge="#5a6778",
        edge_text="#5a6778", select="#6d28d9", highlight="#0e7490",
        error="#dc2626", warn="#b45309",
        source="#b45309", converter="#1d4ed8", load="#047857",
        series="#475569", legend_bg=(255, 255, 255, 235)),
}


class Theme:
    """Mutable style singleton: Theme.set_style('dark'|'print') swaps every
    color in place, so all drawing code just reads Theme.<attr>."""
    style = "dark"
    kind_labels = {
        ElementKind.SOURCE: "SOURCE",
        ElementKind.CONVERTER: "CONVERTER",
        ElementKind.LOAD: "LOAD",
        ElementKind.SERIES: "SERIES",
    }

    @classmethod
    def set_style(cls, name: str):
        p = _PALETTES.get(name, _PALETTES["dark"])
        cls.style = name if name in _PALETTES else "dark"
        cls.bg = QColor(p["bg"])
        cls.grid = QColor(p["grid"])
        cls.card = QColor(p["card"])
        cls.card_edge = QColor(p["card_edge"])
        cls.text = QColor(p["text"])
        cls.text_dim = QColor(p["text_dim"])
        cls.edge = QColor(p["edge"])
        cls.edge_text = QColor(p["edge_text"])
        cls.select = QColor(p["select"])
        cls.highlight = QColor(p["highlight"])
        cls.error = QColor(p["error"])
        cls.warn = QColor(p["warn"])
        cls.kinds = {
            ElementKind.SOURCE: QColor(p["source"]),
            ElementKind.CONVERTER: QColor(p["converter"]),
            ElementKind.LOAD: QColor(p["load"]),
            ElementKind.SERIES: QColor(p["series"]),
        }
        cls.legend_bg = QColor(*p["legend_bg"])


Theme.set_style("dark")


def heat_color(fraction: float) -> QColor:
    """0.0 (cold, blue) .. 1.0 (hot, red) with a yellow midpoint."""
    f = max(0.0, min(1.0, fraction))
    if f < 0.5:
        t = f / 0.5          # blue -> amber
        return QColor(int(59 + t * (245 - 59)), int(130 + t * (158 - 130)),
                      int(246 + t * (11 - 246)))
    t = (f - 0.5) / 0.5      # amber -> red
    return QColor(int(245 + t * (239 - 245)), int(158 + t * (68 - 158)),
                  int(11 + t * (68 - 11)))


def _kind_color(kind: str) -> QColor:
    return Theme.kinds.get(kind, Theme.text_dim)


def element_lines(el: Element, results: TreeResults,
                  detail: str = "standard") -> list:
    """The stat lines shown on a card, scaled to the display-detail level."""
    typ = results.get(el.id, "typ")
    mx = results.get(el.id, "max")
    lines = []
    if detail == "minimal":
        if el.kind == ElementKind.SOURCE:
            lines.append(f"P {fmt_si(typ.p_out, 'W')} · I {fmt_si(typ.i_out, 'A')}")
        elif el.kind == ElementKind.CONVERTER:
            lines.append(f"{fmt_si(typ.v_out, 'V')} · P {fmt_si(typ.p_out, 'W')}")
        elif el.kind == ElementKind.LOAD:
            lines.append(f"P {fmt_si(typ.p_in, 'W')} · {fmt_si(typ.v_in, 'V')}")
        else:
            lines.append(f"{fmt_si(el.resistance_ohm, 'Ω')} · "
                         f"loss {fmt_si(typ.p_loss, 'W')}")
        return lines
    if el.kind == ElementKind.SOURCE:
        lines.append(f"V: {el.v_min:g} / {el.v_typ:g} / {el.v_max:g} V")
        lines.append(f"P out: {fmt_si(typ.p_out, 'W')}  ·  I: {fmt_si(typ.i_out, 'A')}")
        lines.append(f"max corner: {fmt_si(mx.p_out, 'W')} / {fmt_si(mx.i_out, 'A')}")
        if el.limit_type != LimitType.NONE and el.limit_value > 0:
            unit = "A" if el.limit_type == LimitType.CURRENT else "W"
            used = mx.i_out if el.limit_type == LimitType.CURRENT else mx.p_out
            pct = used / el.limit_value * 100 if el.limit_value else 0
            lines.append(f"limit {el.limit_value:g} {unit} · {pct:.0f} % used")
    elif el.kind == ElementKind.CONVERTER:
        if el.eff_points:
            eff_txt = f"η {el.efficiency_at(typ.i_out) * 100:.1f} %*"
        else:
            eff_txt = f"η {el.efficiency_pct:g} %"
        lines.append(f"{fmt_si(typ.v_in, 'V')} → {fmt_si(typ.v_out, 'V')}"
                     f"  ·  {eff_txt}")
        lines.append(f"P in: {fmt_si(typ.p_in, 'W')} → out: {fmt_si(typ.p_out, 'W')}")
        lines.append(f"I out: {fmt_si(typ.i_out, 'A')} · loss {fmt_si(typ.p_loss, 'W')}")
        if el.limit_type != LimitType.NONE and el.limit_value > 0:
            unit = "A" if el.limit_type == LimitType.CURRENT else "W"
            used = mx.i_out if el.limit_type == LimitType.CURRENT else mx.p_out
            pct = used / el.limit_value * 100 if el.limit_value else 0
            lines.append(f"limit {el.limit_value:g} {unit} · {pct:.0f} % used")
    elif el.kind == ElementKind.LOAD:
        unit = "A" if el.load_type == LoadType.CURRENT else "W"
        peak = f" / pk {el.value_max:g} {unit}" if el.value_max is not None else ""
        lines.append(f"{el.load_type} load: {el.value_typ:g} {unit}{peak}")
        lines.append(f"V in: {fmt_si(typ.v_in, 'V')} · P: {fmt_si(typ.p_in, 'W')}")
        if el.v_in_min is not None or el.v_in_max is not None:
            lo = f"{el.v_in_min:g}" if el.v_in_min is not None else "—"
            hi = f"{el.v_in_max:g}" if el.v_in_max is not None else "—"
            lines.append(f"allowed: {lo} … {hi} V")
    elif el.kind == ElementKind.SERIES:
        from ..model.elements import SeriesType
        tag = SeriesType.LABELS.get(getattr(el, "series_type", ""), "R")
        extra = ""
        if getattr(el, "inductance_uh", 0.0):
            extra = f" · {el.inductance_uh:g} µH"
        lines.append(f"{tag}: {fmt_si(el.resistance_ohm, 'Ω')}{extra}"
                     f" · I {fmt_si(typ.i_in, 'A')}")
        lines.append(f"drop {fmt_si(typ.v_in - typ.v_out, 'V')}"
                     f" · loss {fmt_si(typ.p_loss, 'W')}")
        if getattr(el, "rating", ""):
            lines.append(f"rating: {el.rating}")

    if detail == "exhaustive":
        mn = results.get(el.id, "min")
        lines.append(f"min corner: {fmt_si(mn.p_in, 'W')} · "
                     f"{fmt_si(mn.v_in, 'V')} · {fmt_si(mn.i_in, 'A')}")
        if el.kind == ElementKind.SERIES:
            checks = []
            if el.i_max is not None:
                checks.append(f"Imax {el.i_max:g} A")
            if el.p_max is not None:
                checks.append(f"Pmax {el.p_max:g} W")
            if el.v_in_min is not None or el.v_in_max is not None:
                lo = f"{el.v_in_min:g}" if el.v_in_min is not None else "—"
                hi = f"{el.v_in_max:g}" if el.v_in_max is not None else "—"
                checks.append(f"Vin {lo}…{hi} V")
            if checks:
                lines.append(" · ".join(checks))
        if el.part_number:
            lines.append(f"PN: {el.part_number}")
        if el.pins:
            lines.append(f"pins: {el.pins}")
        if el.scenario_overrides and any(el.scenario_overrides.values()):
            states = [s for s, v in el.scenario_overrides.items() if v]
            lines.append("◈ states: " + ", ".join(states))
    return lines


class NodeItem(QGraphicsObject):
    HEADER = 24.0

    def __init__(self, el: Element, tree: PowerTree, results: TreeResults,
                 size: tuple, hidden_count: int, canvas: "PowerCanvas",
                 detail: str = "standard", heat: float | None = None):
        super().__init__()
        self.el = el
        self.tree = tree
        self.canvas = canvas
        self.w, self.h = size
        self.hidden_count = hidden_count
        self.lines = element_lines(el, results, detail)
        self.severity = results.worst_severity(el.id)
        self.has_children = bool(tree.children_of(el.id))
        self.search_hit = False
        self.heat = heat            # None = kind color; 0..1 = cold..hot tint
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        el = self.el
        meta = [f"<b>{el.name}</b> <i>({Theme.kind_labels.get(el.kind, '?')})</i>"]
        for label, val in (("Signal", el.signal_name), ("RefDes", el.refdes),
                           ("Part", el.part_number), ("Pins", el.pins),
                           ("Notes", el.description)):
            if val:
                meta.append(f"{label}: {val}")
        meta += self.lines
        return "<br>".join(meta)

    def boundingRect(self) -> QRectF:
        return QRectF(-3, -3, self.w + 6, self.h + 6)

    def chip_rect(self) -> QRectF:
        return QRectF(self.w - 30, self.h - 20, 26, 16)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.w, self.h)
        color = heat_color(self.heat) if self.heat is not None \
            else _kind_color(self.el.kind)

        # card body
        grad = QLinearGradient(0, 0, 0, self.h)
        grad.setColorAt(0.0, Theme.card.lighter(112))
        grad.setColorAt(1.0, Theme.card)
        painter.setBrush(QBrush(grad))
        edge_pen = QPen(Theme.card_edge, 1.4)
        if self.isSelected():
            edge_pen = QPen(Theme.select, 2.4)
        elif self.search_hit:
            edge_pen = QPen(Theme.highlight, 2.4)
        painter.setPen(edge_pen)
        painter.drawRoundedRect(rect, 9, 9)
        if self.el.kind == ElementKind.SOURCE:   # double border marks the root
            painter.setPen(QPen(color.darker(120), 1.0))
            painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 7, 7)

        # header band
        head = QRectF(0, 0, self.w, self.HEADER)
        path = QPainterPath()
        path.addRoundedRect(rect, 9, 9)
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(head, QColor(color.red(), color.green(), color.blue(), 46))
        painter.fillRect(QRectF(0, 0, 4, self.h), color)
        painter.restore()

        f = QFont("Segoe UI", 8)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QPen(color))
        painter.drawText(head.adjusted(10, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft,
                         Theme.kind_labels.get(self.el.kind, "?"))
        ref = " · ".join(x for x in (self.el.refdes, self.el.signal_name) if x)
        if ref:
            painter.setPen(QPen(Theme.text_dim))
            f2 = QFont("Segoe UI", 7)
            painter.setFont(f2)
            painter.drawText(head.adjusted(10, 0, -8, 0),
                             Qt.AlignVCenter | Qt.AlignRight, ref)

        # name
        f3 = QFont("Segoe UI", 9)
        f3.setBold(True)
        painter.setFont(f3)
        painter.setPen(QPen(Theme.text))
        fm = QFontMetricsF(f3)
        name = fm.elidedText(self.el.name, Qt.ElideRight, self.w - 20)
        painter.drawText(QRectF(10, self.HEADER, self.w - 20, 16),
                         Qt.AlignVCenter | Qt.AlignLeft, name)

        # stat lines
        f4 = QFont("Consolas", 8)
        painter.setFont(f4)
        fm4 = QFontMetricsF(f4)
        y = self.HEADER + 17
        for i, line in enumerate(self.lines):
            painter.setPen(QPen(Theme.text if i < 2 else Theme.text_dim))
            avail = self.w - 18
            if self.has_children and y + 13 > self.h - 22:
                avail = self.w - 44          # keep clear of the collapse chip
            painter.drawText(QRectF(10, y, avail, 13), Qt.AlignVCenter,
                             fm4.elidedText(line, Qt.ElideRight, avail))
            y += 13.5
            if y > self.h - 6:
                break

        # warning badge
        if self.severity in ("error", "warn"):
            c = Theme.error if self.severity == "error" else Theme.warn
            painter.setBrush(QBrush(c))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(self.w - 12, 12), 6.5, 6.5)
            painter.setPen(QPen(Theme.bg, 1.6))
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.drawText(QRectF(self.w - 19, 5, 14, 14), Qt.AlignCenter, "!")

        # collapse chip
        if self.has_children:
            chip = self.chip_rect()
            painter.setBrush(QBrush(Theme.card_edge))
            painter.setPen(QPen(Theme.text_dim, 0.8))
            painter.drawRoundedRect(chip, 4, 4)
            painter.setPen(QPen(Theme.text))
            painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
            label = f"+{self.hidden_count}" if self.el.collapsed else "−"
            painter.drawText(chip, Qt.AlignCenter, label)

    def mousePressEvent(self, event):
        if self.has_children and self.chip_rect().contains(event.pos()):
            self.canvas.collapseToggled.emit(self.el.id)
            event.accept()
            return
        super().mousePressEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.canvas.node_dragged(self)
        return super().itemChange(change, value)


class BlockItem(QGraphicsPathItem):
    def __init__(self, block, rect: tuple, power_text: str,
                 continued: bool = False):
        super().__init__()
        self.continued = continued
        x, y, w, h = rect
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), 12, 12)
        self.setPath(path)
        base = QColor(block.color)
        fill = QColor(base.red(), base.green(), base.blue(), 22)
        self.setBrush(QBrush(fill))
        pen = QPen(QColor(base.red(), base.green(), base.blue(), 140), 1.2,
                   Qt.DashLine)
        self.setPen(pen)
        self.setZValue(-10)
        self.block = block
        self.label_rect = QRectF(x + 8, y + 3, w - 16, 16)
        self.power_text = power_text

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.setPen(QPen(QColor(self.block.color)))
        label = self.block.name + (" ⋯" if self.continued else "")
        painter.drawText(self.label_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         label)
        painter.setPen(QPen(Theme.text_dim))
        painter.setFont(QFont("Consolas", 8))
        painter.drawText(self.label_rect, Qt.AlignRight | Qt.AlignVCenter,
                         self.power_text)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, pts: list, label: str = "", horiz: bool = False):
        super().__init__()
        self.horiz = horiz
        self.label = label
        self.set_points(pts)
        self.setPen(QPen(Theme.edge, 1.6))
        self.setZValue(-5)

    def set_points(self, pts: list):
        self.pts = pts
        path = QPainterPath(QPointF(*pts[0]))
        for p in pts[1:]:
            path.lineTo(QPointF(*p))
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self.pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())
        # arrowhead at the end
        end = QPointF(*self.pts[-1])
        prev = QPointF(*self.pts[-2]) if len(self.pts) > 1 else end
        dx, dy = end.x() - prev.x(), end.y() - prev.y()
        n = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        ux, uy = dx / n, dy / n
        size = 7.0
        left = QPointF(end.x() - ux * size - uy * size * 0.55,
                       end.y() - uy * size + ux * size * 0.55)
        right = QPointF(end.x() - ux * size + uy * size * 0.55,
                        end.y() - uy * size - ux * size * 0.55)
        painter.setBrush(QBrush(Theme.edge))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(QPolygonF([end, left, right]))
        if self.label:
            painter.setFont(QFont("Consolas", 7))
            painter.setPen(QPen(Theme.edge_text))
            mid = QPointF(*self.pts[len(self.pts) // 2])
            painter.drawText(QRectF(mid.x() + 4, mid.y() - 14, 120, 12),
                             Qt.AlignLeft | Qt.AlignVCenter, self.label)


class PowerCanvas(QGraphicsView):
    """Interactive flowchart view for one power tree."""

    elementSelected = Signal(str)
    collapseToggled = Signal(str)
    nodeMoved = Signal()
    contextRequested = Signal(str, object)   # element id ('' = canvas), QPoint

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(Theme.bg))
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.tree: PowerTree | None = None
        self.results: TreeResults | None = None
        self.nodes: dict[str, NodeItem] = {}
        self.edge_items: list = []
        self.legend_visible = True
        self.detail_default = "standard"    # app-level display detail
        self.heat_mode = False              # tint cards by power draw
        self._rebuilding = False
        self.scene_.selectionChanged.connect(self._on_selection)

    # ------------------------------------------------------------------ build
    def rebuild(self, tree: PowerTree | None, results: TreeResults | None,
                keep_view: bool = True):
        self._rebuilding = True
        old_transform = self.transform()
        old_center = self.mapToScene(self.viewport().rect().center())
        selected = {i for i, n in self.nodes.items() if n.isSelected()}
        self.scene_.clear()
        self.nodes.clear()
        self.edge_items.clear()
        self.tree, self.results = tree, results
        if tree is None or results is None or tree.source is None:
            self._rebuilding = False
            return

        lay = L.compute_layout(tree, tree.orientation,
                               detail_default=self.detail_default)
        horiz = tree.orientation == "LR"
        movable = tree.orientation == "custom"

        heat_map = _heat_fractions(tree, results, lay.visible) \
            if self.heat_mode else {}

        # blocks behind everything — one outline per contiguous cluster
        for bid, clusters in L.block_clusters(tree, lay).items():
            block = tree.blocks[bid]
            p = block_power(tree, results, bid, "typ")
            multi = len(clusters) > 1
            for rect, _members, primary in clusters:
                power = fmt_si(p, "W") if primary else ""
                item = BlockItem(block, rect, power,
                                 continued=multi and not primary)
                self.scene_.addItem(item)

        # edges
        edge_map = {}
        for pid, cid, pts in lay.edges:
            parent = tree.elements[pid]
            label = ""
            if parent.kind == ElementKind.CONVERTER:
                label = parent.signal_name or fmt_si(parent.vout_typ, "V")
            elif parent.kind == ElementKind.SOURCE:
                label = parent.signal_name or ""
            item = EdgeItem(pts, label, horiz)
            self.scene_.addItem(item)
            edge_map[(pid, cid)] = item
        self._edge_map = edge_map

        # junction dots on branched rails (auto layouts only — in custom
        # mode dragging would leave them stale)
        if not movable:
            for jx, jy in lay.junctions:
                dot = self.scene_.addEllipse(jx - 3.2, jy - 3.2, 6.4, 6.4,
                                             QPen(Qt.NoPen), QBrush(Theme.edge))
                dot.setZValue(-4)

        # nodes
        for el_id in lay.visible:
            el = tree.elements[el_id]
            size = lay.sizes[el_id]
            node = NodeItem(el, tree, results, size,
                            lay.hidden_counts.get(el_id, 0), self,
                            detail=lay.details.get(el_id, "standard"),
                            heat=heat_map.get(el_id))
            cx, cy = lay.positions[el_id]
            node.setPos(cx - size[0] / 2, cy - size[1] / 2)
            node.setFlag(QGraphicsItem.ItemIsMovable, movable)
            self.scene_.addItem(node)
            self.nodes[el_id] = node
            if el_id in selected:
                node.setSelected(True)

        margin = 120
        b = lay.bounds
        self.scene_.setSceneRect(b[0] - margin, b[1] - margin,
                                 b[2] + margin * 2, b[3] + margin * 2)
        if keep_view and not old_transform.isIdentity():
            self.setTransform(old_transform)
            self.centerOn(old_center)
        else:
            self.fit()
        self._rebuilding = False

    # ------------------------------------------------------------ interaction
    def _on_selection(self):
        if self._rebuilding:
            return
        sel = self.scene_.selectedItems()
        for item in sel:
            if isinstance(item, NodeItem):
                self.elementSelected.emit(item.el.id)
                return
        self.elementSelected.emit("")

    def node_dragged(self, node: NodeItem):
        if self._rebuilding or self.tree is None:
            return
        center = node.pos() + QPointF(node.w / 2, node.h / 2)
        node.el.x, node.el.y = center.x(), center.y()
        self._reroute_edges()
        self.nodeMoved.emit()

    def _reroute_edges(self):
        horiz = self.tree.orientation == "LR"
        for (pid, cid), edge in getattr(self, "_edge_map", {}).items():
            pn, cn = self.nodes.get(pid), self.nodes.get(cid)
            if not pn or not cn:
                continue
            px = pn.pos().x() + pn.w / 2
            py = pn.pos().y() + pn.h / 2
            cx = cn.pos().x() + cn.w / 2
            cy = cn.pos().y() + cn.h / 2
            if horiz:
                start = (pn.pos().x() + pn.w, py)
                end = (cn.pos().x(), cy)
                mid = (start[0] + end[0]) / 2
                pts = [start, (mid, start[1]), (mid, end[1]), end]
            else:
                start = (px, pn.pos().y() + pn.h)
                end = (cx, cn.pos().y())
                mid = (start[1] + end[1]) / 2
                pts = [start, (start[0], mid), (end[0], mid), end]
            edge.set_points(pts)
        self.scene_.update()

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        while item is not None and not isinstance(item, NodeItem):
            item = item.parentItem()
        el_id = item.el.id if isinstance(item, NodeItem) else ""
        if el_id:
            self.scene_.clearSelection()
            if el_id in self.nodes:
                self.nodes[el_id].setSelected(True)
        self.contextRequested.emit(el_id, event.globalPos())
        event.accept()

    def fit(self):
        if self.scene_.items():
            self.fitInView(self.scene_.itemsBoundingRect().adjusted(-40, -40, 40, 40),
                           Qt.KeepAspectRatio)

    def highlight(self, element_ids: set):
        first = None
        for el_id, node in self.nodes.items():
            node.search_hit = el_id in element_ids
            if node.search_hit and first is None:
                first = node
            node.update()
        if first is not None:
            self.centerOn(first)

    def select_element(self, element_id: str):
        self.scene_.clearSelection()
        node = self.nodes.get(element_id)
        if node:
            node.setSelected(True)
            self.centerOn(node)

    # ---------------------------------------------------------------- legend
    def drawForeground(self, painter: QPainter, rect: QRectF):
        super().drawForeground(painter, rect)
        if not self.legend_visible or not self.nodes:
            return
        painter.save()
        painter.resetTransform()
        if self.heat_mode:
            entries = [(heat_color(0.05), "cold (low power)"),
                       (heat_color(0.5), "medium"),
                       (heat_color(1.0), "hot (highest power)")]
        else:
            entries = [(Theme.kinds[k], Theme.kind_labels[k]) for k in
                       (ElementKind.SOURCE, ElementKind.CONVERTER,
                        ElementKind.LOAD, ElementKind.SERIES)]
        extras = [(Theme.error, "limit / range violation"),
                  (Theme.warn, "margin < 10 %")]
        w, line_h = 190, 18
        h = (len(entries) + len(extras)) * line_h + 34
        x, y = 12, self.viewport().height() - h - 12
        painter.setBrush(QBrush(Theme.legend_bg))
        painter.setPen(QPen(Theme.card_edge, 1))
        painter.drawRoundedRect(QRectF(x, y, w, h), 8, 8)
        painter.setPen(QPen(Theme.text))
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.drawText(QRectF(x + 10, y + 6, w - 20, 14), Qt.AlignLeft, "LEGEND")
        painter.setFont(QFont("Segoe UI", 8))
        yy = y + 26
        for color, label in entries:
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(x + 10, yy + 3, 14, 10), 3, 3)
            painter.setPen(QPen(Theme.text_dim))
            painter.drawText(QRectF(x + 32, yy, w - 40, line_h),
                             Qt.AlignVCenter, label.title())
            yy += line_h
        for color, label in extras:
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(x + 12, yy + 3, 10, 10))
            painter.setPen(QPen(Theme.text_dim))
            painter.drawText(QRectF(x + 32, yy, w - 40, line_h),
                             Qt.AlignVCenter, label)
            yy += line_h
        painter.restore()


# ---------------------------------------------------------------------------
# headless HD rendering (used by image / PDF / notes exports)
# ---------------------------------------------------------------------------

def render_tree_image(tree: PowerTree, results: TreeResults,
                      orientation: str | None = None, scale: float = 3.0,
                      with_legend: bool = True, style: str | None = None,
                      detail_default: str = "standard",
                      heat: bool = False) -> QImage:
    """Render a power tree to a high-resolution QImage (no window needed).
    style: None = current Theme; 'dark' | 'print' force a palette."""
    prev_style = Theme.style
    if style and style != prev_style:
        Theme.set_style(style)
    try:
        return _render_tree_image(tree, results, orientation, scale,
                                  with_legend, detail_default, heat)
    finally:
        if style and style != prev_style:
            Theme.set_style(prev_style)


def _render_tree_image(tree, results, orientation, scale, with_legend,
                       detail_default, heat) -> QImage:
    scene = QGraphicsScene()
    lay = L.compute_layout(tree, orientation or tree.orientation,
                           detail_default=detail_default)
    canvas_stub = _StubCanvas()
    heat_map = _heat_fractions(tree, results, lay.visible) if heat else {}
    for bid, clusters in L.block_clusters(tree, lay).items():
        block = tree.blocks[bid]
        p = block_power(tree, results, bid, "typ")
        multi = len(clusters) > 1
        for rect, _members, primary in clusters:
            power = fmt_si(p, "W") if primary else ""
            scene.addItem(BlockItem(block, rect, power,
                                    continued=multi and not primary))
    horiz = (orientation or tree.orientation) == "LR"
    for pid, cid, pts in lay.edges:
        parent = tree.elements[pid]
        label = ""
        if parent.kind == ElementKind.CONVERTER:
            label = parent.signal_name or fmt_si(parent.vout_typ, "V")
        elif parent.kind == ElementKind.SOURCE:
            label = parent.signal_name or ""
        scene.addItem(EdgeItem(pts, label, horiz))
    for jx, jy in lay.junctions:
        dot = scene.addEllipse(jx - 3.2, jy - 3.2, 6.4, 6.4,
                               QPen(Qt.NoPen), QBrush(Theme.edge))
        dot.setZValue(-4)
    for el_id in lay.visible:
        el = tree.elements[el_id]
        size = lay.sizes[el_id]
        node = NodeItem(el, tree, results, size,
                        lay.hidden_counts.get(el_id, 0), canvas_stub,
                        detail=lay.details.get(el_id, "standard"),
                        heat=heat_map.get(el_id))
        cx, cy = lay.positions[el_id]
        node.setPos(cx - size[0] / 2, cy - size[1] / 2)
        scene.addItem(node)

    pad = 50.0
    legend_h = 120.0 if with_legend else 0.0
    src_rect = scene.itemsBoundingRect().adjusted(-pad, -pad - 34, pad, pad + legend_h)
    img = QImage(int(src_rect.width() * scale),
                 int(src_rect.height() * scale), QImage.Format_ARGB32)
    img.fill(Theme.bg)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    scene.render(painter, QRectF(0, 0, img.width(), img.height()), src_rect)

    # title + legend drawn straight onto the image
    painter.setFont(QFont("Segoe UI", int(10 * scale), QFont.Bold))
    painter.setPen(QPen(Theme.text))
    painter.drawText(QRectF(14 * scale, 8 * scale, img.width() - 28 * scale,
                            20 * scale), Qt.AlignLeft | Qt.AlignVCenter, tree.name)
    if with_legend:
        _draw_image_legend(painter, img, scale)
    painter.end()
    return img


def _heat_fractions(tree: PowerTree, results: TreeResults,
                    visible: set) -> dict:
    """Element -> 0..1 hot/cold fraction of typ input power (sqrt-scaled so
    mid-size loads stay distinguishable; source excluded — it is the total)."""
    powers = {el_id: results.get(el_id, "typ").p_in for el_id in visible
              if tree.elements[el_id].kind != ElementKind.SOURCE}
    pmax = max(powers.values(), default=0.0)
    if pmax <= 0:
        return {}
    return {el_id: (p / pmax) ** 0.4 for el_id, p in powers.items()}


class _StubCanvas:
    """Signal sink for headless NodeItems."""
    class _Sig:
        def emit(self, *a):
            pass
    collapseToggled = _Sig()

    def node_dragged(self, node):
        pass


def _draw_image_legend(painter: QPainter, img: QImage, scale: float):
    entries = [(Theme.kinds[k], Theme.kind_labels[k].title()) for k in
               (ElementKind.SOURCE, ElementKind.CONVERTER,
                ElementKind.LOAD, ElementKind.SERIES)]
    entries += [(Theme.error, "Violation"), (Theme.warn, "Low margin")]
    x = 14 * scale
    y = img.height() - 30 * scale
    painter.setFont(QFont("Segoe UI", int(8 * scale)))
    for color, label in entries:
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(x, y, 14 * scale, 10 * scale),
                                3 * scale, 3 * scale)
        painter.setPen(QPen(Theme.text_dim))
        tw = QFontMetricsF(painter.font()).horizontalAdvance(label)
        painter.drawText(QRectF(x + 18 * scale, y - 2 * scale, tw + 8 * scale,
                                14 * scale), Qt.AlignVCenter, label)
        x += 18 * scale + tw + 20 * scale
