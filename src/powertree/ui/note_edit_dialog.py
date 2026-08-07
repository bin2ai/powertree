"""Per-element documentation editor dialog.

Opened straight from the Properties panel: edits the element's linked note
(creating + linking one automatically if none exists) with the full markdown
editor, live preview and image import — same Note objects as the central
Documentation Notes vault, so everything stays in one searchable place."""

from __future__ import annotations

import base64
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QPlainTextEdit,
    QTextBrowser, QPushButton, QLineEdit, QFileDialog, QLabel,
    QDialogButtonBox, QComboBox,
)

from ..model.elements import Project, Element, Note
from ..export.md_render import md_to_html_body
from .notes import _PREVIEW_CSS


class NoteEditDialog(QDialog):
    def __init__(self, project: Project, element: Element, parent=None):
        super().__init__(parent)
        self.project = project
        self.element = element
        self.setWindowTitle(f"Documentation — {element.name}")
        self.resize(780, 560)

        linked = project.notes_for_element(element.id)
        if linked:
            self.note = linked[0]
            self._created = False
        else:
            self.note = project.add_note(element.name)
            self.note.linked_element_ids.append(element.id)
            self._created = True

        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit(self.note.title)
        top.addWidget(self.title_edit, 1)
        if len(linked) > 1:
            self.pick = QComboBox()
            for n in linked:
                self.pick.addItem(n.title, n.id)
            self.pick.currentIndexChanged.connect(self._switch_note)
            top.addWidget(self.pick)
        img_btn = QPushButton("🖼 Insert image…")
        img_btn.setToolTip("Embed a PNG/JPG/GIF/SVG into the note (stored "
                           "inside the project file)")
        img_btn.clicked.connect(self._insert_image)
        top.addWidget(img_btn)
        lay.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.editor = QPlainTextEdit(self.note.body_md)
        self.editor.setPlaceholderText(
            "Markdown — where did this element's numbers come from?\n"
            "# headings, **bold**, | tables |, ![images](name), lists…")
        self.editor.textChanged.connect(lambda: self._timer.start())
        split.addWidget(self.editor)
        self.preview = QTextBrowser()
        self.preview.document().setDefaultStyleSheet(_PREVIEW_CSS)
        split.addWidget(self.preview)
        split.setSizes([390, 390])
        lay.addWidget(split, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._render)
        self._render()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self._cancel)
        lay.addWidget(buttons)

    def _switch_note(self):
        self._commit_current()
        note_id = self.pick.currentData()
        self.note = self.project.notes[note_id]
        self.title_edit.setText(self.note.title)
        self.editor.setPlainText(self.note.body_md)
        self._render()

    def _render(self):
        body = md_to_html_body(self.editor.toPlainText(), self.note.images)
        self.preview.setHtml(f"<html><body>{body}</body></html>")

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.svg)")
        if not path:
            return
        name = os.path.basename(path)
        base, ext = os.path.splitext(name)
        i = 2
        while name in self.note.images:
            name = f"{base}_{i}{ext}"
            i += 1
        with open(path, "rb") as fh:
            self.note.images[name] = base64.b64encode(fh.read()).decode("ascii")
        self.editor.insertPlainText(f"\n![{base}]({name})\n")

    def _commit_current(self):
        self.note.title = self.title_edit.text().strip() or self.element.name
        self.note.body_md = self.editor.toPlainText()

    def _save(self):
        self._commit_current()
        self.accept()

    def _cancel(self):
        if self._created and not self.editor.toPlainText().strip():
            self.project.remove_note(self.note.id)   # don't keep empty stubs
        self.reject()
