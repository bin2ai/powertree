"""Block Designer — customize a block's summary-node appearance:
per-pin side (top/bottom/left/right) and order, card size, custom info
lines, stats visibility and color. All settings persist in the project."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTreeWidget,
    QTreeWidgetItem, QComboBox, QPushButton, QDoubleSpinBox, QPlainTextEdit,
    QCheckBox, QDialogButtonBox, QLabel, QColorDialog, QLineEdit,
)

from ..model.elements import PowerTree, Block
from .layout import block_pins

SIDES = ["auto", "top", "bottom", "left", "right"]


class BlockDesignerDialog(QDialog):
    def __init__(self, tree: PowerTree, block: Block, parent=None):
        super().__init__(parent)
        self.tree = tree
        self.block = block
        self.setWindowTitle(f"Block designer — {block.name}")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)

        info = QLabel(
            "Customize how this block renders when collapsed to a summary "
            "node: place each pin on any card side, reorder pins, set the "
            "card size and add your own info lines.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #98a3b8;")
        lay.addWidget(info)

        form = QFormLayout()
        lay.addLayout(form)
        self.name_edit = QLineEdit(block.name)
        form.addRow("Block name", self.name_edit)

        # ---- pins table ----
        ins, outs = block_pins(tree, block.id)
        self.pins = QTreeWidget()
        self.pins.setColumnCount(3)
        self.pins.setHeaderLabels(["Pin (net)", "Direction", "Side"])
        self.pins.setRootIsDecorated(False)
        self.pins.setColumnWidth(0, 200)
        self.pins.setColumnWidth(1, 80)
        order_in = (block.pin_order or {}).get("in") or []
        order_out = (block.pin_order or {}).get("out") or []

        def ordered(nets, saved):
            rank = {n: i for i, n in enumerate(saved)}
            return sorted(nets, key=lambda n: (rank.get(n, len(rank) + 1), n))

        for direction, nets in (("in", ordered(ins, order_in)),
                                ("out", ordered(outs, order_out))):
            for net in nets:
                item = QTreeWidgetItem(self.pins, [net, direction, ""])
                combo = QComboBox()
                combo.addItems(SIDES)
                side = (block.pin_side or {}).get(net)
                combo.setCurrentText(side if side in SIDES else "auto")
                self.pins.setItemWidget(item, 2, combo)
        lay.addWidget(self.pins, 1)

        row = QHBoxLayout()
        up = QPushButton("▲ Move up")
        up.clicked.connect(lambda: self._move(-1))
        down = QPushButton("▼ Move down")
        down.clicked.connect(lambda: self._move(1))
        row.addWidget(up)
        row.addWidget(down)
        row.addStretch(1)
        lay.addLayout(row)

        form2 = QFormLayout()
        lay.addLayout(form2)
        self.w_spin = QDoubleSpinBox()
        self.w_spin.setRange(0, 2000)
        self.w_spin.setSpecialValueText("auto")
        self.w_spin.setValue(block.width or 0)
        self.w_spin.setToolTip("0 = automatic (grows with pin count)")
        form2.addRow("Card width (px)", self.w_spin)
        self.h_spin = QDoubleSpinBox()
        self.h_spin.setRange(0, 1200)
        self.h_spin.setSpecialValueText("auto")
        self.h_spin.setValue(block.height or 0)
        form2.addRow("Card height (px)", self.h_spin)
        self.stats_check = QCheckBox("Show power stats (P in / dissipated / "
                                     "pass-through)")
        self.stats_check.setChecked(block.show_stats)
        form2.addRow("", self.stats_check)
        self.info_edit = QPlainTextEdit(block.info_text)
        self.info_edit.setPlaceholderText(
            "Custom info lines shown on the card, one per line\n"
            "e.g.  XC7Z020-1CLG484\n      bank budget rev C")
        self.info_edit.setMaximumHeight(70)
        form2.addRow("Info lines", self.info_edit)
        self.color_btn = QPushButton(block.color)
        self.color_btn.setStyleSheet(
            f"background: {block.color}; color: white; font-weight: 600;")
        self.color_btn.clicked.connect(self._pick_color)
        self._color = block.color
        form2.addRow("Accent color", self.color_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _move(self, delta: int):
        item = self.pins.currentItem()
        if item is None:
            return
        idx = self.pins.indexOfTopLevelItem(item)
        target = idx + delta
        if target < 0 or target >= self.pins.topLevelItemCount():
            return
        combo = self.pins.itemWidget(item, 2)
        side = combo.currentText() if combo else "auto"
        taken = self.pins.takeTopLevelItem(idx)
        self.pins.insertTopLevelItem(target, taken)
        combo2 = QComboBox()
        combo2.addItems(SIDES)
        combo2.setCurrentText(side)
        self.pins.setItemWidget(taken, 2, combo2)
        self.pins.setCurrentItem(taken)

    def _pick_color(self):
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor(self._color), self,
                                      "Block accent color")
        if color.isValid():
            self._color = color.name()
            self.color_btn.setText(self._color)
            self.color_btn.setStyleSheet(
                f"background: {self._color}; color: white;"
                "font-weight: 600;")

    def _apply(self):
        b = self.block
        b.name = self.name_edit.text().strip() or b.name
        b.width = self.w_spin.value() or None
        b.height = self.h_spin.value() or None
        b.show_stats = self.stats_check.isChecked()
        b.info_text = self.info_edit.toPlainText()
        b.color = self._color
        pin_side = {}
        order_in, order_out = [], []
        for i in range(self.pins.topLevelItemCount()):
            item = self.pins.topLevelItem(i)
            net = item.text(0)
            direction = item.text(1)
            combo = self.pins.itemWidget(item, 2)
            side = combo.currentText() if combo else "auto"
            if side != "auto":
                pin_side[net] = side
            (order_in if direction == "in" else order_out).append(net)
        b.pin_side = pin_side
        b.pin_order = {"in": order_in, "out": order_out}
        self.accept()
