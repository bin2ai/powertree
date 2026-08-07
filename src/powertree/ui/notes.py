"""Hierarchical documentation notes: tree + markdown editor + live preview.

Notes capture WHERE power figures came from (datasheets, emails, lab
measurements). They nest arbitrarily, embed images, link to tree elements, and
export to Markdown / HTML / PDF from the File menu.
"""

from __future__ import annotations

import base64
import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
    QPlainTextEdit, QTextBrowser, QToolButton, QLineEdit, QFileDialog,
    QMessageBox, QMenu, QLabel,
)

from ..model.elements import Project, Note
from ..export.md_render import md_to_html_body

_PREVIEW_CSS = """
body { font-family: 'Segoe UI'; color: #e8ecf5; background: #131722; }
h1, h2, h3 { color: #ffffff; }
a { color: #7c9dff; }
code, pre { background: #1a2030; color: #d7e3ff; }
table { border-collapse: collapse; }
th, td { border: 1px solid #2c3650; padding: 3px 8px; }
img { max-width: 100%; }
"""


class NotesPanel(QWidget):
    changed = Signal()
    jumpToElement = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.current: Note | None = None
        self._items: dict[str, QTreeWidgetItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        for label, tip, slot in (
                ("＋", "Add top-level note", self.add_root_note),
                ("↳", "Add child under selected note", self.add_child_note),
                ("🖼", "Insert image into note", self.insert_image),
                ("🔗", "Link note to the selected tree element", None),
                ("✕", "Delete selected note (and children)", self.delete_note)):
            btn = QToolButton()
            btn.setText(label)
            btn.setToolTip(tip)
            if label == "🔗":
                self.link_btn = btn
            elif slot:
                btn.clicked.connect(slot)
            bar.addWidget(btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Search notes (title + body)…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_search)
        layout.addWidget(self.search)

        split = QSplitter(Qt.Vertical)
        layout.addWidget(split, 1)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.itemSelectionChanged.connect(self._on_select)
        self.tree_widget.itemChanged.connect(self._on_rename)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(
            self._note_context_menu)
        split.addWidget(self.tree_widget)

        editor_split = QSplitter(Qt.Vertical)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "Markdown body — # headings, **bold**, tables, images, lists…")
        self.editor.textChanged.connect(self._on_edit)
        editor_split.addWidget(self.editor)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.preview.document().setDefaultStyleSheet(_PREVIEW_CSS)
        editor_split.addWidget(self.preview)
        split.addWidget(editor_split)
        split.setSizes([180, 420])

        self.links_label = QLabel("")
        self.links_label.setStyleSheet("color: #98a3b8; font-size: 11px;")
        self.links_label.setWordWrap(True)
        layout.addWidget(self.links_label)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(350)
        self._preview_timer.timeout.connect(self._render_preview)

    # ------------------------------------------------------------------- api
    def set_project(self, project: Project):
        self.project = project
        self.current = None
        self.rebuild()

    def rebuild(self):
        self.tree_widget.blockSignals(True)
        self.tree_widget.clear()
        self._items.clear()
        if self.project:
            def add(parent_id, parent_item):
                for note in self.project.note_children(parent_id):
                    item = QTreeWidgetItem(parent_item, [note.title])
                    item.setData(0, Qt.UserRole, note.id)
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                    self._items[note.id] = item
                    add(note.id, item)
            add(None, self.tree_widget)
            self.tree_widget.expandAll()
        self.tree_widget.blockSignals(False)
        self._sync_editor()

    def _apply_search(self, text: str):
        """Hide notes not matching; keep ancestors of matches visible."""
        text = text.strip().lower()
        if not self.project:
            return
        if not text:
            for item in self._items.values():
                item.setHidden(False)
            return
        matches = {n.id for n in self.project.notes.values()
                   if text in n.title.lower() or text in n.body_md.lower()}
        keep = set()
        for nid in matches:
            note = self.project.notes.get(nid)
            while note is not None:
                keep.add(note.id)
                note = self.project.notes.get(note.parent_id) \
                    if note.parent_id else None
        for nid, item in self._items.items():
            item.setHidden(nid not in keep)

    def focus_element(self, element_id: str):
        """Select the first note linked to the element (or hint if none)."""
        if not self.project:
            return
        for note in self.project.notes.values():
            if element_id in note.linked_element_ids:
                item = self._items.get(note.id)
                if item:
                    self.tree_widget.setCurrentItem(item)
                return
        self.links_label.setText(
            "No note is linked to this element yet — create one and use 🔗.")

    def selected_note(self) -> Note | None:
        items = self.tree_widget.selectedItems()
        if not items or not self.project:
            return None
        return self.project.notes.get(items[0].data(0, Qt.UserRole))

    # ----------------------------------------------------------------- slots
    def _on_select(self):
        self.current = self.selected_note()
        self._sync_editor()

    def _sync_editor(self):
        note = self.current
        self.editor.blockSignals(True)
        self.editor.setPlainText(note.body_md if note else "")
        self.editor.setEnabled(note is not None)
        self.editor.blockSignals(False)
        self._render_preview()
        self._render_links()

    def _on_edit(self):
        if self.current is not None:
            self.current.body_md = self.editor.toPlainText()
            self.changed.emit()
            self._preview_timer.start()

    def _on_rename(self, item, _col):
        note = self.project.notes.get(item.data(0, Qt.UserRole)) \
            if self.project else None
        if note:
            note.title = item.text(0) or "Untitled"
            self.changed.emit()

    def _render_preview(self):
        note = self.current
        if note is None:
            self.preview.setHtml("")
            return
        body = md_to_html_body(note.body_md, note.images)
        self.preview.setHtml(f"<html><body>{body}</body></html>")

    def _render_links(self):
        note = self.current
        if not note or not self.project:
            self.links_label.setText("")
            return
        names = []
        for tree in self.project.trees:
            for el_id in note.linked_element_ids:
                el = tree.elements.get(el_id)
                if el:
                    names.append(el.name)
        self.links_label.setText(
            f"Linked elements: {', '.join(names)}" if names
            else "Not linked to any element (use 🔗 with an element selected).")

    # --------------------------------------------------------------- actions
    def add_root_note(self):
        if not self.project:
            return
        note = self.project.add_note("New note")
        self.changed.emit()
        self.rebuild()
        item = self._items.get(note.id)
        if item:
            self.tree_widget.setCurrentItem(item)
            self.tree_widget.editItem(item, 0)

    def add_child_note(self):
        if not self.project:
            return
        parent = self.selected_note()
        note = self.project.add_note("New note",
                                     parent_id=parent.id if parent else None)
        self.changed.emit()
        self.rebuild()
        item = self._items.get(note.id)
        if item:
            self.tree_widget.setCurrentItem(item)
            self.tree_widget.editItem(item, 0)

    def delete_note(self):
        note = self.selected_note()
        if not note or not self.project:
            return
        count = 1 + len([1 for n in self.project.notes.values()
                         if n.parent_id == note.id])
        if QMessageBox.question(
                self, "Delete note",
                f"Delete '{note.title}' and all child notes?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.project.remove_note(note.id)
        self.current = None
        self.changed.emit()
        self.rebuild()

    def insert_image(self):
        note = self.current
        if note is None:
            QMessageBox.information(self, "Insert image",
                                    "Select a note first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.svg)")
        if not path:
            return
        name = os.path.basename(path)
        base, ext = os.path.splitext(name)
        i = 2
        while name in note.images:
            name = f"{base}_{i}{ext}"
            i += 1
        with open(path, "rb") as fh:
            note.images[name] = base64.b64encode(fh.read()).decode("ascii")
        self.editor.insertPlainText(f"\n![{base}]({name})\n")
        self.changed.emit()

    def _note_context_menu(self, pos):
        note = self.selected_note()
        if note is None or self.project is None:
            return
        menu = QMenu(self)
        menu.addAction("Export this note + children → Markdown…",
                       lambda: self._export_subtree("md"))
        menu.addAction("Export this note + children → HTML…",
                       lambda: self._export_subtree("html"))
        menu.addAction("Export this note + children → PDF…",
                       lambda: self._export_subtree("pdf"))
        menu.addSeparator()
        menu.addAction("Delete note (and children)", self.delete_note)
        menu.exec(self.tree_widget.mapToGlobal(pos))

    def _export_subtree(self, fmt: str):
        note = self.selected_note()
        if note is None:
            return
        filters = {"md": "Markdown (*.md)", "html": "HTML (*.html)",
                   "pdf": "PDF (*.pdf)"}
        path, _ = QFileDialog.getSaveFileName(
            self, "Export note subtree", f"{note.title}.{fmt}", filters[fmt])
        if not path:
            return
        from ..export.notes_export import (
            export_notes_markdown, export_notes_html, export_notes_pdf)
        fn = {"md": export_notes_markdown, "html": export_notes_html,
              "pdf": export_notes_pdf}[fmt]
        try:
            written = fn(self.project, path, root_note_id=note.id)
        except Exception as exc:
            QMessageBox.critical(self, "Export note subtree",
                                 f"Export failed:\n{exc}")
            return
        self.links_label.setText(f"Exported: {written}")

    def link_current_to(self, element_id: str, element_name: str):
        note = self.current
        if note is None:
            QMessageBox.information(
                self, "Link note",
                "Select a note first, then press 🔗 to link it to the "
                "selected tree element.")
            return
        if element_id in note.linked_element_ids:
            note.linked_element_ids.remove(element_id)
            self.links_label.setText(f"Unlinked from {element_name}.")
        else:
            note.linked_element_ids.append(element_id)
            self.links_label.setText(f"Linked to {element_name}.")
        self.changed.emit()
        self._render_links()
