"""PowerTree main window — wires model, canvas, list, properties, notes,
search, findings and every import/export path together.

Auto-refresh contract: any model mutation funnels through refresh(), which
re-solves the current tree bottom-up and repaints every view.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QDockWidget, QTabWidget, QToolBar, QComboBox, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QFileDialog, QInputDialog,
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QListView,
    QApplication,
)

from .. import APP_NAME, FILE_EXT
from ..model.elements import (
    Project, PowerTree, Source, Converter, Load, SeriesElement, Element,
    ElementKind,
)
from ..model.calc import solve_tree, TreeResults, fmt_si
from ..model import serialization
from ..sampledata import build_sample_project
from ..export.pdf_report import export_pdf_report
from ..export.excel_export import export_excel_xlsm, export_excel_xlsx
from ..export.image_export import export_tree_png
from ..export.notes_export import (
    export_notes_markdown, export_notes_html, export_notes_pdf)
from .canvas import PowerCanvas
from .listview import TreeListView
from .props import PropertyPanel
from .notes import NotesPanel
from . import layout as L

SEARCH_FIELDS = ("name", "signal_name", "refdes", "part_number", "pins",
                 "description")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project: Project = build_sample_project()
        self.current_tree: PowerTree | None = self.project.trees[0] \
            if self.project.trees else None
        self.results: TreeResults | None = None
        self.selected_element_id: str = ""
        self.dirty = False

        self.setWindowTitle(APP_NAME)
        self.resize(1560, 940)
        self._build_central()
        self._build_docks()
        self._build_toolbar()
        self._build_menus()
        self._build_statusbar()
        self._rebuild_tree_list()
        self.refresh(full=True)

    # ================================================================ layout
    def _build_central(self):
        self.tabs = QTabWidget()
        self.canvas = PowerCanvas()
        self.canvas.elementSelected.connect(self._on_canvas_select)
        self.canvas.collapseToggled.connect(self._on_collapse_toggle)
        self.canvas.nodeMoved.connect(self._mark_dirty)
        self.list_view = TreeListView()
        self.list_view.elementSelected.connect(self._on_list_select)
        self.tabs.addTab(self.canvas, "Flowchart")
        self.tabs.addTab(self.list_view, "List view")
        self.setCentralWidget(self.tabs)

    def _build_docks(self):
        # left: project explorer
        self.trees_list = QListWidget()
        self.trees_list.currentRowChanged.connect(self._on_tree_pick)
        self.trees_list.itemDoubleClicked.connect(self._rename_tree)
        explorer = QWidget()
        lay = QVBoxLayout(explorer)
        lay.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        for text, tip, slot in (("＋ Tree", "Add a new power tree",
                                 self._add_tree),
                                ("✕", "Delete selected tree",
                                 self._delete_tree)):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(self.trees_list, 1)
        self.explorer_dock = QDockWidget("Power Trees", self)
        self.explorer_dock.setWidget(explorer)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.explorer_dock)

        # right: properties + notes (tabbed)
        self.props = PropertyPanel()
        self.props.changed.connect(lambda: self.refresh())
        self.props.structureChanged.connect(lambda: self.refresh(full=True))
        self.props.openNotesRequested.connect(self._open_notes_for)
        self.props_dock = QDockWidget("Properties", self)
        self.props_dock.setWidget(self.props)
        self.addDockWidget(Qt.RightDockWidgetArea, self.props_dock)

        self.notes = NotesPanel()
        self.notes.changed.connect(self._mark_dirty)
        self.notes.link_btn.clicked.connect(self._link_note_to_selection)
        self.notes.set_project(self.project)
        self.notes_dock = QDockWidget("Documentation Notes", self)
        self.notes_dock.setWidget(self.notes)
        self.addDockWidget(Qt.RightDockWidgetArea, self.notes_dock)
        self.tabifyDockWidget(self.props_dock, self.notes_dock)
        self.props_dock.raise_()

        # bottom: findings
        self.findings = QListWidget()
        self.findings.itemClicked.connect(self._on_finding_click)
        self.findings_dock = QDockWidget("Findings — margin analysis", self)
        self.findings_dock.setWidget(self.findings)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.findings_dock)

        self.resizeDocks([self.explorer_dock], [230], Qt.Horizontal)
        self.resizeDocks([self.props_dock], [330], Qt.Horizontal)
        self.resizeDocks([self.findings_dock], [130], Qt.Vertical)

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        def act(text, tip, slot, shortcut=None):
            a = QAction(text, self)
            a.setToolTip(tip)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        act("⊕ Source", "Add the source (root) to an empty tree",
            lambda: self._add_element(ElementKind.SOURCE))
        act("⊞ Converter", "Add a converter under the selected element",
            lambda: self._add_element(ElementKind.CONVERTER))
        act("◎ Load", "Add a load under the selected element",
            lambda: self._add_element(ElementKind.LOAD))
        act("≡ Series", "Add a series element under the selected element",
            lambda: self._add_element(ElementKind.SERIES))
        act("▣ Block", "Create a block and assign the selected element",
            self._add_block)
        tb.addSeparator()
        act("🗑 Delete", "Delete the selected element (with its subtree)",
            self._delete_element, QKeySequence.Delete)
        tb.addSeparator()

        tb.addWidget(QLabel(" Layout: "))
        self.orient_combo = QComboBox()
        self.orient_combo.addItems(["Top-down", "Left-right", "Custom (drag)"])
        self.orient_combo.setToolTip(
            "Flowchart placement: automatic top-down / left-right, or custom "
            "free placement by dragging nodes")
        self.orient_combo.currentIndexChanged.connect(self._on_orientation)
        tb.addWidget(self.orient_combo)
        act("⛶ Fit", "Fit the whole tree in the view", self.canvas.fit, "Ctrl+0")
        act("▸ Collapse", "Collapse every converter / series branch",
            lambda: self._set_all_collapsed(True))
        act("▾ Expand", "Expand everything",
            lambda: self._set_all_collapsed(False))
        self.legend_action = QAction("◨ Legend", self)
        self.legend_action.setCheckable(True)
        self.legend_action.setChecked(True)
        self.legend_action.toggled.connect(self._on_legend)
        tb.addAction(self.legend_action)
        tb.addSeparator()

        from PySide6.QtWidgets import QSizePolicy
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(
            "🔍 Search name / signal / refdes / part…  (Ctrl+F)")
        self.search_box.setFixedWidth(280)
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._on_search)
        tb.addWidget(self.search_box)
        focus = QAction(self)
        focus.setShortcut("Ctrl+F")
        focus.triggered.connect(
            lambda: (self.search_box.setFocus(), self.search_box.selectAll()))
        self.addAction(focus)

    def _build_menus(self):
        m_file = self.menuBar().addMenu("&File")

        def add(menu, text, slot, shortcut=None):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        add(m_file, "&New project", self._new_project, QKeySequence.New)
        add(m_file, "&Open project…", self._open_project, QKeySequence.Open)
        add(m_file, "&Save project", self._save_project, QKeySequence.Save)
        add(m_file, "Save project &as…", lambda: self._save_project(force_dialog=True),
            QKeySequence.SaveAs)
        m_file.addSeparator()
        m_export = m_file.addMenu("&Export")
        add(m_export, "PDF report (trees + margins + notes)…", self._export_pdf)
        add(m_export, "Excel macro-enabled report (.xlsm)…", self._export_excel)
        add(m_export, "Flowchart image (HD PNG)…", self._export_png)
        m_export.addSeparator()
        add(m_export, "Notes → Markdown…", lambda: self._export_notes("md"))
        add(m_export, "Notes → HTML…", lambda: self._export_notes("html"))
        add(m_export, "Notes → PDF…", lambda: self._export_notes("pdf"))
        m_file.addSeparator()
        add(m_file, "E&xit", self.close, "Alt+F4")

        m_view = self.menuBar().addMenu("&View")
        for dock in (self.explorer_dock, self.props_dock, self.notes_dock,
                     self.findings_dock):
            m_view.addAction(dock.toggleViewAction())

        m_help = self.menuBar().addMenu("&Help")
        add(m_help, "About PowerTree", self._about)

    def _build_statusbar(self):
        self.status_label = QLabel("")
        self.statusBar().addWidget(self.status_label, 1)

    # ============================================================== refresh
    def refresh(self, full: bool = False):
        """Recalculate the current tree bottom-up and repaint every view."""
        self._mark_dirty()
        tree = self.current_tree
        self.results = solve_tree(tree) if tree else None
        self.canvas.rebuild(tree, self.results, keep_view=not full)
        self.list_view.rebuild(tree, self.results)
        self._rebuild_findings()
        self._update_status()
        if self.selected_element_id and tree and \
                self.selected_element_id in tree.elements:
            self.props.set_target(self.project, tree,
                                  tree.elements[self.selected_element_id])
        else:
            self.selected_element_id = ""
            self.props.set_target(self.project, tree, None)
        if self.search_box.text():
            self._on_search(self.search_box.text())

    def _rebuild_findings(self):
        self.findings.clear()
        if not self.results:
            return
        icons = {"error": "⛔", "warn": "⚠️", "info": "ℹ️"}
        for w in self.results.warnings:
            item = QListWidgetItem(
                f"{icons.get(w.severity, '•')}  [{w.corner}]  {w.message}")
            item.setData(Qt.UserRole, w.element_id)
            self.findings.addItem(item)
        title = "Findings — margin analysis"
        if self.results.warnings:
            errs = sum(1 for w in self.results.warnings if w.severity == "error")
            warns = sum(1 for w in self.results.warnings if w.severity == "warn")
            title += f"  ({errs} errors, {warns} warnings)"
        self.findings_dock.setWindowTitle(title)

    def _update_status(self):
        tree = self.current_tree
        if not tree or not tree.source or not self.results:
            self.status_label.setText("Add a source to start building the tree.")
            return
        src = tree.source
        typ = self.results.get(src.id, "typ")
        mx = self.results.get(src.id, "max")
        mn = self.results.get(src.id, "min")
        errs = sum(1 for w in self.results.warnings if w.severity == "error")
        warns = sum(1 for w in self.results.warnings if w.severity == "warn")
        health = "✅ all margins healthy" if not (errs or warns) else \
            f"⛔ {errs} violations · ⚠️ {warns} low margins"
        self.status_label.setText(
            f"{tree.name} — source power: {fmt_si(mn.p_out, 'W')} min / "
            f"{fmt_si(typ.p_out, 'W')} typ / {fmt_si(mx.p_out, 'W')} max · "
            f"{len(tree.elements)} elements · {health}")

    def _mark_dirty(self):
        self.dirty = True
        self._update_title()

    def _update_title(self):
        star = " •" if self.dirty else ""
        path = f" — {os.path.basename(self.project.file_path)}" \
            if self.project.file_path else ""
        self.setWindowTitle(f"{APP_NAME}{path}{star}")

    # ====================================================== tree management
    def _rebuild_tree_list(self):
        self.trees_list.blockSignals(True)
        self.trees_list.clear()
        for tree in self.project.trees:
            src = tree.source
            sub = f" · {src.v_typ:g} V" if src else " · no source"
            self.trees_list.addItem(f"⚡ {tree.name}{sub}")
        if self.current_tree:
            idx = self.project.trees.index(self.current_tree)
            self.trees_list.setCurrentRow(idx)
        self.trees_list.blockSignals(False)

    def _on_tree_pick(self, row: int):
        if 0 <= row < len(self.project.trees):
            self.current_tree = self.project.trees[row]
            self.selected_element_id = ""
            self.orient_combo.blockSignals(True)
            self.orient_combo.setCurrentIndex(
                {"TD": 0, "LR": 1, "custom": 2}.get(
                    self.current_tree.orientation, 0))
            self.orient_combo.blockSignals(False)
            self.refresh(full=True)
            self.canvas.fit()

    def _add_tree(self):
        tree = self.project.new_tree()
        self.current_tree = tree
        self._rebuild_tree_list()
        self.refresh(full=True)

    def _rename_tree(self, item):
        row = self.trees_list.row(item)
        tree = self.project.trees[row]
        name, ok = QInputDialog.getText(self, "Rename power tree",
                                        "Name:", text=tree.name)
        if ok and name:
            tree.name = name
            self._rebuild_tree_list()
            self.refresh()

    def _delete_tree(self):
        row = self.trees_list.currentRow()
        if row < 0:
            return
        tree = self.project.trees[row]
        if QMessageBox.question(
                self, "Delete power tree",
                f"Delete '{tree.name}' with {len(tree.elements)} elements?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.project.remove_tree(tree.id)
        self.current_tree = self.project.trees[0] if self.project.trees else None
        self._rebuild_tree_list()
        self.refresh(full=True)

    # =================================================== element management
    def _selected_element(self) -> Element | None:
        tree = self.current_tree
        if tree and self.selected_element_id in tree.elements:
            return tree.elements[self.selected_element_id]
        return None

    def _add_element(self, kind: str):
        tree = self.current_tree
        if tree is None:
            QMessageBox.information(self, "Add element",
                                    "Create a power tree first (＋ Tree).")
            return
        classes = {ElementKind.SOURCE: Source, ElementKind.CONVERTER: Converter,
                   ElementKind.LOAD: Load, ElementKind.SERIES: SeriesElement}
        try:
            if kind == ElementKind.SOURCE:
                el = tree.add_element(Source(name="New Source"))
            else:
                parent = self._selected_element()
                if parent is not None and \
                        parent.kind == ElementKind.LOAD:
                    parent = tree.parent_of(parent)
                if parent is None:
                    candidates = [e for e in tree.elements.values()
                                  if tree.can_parent(e)]
                    if tree.source is not None and len(candidates) >= 1:
                        parent = tree.source
                if parent is None:
                    QMessageBox.information(
                        self, "Add element",
                        "Select the parent first (a source, converter or "
                        "series element)." if tree.source else
                        "Start the tree with a ⊕ Source — every power tree "
                        "has exactly one.")
                    return
                names = {ElementKind.CONVERTER: "New Converter",
                         ElementKind.LOAD: "New Load",
                         ElementKind.SERIES: "New Series R"}
                el = tree.add_element(classes[kind](name=names[kind]),
                                      parent_id=parent.id)
        except ValueError as exc:
            QMessageBox.warning(self, "Add element", str(exc))
            return
        self.selected_element_id = el.id
        self._rebuild_tree_list()
        self.refresh(full=True)
        self.canvas.select_element(el.id)

    def _delete_element(self):
        el = self._selected_element()
        tree = self.current_tree
        if el is None or tree is None:
            return
        n = len(tree.descendants_of(el.id))
        msg = f"Delete '{el.name}'" + (f" and its {n} descendants?" if n
                                       else "?")
        if QMessageBox.question(self, "Delete element", msg) \
                != QMessageBox.StandardButton.Yes:
            return
        tree.remove_element(el.id)
        self.selected_element_id = ""
        self._rebuild_tree_list()
        self.refresh(full=True)

    def _add_block(self):
        tree = self.current_tree
        if tree is None:
            return
        name, ok = QInputDialog.getText(self, "New block",
                                        "Block name (e.g. 'MCU', 'RF front end'):")
        if not ok or not name:
            return
        block = tree.add_block(name)
        el = self._selected_element()
        if el is not None:
            el.block_id = block.id
        self.refresh(full=True)

    def _on_collapse_toggle(self, element_id: str):
        tree = self.current_tree
        if tree and element_id in tree.elements:
            el = tree.elements[element_id]
            el.collapsed = not el.collapsed
            self.refresh(full=True)

    def _set_all_collapsed(self, collapsed: bool):
        tree = self.current_tree
        if not tree:
            return
        for el in tree.elements.values():
            if el.kind in (ElementKind.CONVERTER, ElementKind.SERIES) \
                    and tree.children_of(el.id):
                el.collapsed = collapsed
        self.refresh(full=True)
        self.canvas.fit()

    def _on_orientation(self, idx: int):
        tree = self.current_tree
        if not tree:
            return
        new = {0: "TD", 1: "LR", 2: "custom"}[idx]
        if new == "custom" and tree.orientation != "custom":
            # seed custom positions from the current automatic layout
            lay = L.compute_layout(tree, tree.orientation)
            for el_id, (cx, cy) in lay.positions.items():
                tree.elements[el_id].x = cx
                tree.elements[el_id].y = cy
        tree.orientation = new
        self.refresh(full=True)
        self.canvas.fit()

    def _on_legend(self, checked: bool):
        self.canvas.legend_visible = checked
        self.canvas.viewport().update()

    # ========================================================== selection
    def _on_canvas_select(self, element_id: str):
        self.selected_element_id = element_id
        tree = self.current_tree
        el = tree.elements.get(element_id) if tree and element_id else None
        self.props.set_target(self.project, tree, el)
        if el:
            self.list_view.select_element(element_id)

    def _on_list_select(self, element_id: str):
        self.selected_element_id = element_id
        tree = self.current_tree
        el = tree.elements.get(element_id) if tree else None
        self.props.set_target(self.project, tree, el)
        self.canvas.select_element(element_id)

    def _on_finding_click(self, item):
        el_id = item.data(Qt.UserRole)
        if el_id and self.current_tree and el_id in self.current_tree.elements:
            self.selected_element_id = el_id
            self.canvas.select_element(el_id)
            self.list_view.select_element(el_id)
            self.props.set_target(self.project, self.current_tree,
                                  self.current_tree.elements[el_id])

    # ============================================================= search
    def _on_search(self, text: str):
        text = text.strip().lower()
        tree = self.current_tree
        if not text or not tree:
            self.canvas.highlight(set())
            self.list_view.apply_filter(None)
            if tree:
                self._update_status()
            return
        matches = set()
        for el in tree.elements.values():
            for field in SEARCH_FIELDS:
                if text in str(getattr(el, field, "")).lower():
                    matches.add(el.id)
                    break
        other = 0
        for t in self.project.trees:
            if t is tree:
                continue
            for el in t.elements.values():
                if any(text in str(getattr(el, f, "")).lower()
                       for f in SEARCH_FIELDS):
                    other += 1
        self.canvas.highlight(matches)
        self.list_view.apply_filter(matches)
        extra = f" (+{other} in other trees)" if other else ""
        self.status_label.setText(
            f"Search '{text}': {len(matches)} match(es) in {tree.name}{extra}")

    # ============================================================== notes
    def _open_notes_for(self, element_id: str):
        self.notes_dock.show()
        self.notes_dock.raise_()
        self.notes.focus_element(element_id)

    def _link_note_to_selection(self):
        el = self._selected_element()
        if el is None:
            QMessageBox.information(
                self, "Link note",
                "Select an element in the flowchart or list first.")
            return
        self.notes.link_current_to(el.id, el.name)

    # ========================================================= file actions
    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        ret = QMessageBox.question(
            self, "Unsaved changes", "Save the project before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if ret == QMessageBox.StandardButton.Save:
            return self._save_project()
        return ret == QMessageBox.StandardButton.Discard

    def _new_project(self):
        if not self._confirm_discard():
            return
        self.project = Project("New Project")
        tree = self.project.new_tree("Power Tree 1")
        self.current_tree = tree
        self.selected_element_id = ""
        self.notes.set_project(self.project)
        self._rebuild_tree_list()
        self.dirty = False
        self.refresh(full=True)
        self.dirty = False
        self._update_title()

    def _open_project(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open project", "",
            f"PowerTree project (*{FILE_EXT});;All files (*)")
        if not path:
            return
        try:
            self.project = serialization.load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open project",
                                 f"Could not open project:\n{exc}")
            return
        self.current_tree = self.project.trees[0] if self.project.trees else None
        self.selected_element_id = ""
        self.notes.set_project(self.project)
        self._rebuild_tree_list()
        self.refresh(full=True)
        self.canvas.fit()
        self.dirty = False
        self._update_title()

    def _save_project(self, force_dialog: bool = False) -> bool:
        path = self.project.file_path
        if force_dialog or not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save project", f"{self.project.name}{FILE_EXT}",
                f"PowerTree project (*{FILE_EXT})")
            if not path:
                return False
            if not path.lower().endswith(FILE_EXT):
                path += FILE_EXT
        try:
            serialization.save_project(self.project, path)
        except Exception as exc:
            QMessageBox.critical(self, "Save project",
                                 f"Could not save project:\n{exc}")
            return False
        self.dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Saved {path}", 4000)
        return True

    # ============================================================= exports
    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF report", f"{self.project.name}_report.pdf",
            "PDF (*.pdf)")
        if not path:
            return
        try:
            export_pdf_report(self.project, path)
        except Exception as exc:
            QMessageBox.critical(self, "PDF export", f"Export failed:\n{exc}")
            return
        self.statusBar().showMessage(f"PDF report written: {path}", 6000)

    def _export_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Excel report", f"{self.project.name}_report.xlsm",
            "Excel macro-enabled (*.xlsm);;Excel workbook (*.xlsx)")
        if not path:
            return
        try:
            if path.lower().endswith(".xlsx"):
                written, msg = export_excel_xlsx(self.project, path), ""
            else:
                written, msg = export_excel_xlsm(self.project, path)
        except Exception as exc:
            QMessageBox.critical(self, "Excel export", f"Export failed:\n{exc}")
            return
        if msg and "unavailable" in msg:
            QMessageBox.information(self, "Excel export", msg)
        self.statusBar().showMessage(f"Excel report written: {written}", 6000)

    def _export_png(self):
        tree = self.current_tree
        if not tree:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export flowchart image", f"{tree.name}.png", "PNG (*.png)")
        if not path:
            return
        try:
            export_tree_png(tree, path, scale=3.0)
        except Exception as exc:
            QMessageBox.critical(self, "Image export", f"Export failed:\n{exc}")
            return
        self.statusBar().showMessage(f"HD flowchart image written: {path}", 6000)

    def _export_notes(self, fmt: str):
        ext = {"md": "Markdown (*.md)", "html": "HTML (*.html)",
               "pdf": "PDF (*.pdf)"}[fmt]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export notes", f"{self.project.name}_notes.{fmt}", ext)
        if not path:
            return
        fn = {"md": export_notes_markdown, "html": export_notes_html,
              "pdf": export_notes_pdf}[fmt]
        try:
            written = fn(self.project, path)
        except Exception as exc:
            QMessageBox.critical(self, "Notes export", f"Export failed:\n{exc}")
            return
        self.statusBar().showMessage(f"Notes exported: {written}", 6000)

    def _about(self):
        QMessageBox.about(
            self, "About PowerTree",
            "<b>PowerTree</b> — electronic circuit power tree analysis.<br>"
            "Bottom-up power budgeting with min/typ/max corners, margin "
            "analysis, flowchart + list views, PDF / Excel / image / notes "
            "exports.<br><br>Runs fully offline. Project format: "
            f"<code>{FILE_EXT}</code>")

    def closeEvent(self, event):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
