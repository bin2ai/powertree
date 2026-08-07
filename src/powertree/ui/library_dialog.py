"""Component library manager: browse user parts + built-in templates, place
parts into the current tree, save blocks as parts, import/export .json."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QDialogButtonBox, QFileDialog, QMessageBox,
    QInputDialog,
)

from .. import library
from ..templates import TEMPLATES
from ..model.elements import PowerTree


class LibraryDialog(QDialog):
    """Returns with .placed = list of created elements when a part was
    placed into the tree."""

    def __init__(self, tree: PowerTree | None, parent=None):
        super().__init__(parent)
        self.tree = tree
        self.placed: list = []
        self.setWindowTitle("Component library")
        self.resize(680, 460)
        lay = QVBoxLayout(self)

        info = QLabel(
            "Your saved parts live in a per-user library "
            f"({library.library_path()}) and appear alongside the built-in "
            "templates everywhere (Ctrl+T, CLI, MCP). Export a part to a "
            ".json file to share it; import merges into your library.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #98a3b8;")
        lay.addWidget(info)

        self.list = QTreeWidget()
        self.list.setColumnCount(4)
        self.list.setHeaderLabels(["Part", "Category", "Elements", "Source"])
        self.list.setRootIsDecorated(False)
        self.list.setAlternatingRowColors(True)
        for i, w in enumerate([230, 120, 70, 90]):
            self.list.setColumnWidth(i, w)
        lay.addWidget(self.list, 1)
        self._reload()

        row = QHBoxLayout()
        place = QPushButton("⌸ Place into tree…")
        place.setToolTip("Instantiate the selected part (maps its rails to "
                         "existing elements)")
        place.clicked.connect(self._place)
        row.addWidget(place)
        save_block = QPushButton("＋ Save block as part…")
        save_block.setToolTip("Capture one of the current tree's blocks "
                              "(members, topology, designer style) as a "
                              "reusable part")
        save_block.clicked.connect(self._save_block)
        row.addWidget(save_block)
        imp = QPushButton("⇩ Import…")
        imp.clicked.connect(self._import)
        row.addWidget(imp)
        exp = QPushButton("⇧ Export…")
        exp.clicked.connect(self._export)
        row.addWidget(exp)
        rm = QPushButton("✕ Delete")
        rm.clicked.connect(self._delete)
        row.addWidget(rm)
        row.addStretch(1)
        lay.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        lay.addWidget(buttons)

    # ------------------------------------------------------------------ data
    def _reload(self):
        self.list.clear()
        for part in library.load_library():
            item = QTreeWidgetItem(self.list, [
                part["name"], part.get("category", "My Library"),
                str(len(part.get("items", []))), "library"])
            item.setData(0, Qt.UserRole, part)
        for t in TEMPLATES:
            item = QTreeWidgetItem(self.list, [
                t.name, t.category, str(len(t.items)), "built-in"])
            item.setData(0, Qt.UserRole, None)
            item.setForeground(3, self.list.palette().brush(
                self.list.palette().ColorRole.PlaceholderText))

    def _selected_part(self):
        item = self.list.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    # --------------------------------------------------------------- actions
    def _place(self):
        item = self.list.currentItem()
        if item is None or self.tree is None:
            return
        part = item.data(0, Qt.UserRole)
        key = part["key"] if part else None
        from .template_dialog import TemplateDialog
        dlg = TemplateDialog(self.tree, self, preselect_key=key or
                             self._builtin_key(item))
        if dlg.exec() and dlg.created:
            # apply saved designer style for library parts
            if part and part.get("block_style") and dlg.created:
                block = self.tree.blocks.get(dlg.created[0].block_id)
                if block is not None:
                    for f in library._STYLE_FIELDS:
                        if f in part["block_style"]:
                            setattr(block, f, part["block_style"][f])
            self.placed = dlg.created
            self.accept()

    def _builtin_key(self, item) -> str | None:
        name = item.text(0)
        for t in TEMPLATES:
            if t.name == name:
                return t.key
        return None

    def _save_block(self):
        if self.tree is None or not self.tree.blocks:
            QMessageBox.information(self, "Save block",
                                    "The current tree has no blocks.")
            return
        blocks = list(self.tree.blocks.values())
        names = [b.name for b in blocks]
        name, ok = QInputDialog.getItem(
            self, "Save block as part", "Block to capture:", names, 0, False)
        if not ok:
            return
        block = blocks[names.index(name)]
        try:
            part = library.block_to_part(self.tree, block.id)
            library.add_part(part)
        except ValueError as exc:
            QMessageBox.warning(self, "Save block", str(exc))
            return
        self._reload()
        QMessageBox.information(
            self, "Save block",
            f"Saved '{part['name']}' ({len(part['items'])} elements) to "
            "your library — available from Ctrl+T everywhere.")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import library part(s)", "", "Library part (*.json)")
        if not path:
            return
        try:
            parts = library.import_part(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Import", f"Import failed:\n{exc}")
            return
        self._reload()
        QMessageBox.information(
            self, "Import", f"Imported {len(parts)} part(s).")

    def _export(self):
        part = self._selected_part()
        if part is None:
            QMessageBox.information(
                self, "Export", "Select one of YOUR library parts "
                "(built-ins ship with the app).")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export part", f"{part['key']}.json",
            "Library part (*.json)")
        if not path:
            return
        library.export_part(part, path)
        QMessageBox.information(self, "Export", f"Exported to {path}")

    def _delete(self):
        part = self._selected_part()
        if part is None:
            QMessageBox.information(self, "Delete",
                                    "Built-in templates cannot be deleted.")
            return
        if QMessageBox.question(
                self, "Delete part",
                f"Remove '{part['name']}' from your library?") == \
                QMessageBox.StandardButton.Yes:
            library.remove_part(part["key"])
            self._reload()
