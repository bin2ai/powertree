"""'Add device from template' dialog: pick a template, name the block,
assign a refdes and map each external rail to an existing parent element."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QLabel,
    QDialogButtonBox, QListWidget, QListWidgetItem, QHBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from ..model.elements import PowerTree, ElementKind
from ..templates import all_templates, instantiate_template


class TemplateDialog(QDialog):
    def __init__(self, tree: PowerTree, parent=None,
                 preselect_key: str | None = None):
        super().__init__(parent)
        self.tree = tree
        self.created: list = []
        self._preselect_key = preselect_key
        self.setWindowTitle("Add device from template")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        lay.addLayout(row)

        # template picker (grouped by category)
        self.list = QListWidget()
        self.list.setMinimumWidth(200)
        cats: dict = {}
        for t in all_templates():
            cats.setdefault(t.category, []).append(t)
        preselect_item = None
        for cat in sorted(cats):
            hdr = QListWidgetItem(f"— {cat} —")
            hdr.setFlags(Qt.NoItemFlags)
            self.list.addItem(hdr)
            for t in cats[cat]:
                item = QListWidgetItem("  " + t.name)
                item.setData(Qt.UserRole, t)
                self.list.addItem(item)
                if preselect_key and t.key == preselect_key:
                    preselect_item = item
        self.list.currentItemChanged.connect(self._on_pick)
        if preselect_item is not None:
            self.list.setCurrentItem(preselect_item)
        row.addWidget(self.list)

        right = QWidget()
        self.form = QFormLayout(right)
        row.addWidget(right, 1)

        self.desc = QLabel("Select a template.")
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet("color: #98a3b8;")
        self.form.addRow(self.desc)
        self.block_name = QLineEdit()
        self.form.addRow("Block name", self.block_name)
        self.refdes = QLineEdit()
        self.refdes.setPlaceholderText("e.g. U1")
        self.form.addRow("RefDes", self.refdes)
        self.rail_combos: dict = {}

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        lay.addWidget(self.buttons)

        self.error = QLabel("")
        self.error.setStyleSheet("color: #f43f5e;")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)

    def _parents(self):
        """Eligible rail parents: source, converters, series elements."""
        out = []
        for el in self.tree.elements.values():
            if el.kind in (ElementKind.SOURCE, ElementKind.CONVERTER,
                           ElementKind.SERIES):
                label = el.name
                if el.signal_name:
                    label += f"  [{el.signal_name}]"
                out.append((label, el.id))
        out.sort()
        return out

    def _on_pick(self, item, _prev=None):
        template = item.data(Qt.UserRole) if item else None
        for combo in self.rail_combos.values():
            self.form.removeRow(combo)
        self.rail_combos.clear()
        if template is None:
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            return
        self.template = template
        self.desc.setText(template.description)
        if not self.block_name.text():
            self.block_name.setText(template.name)
        parents = self._parents()
        used_rails = {i.rail for i in template.items
                      if not i.rail.startswith("@")}
        for rail in template.rails:
            if rail not in used_rails:
                continue
            combo = QComboBox()
            for label, el_id in parents:
                combo.addItem(label, el_id)
            # preselect a parent whose signal/name mentions the rail key
            key = rail.split()[0].lower().replace("v", "v")
            for i, (label, _id) in enumerate(parents):
                if key in label.lower().replace("_", "."):
                    combo.setCurrentIndex(i)
                    break
            self.rail_combos[rail] = combo
            self.form.addRow(f"Rail {rail} ←", combo)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(parents))
        if not parents:
            self.error.setText("This tree has no source/converter/series "
                               "element to attach to yet.")

    def _accept(self):
        rail_map = {rail: combo.currentData()
                    for rail, combo in self.rail_combos.items()}
        try:
            self.created = instantiate_template(
                self.tree, self.template, rail_map,
                block_name=self.block_name.text().strip(),
                refdes=self.refdes.text().strip())
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        # library parts carry a saved block-designer style — apply it
        from .. import library as _lib
        for part in _lib.load_library():
            if part.get("key") == self.template.key and \
                    part.get("block_style") and self.created:
                block = self.tree.blocks.get(self.created[0].block_id)
                if block is not None:
                    for f in _lib._STYLE_FIELDS:
                        if f in part["block_style"]:
                            setattr(block, f, part["block_style"][f])
                break
        self.accept()
