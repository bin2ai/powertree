"""Command palette (Ctrl+K): fuzzy-search every menu action and run it."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu,
)


def _collect_actions(menubar):
    """(path, QAction) for every enabled, named action in the menu tree."""
    out = []

    def walk(menu: QMenu, prefix: str):
        for action in menu.actions():
            if action.menu() is not None:
                walk(action.menu(), f"{prefix}{action.text().replace('&', '')} › ")
            elif action.text() and not action.isSeparator():
                label = action.text().replace("&", "")
                out.append((f"{prefix}{label}", action))
    for action in menubar.actions():
        if action.menu() is not None:
            walk(action.menu(), f"{action.text().replace('&', '')} › ")
    return out


class CommandPalette(QDialog):
    def __init__(self, mainwindow):
        super().__init__(mainwindow)
        self.setWindowTitle("Command palette")
        self.setModal(True)
        self.resize(520, 380)
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Type a command… (e.g. 'export pdf', 'heat', 'validate')")
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._run_current)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemActivated.connect(lambda _: self._run_current())
        lay.addWidget(self.list, 1)
        self._entries = _collect_actions(mainwindow.menuBar())
        self._filter("")
        self.search.setFocus()

    def _filter(self, text: str):
        words = text.lower().split()
        self.list.clear()
        for path, action in self._entries:
            if not action.isEnabled():
                continue
            hay = path.lower()
            if all(w in hay for w in words):
                shortcut = action.shortcut().toString()
                label = f"{path}    ({shortcut})" if shortcut else path
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, action)
                self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _run_current(self):
        item = self.list.currentItem()
        if item is None:
            return
        action = item.data(Qt.UserRole)
        self.accept()
        action.trigger()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Down, Qt.Key_Up):
            row = self.list.currentRow()
            row += 1 if event.key() == Qt.Key_Down else -1
            self.list.setCurrentRow(max(0, min(row, self.list.count() - 1)))
            event.accept()
            return
        super().keyPressEvent(event)
