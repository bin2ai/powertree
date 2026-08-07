"""Hierarchical list view of a power tree with live electrical columns."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from ..model.elements import PowerTree, ElementKind
from ..model.calc import TreeResults, fmt_si

KIND_COLORS = {
    ElementKind.SOURCE: QColor("#f59e0b"),
    ElementKind.CONVERTER: QColor("#3b82f6"),
    ElementKind.LOAD: QColor("#10b981"),
    ElementKind.SERIES: QColor("#94a3b8"),
}
HEADERS = ["Element", "Type", "RefDes", "Signal", "Block",
           "V in", "I in", "P in", "% of tree", "P out", "Loss",
           "P in (max)", "Status"]


class TreeListView(QTreeWidget):
    elementSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(HEADERS))
        self.setHeaderLabels(HEADERS)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.itemSelectionChanged.connect(self._on_select)
        self._items: dict[str, QTreeWidgetItem] = {}
        for i, w in enumerate([190, 72, 60, 100, 110, 64, 70, 70, 62, 70,
                               66, 78, 110]):
            self.setColumnWidth(i, w)

    def rebuild(self, tree: PowerTree | None, results: TreeResults | None):
        expanded = {el_id for el_id, it in self._items.items() if it.isExpanded()}
        selected = {el_id for el_id, it in self._items.items() if it.isSelected()}
        prev_known = set(self._items)
        first_build = not self._items
        self.blockSignals(True)
        self.clear()
        self._items.clear()
        if tree is None or results is None or tree.source is None:
            self.blockSignals(False)
            return

        def status(el_id):
            warns = results.warnings_for(el_id)
            if not warns:
                return "OK", None
            worst = results.worst_severity(el_id)
            color = QColor("#f43f5e") if worst == "error" else QColor("#fbbf24")
            label = "VIOLATION" if worst == "error" else "LOW MARGIN"
            return f"{label} ({len(warns)})", color

        p_src = results.get(tree.source.id, "typ").p_out \
            if tree.source else 0.0

        def add(el, parent_item):
            typ = results.get(el.id, "typ")
            mx = results.get(el.id, "max")
            block = tree.blocks.get(el.block_id) if el.block_id else None
            stat, stat_color = status(el.id)
            is_load = el.kind == ElementKind.LOAD
            pct = f"{typ.p_in / p_src * 100:.1f} %" if p_src > 1e-12 else "—"
            row = [el.name, el.kind, el.refdes, el.signal_name,
                   block.name if block else "",
                   fmt_si(typ.v_in, "V"), fmt_si(typ.i_in, "A"),
                   fmt_si(typ.p_in, "W"), pct,
                   "—" if is_load else fmt_si(typ.p_out, "W"),
                   fmt_si(typ.p_loss, "W") if typ.p_loss > 1e-12 else "—",
                   fmt_si(mx.p_in, "W"), stat]
            item = QTreeWidgetItem(parent_item, row)
            item.setData(0, Qt.UserRole, el.id)
            item.setForeground(1, QBrush(KIND_COLORS.get(el.kind,
                                                         QColor("#98a3b8"))))
            f = item.font(0)
            f.setBold(el.kind in (ElementKind.SOURCE, ElementKind.CONVERTER))
            item.setFont(0, f)
            mono = QFont("Consolas", 8)
            for col in range(5, 12):
                item.setFont(col, mono)
                item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
            if stat_color:
                item.setForeground(12, QBrush(stat_color))
                fb = item.font(12)
                fb.setBold(True)
                item.setFont(12, fb)
            self._items[el.id] = item
            for child in tree.children_of(el.id):
                add(child, item)
            return item

        root = add(tree.source, self)
        if first_build:
            self.expandAll()
        else:
            # keep the user's expand state; new rows default to expanded
            for el_id, it in self._items.items():
                it.setExpanded(el_id in expanded or el_id not in prev_known)
            root.setExpanded(True)
        for el_id in selected:
            if el_id in self._items:
                self._items[el_id].setSelected(True)
        self.blockSignals(False)

    def _on_select(self):
        items = self.selectedItems()
        if items:
            self.elementSelected.emit(items[0].data(0, Qt.UserRole))

    def select_element(self, element_id: str):
        self.blockSignals(True)
        self.clearSelection()
        item = self._items.get(element_id)
        if item:
            item.setSelected(True)
            self.scrollToItem(item)
        self.blockSignals(False)

    def apply_filter(self, matching_ids: set | None):
        """Hide rows not in the match set (ancestors of matches stay visible)."""
        if matching_ids is None:
            for item in self._items.values():
                item.setHidden(False)
            return
        keep: set = set()
        for el_id, item in self._items.items():
            if el_id in matching_ids:
                keep.add(el_id)
                parent = item.parent()
                while parent is not None:
                    keep.add(parent.data(0, Qt.UserRole))
                    parent = parent.parent()
        for el_id, item in self._items.items():
            item.setHidden(el_id not in keep)
