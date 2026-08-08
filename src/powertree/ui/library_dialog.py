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
        sources = [(library.library_path(), "library")]
        project_lib = library.project_library_path()
        if project_lib:
            sources.append((project_lib, "project"))
        for path, label in sources:
            for part in library.load_parts(path):
                meta = part.get("meta") or {}
                info = f"v{meta.get('version', 1)}"
                if meta.get("author"):
                    info += f" · {meta['author']}"
                if meta.get("updated"):
                    info += f" · {meta['updated']}"
                item = QTreeWidgetItem(self.list, [
                    f"{part['name']}  ({info})",
                    part.get("category", "My Library"),
                    str(len(part.get("items", []))), label])
                item.setData(0, Qt.UserRole, part)
                item.setData(0, Qt.UserRole + 1, path)
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
        target = None
        project_lib = library.project_library_path()
        if project_lib:
            box = QMessageBox(self)
            box.setWindowTitle("Save block as part")
            box.setText("Save to which library?")
            user_btn = box.addButton("My library (this PC)",
                                     QMessageBox.ButtonRole.AcceptRole)
            proj_btn = box.addButton("Project library (share via repo)",
                                     QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is proj_btn:
                target = project_lib
            elif box.clickedButton() is not user_btn:
                return
        try:
            part = library.block_to_part(self.tree, block.id)
            library.add_part(part, path=target)
        except ValueError as exc:
            QMessageBox.warning(self, "Save block", str(exc))
            return
        self._reload()
        where = "the project library" if target else "your library"
        QMessageBox.information(
            self, "Save block",
            f"Saved '{part['name']}' ({len(part['items'])} elements) to "
            f"{where} — available from Ctrl+T everywhere.")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import library part(s)", "", "Library part (*.json)")
        if not path:
            return
        # conflict handling: ask when any imported key already exists
        try:
            with open(path, "r", encoding="utf-8") as fh:
                import json as _json
                incoming = _json.load(fh)
            incoming = incoming if isinstance(incoming, list) else [incoming]
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Import", f"Import failed:\n{exc}")
            return
        existing = {p.get("key") for p in library.load_library()}
        conflicts = [p.get("key") for p in incoming
                     if p.get("key") in existing]
        on_conflict = "overwrite"
        if conflicts:
            box = QMessageBox(self)
            box.setWindowTitle("Import conflicts")
            box.setText(f"{len(conflicts)} part(s) already exist "
                        f"({', '.join(conflicts[:4])}…). How to handle?")
            ow = box.addButton("Overwrite (bump version)",
                               QMessageBox.ButtonRole.AcceptRole)
            rn = box.addButton("Keep both (rename import)",
                               QMessageBox.ButtonRole.AcceptRole)
            sk = box.addButton("Skip conflicting",
                               QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is rn:
                on_conflict = "rename"
            elif box.clickedButton() is sk:
                on_conflict = "skip"
            elif box.clickedButton() is not ow:
                return
        try:
            parts = library.import_part(path, on_conflict=on_conflict)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Import", f"Import failed:\n{exc}")
            return
        self._reload()
        QMessageBox.information(
            self, "Import", f"Imported {len(parts)} part(s).")

    def _export(self):
        part = self._selected_part()
        if part is None:
            # nothing selected (or a built-in): offer whole-library export
            if QMessageBox.question(
                    self, "Export",
                    "Export your ENTIRE library to one file?") == \
                    QMessageBox.StandardButton.Yes:
                path, _ = QFileDialog.getSaveFileName(
                    self, "Export library", "powertree_library.json",
                    "Library (*.json)")
                if path:
                    library.export_library(path)
                    QMessageBox.information(self, "Export",
                                            f"Exported to {path}")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export part", f"{part['key']}.json",
            "Library part (*.json)")
        if not path:
            return
        library.export_part(part, path)
        QMessageBox.information(self, "Export", f"Exported to {path}")

    def _delete(self):
        item = self.list.currentItem()
        part = self._selected_part()
        if part is None:
            QMessageBox.information(self, "Delete",
                                    "Built-in templates cannot be deleted.")
            return
        source_path = item.data(0, Qt.UserRole + 1)
        if QMessageBox.question(
                self, "Delete part",
                f"Remove '{part['name']}' from this library?") == \
                QMessageBox.StandardButton.Yes:
            library.remove_part(part["key"], path=source_path)
            self._reload()
