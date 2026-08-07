"""PowerTree main window — wires model, canvas, list, properties, notes,
search, findings and every import/export path together.

Auto-refresh contract: any model mutation funnels through refresh(), which
re-solves the current tree bottom-up and repaints every view.
"""

from __future__ import annotations

import os
import time

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
from ..settings import AppSettings, DETAIL_LEVELS
from .canvas import PowerCanvas, Theme
from .listview import TreeListView
from .props import PropertyPanel
from .notes import NotesPanel
from . import layout as L

SEARCH_FIELDS = ("name", "signal_name", "refdes", "part_number", "pins",
                 "description")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = AppSettings()
        self.project: Project = build_sample_project()
        self.current_tree: PowerTree | None = self.project.trees[0] \
            if self.project.trees else None
        self.results: TreeResults | None = None
        self.selected_element_id: str = ""
        self.active_scenario: str | None = None
        self.dirty = False
        # snapshot-based undo/redo (bursts of edits within 1.2 s coalesce)
        self._undo_stack: list = []
        self._redo_stack: list = []
        self._last_snapshot = serialization.project_to_dict(self.project)
        self._last_snap_time = 0.0
        self._restoring = False

        self.setWindowTitle(APP_NAME)
        self.resize(1560, 940)
        self._build_central()
        self._build_docks()
        self._build_toolbar()
        self._build_menus()
        self._build_statusbar()
        self._apply_settings(initial=True)
        self._rebuild_tree_list()
        self.refresh(full=True)
        # crash-safety autosave every 3 minutes while dirty
        from PySide6.QtCore import QTimer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(180_000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()
        # first-run onboarding
        if not self.settings._qs.value("seen_quickstart", False, type=bool):
            self.settings._qs.setValue("seen_quickstart", True)
            QTimer.singleShot(
                700, lambda: self._show_quickstart(modal=False))

    def _autosave_path(self) -> str | None:
        return f"{self.project.file_path}.autosave" \
            if self.project.file_path else None

    def _autosave(self):
        path = self._autosave_path()
        if not path or not self.dirty:
            return
        try:
            payload = serialization.project_to_dict(self.project)
            import json
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            self.statusBar().showMessage("Autosaved (recovery copy)", 2000)
        except OSError:
            pass

    def _apply_settings(self, initial: bool = False):
        s = self.settings
        from ..model import calc
        calc.SI_DIGITS = max(3, min(6, int(s.get("si_digits"))))
        Theme.set_style(s.get("canvas_style"))
        self.canvas.setBackgroundBrush(Theme.bg)
        self.canvas.detail_default = s.get("detail_default")
        self.canvas.heat_mode = s.get("heat_mode")
        self.canvas.legend_visible = s.get("legend")
        self.heat_action.setChecked(s.get("heat_mode"))
        self.print_action.setChecked(s.get("canvas_style") == "print")
        self.legend_action.setChecked(s.get("legend"))
        if not initial:
            self.refresh(full=True)

    # ================================================================ layout
    def _build_central(self):
        self.tabs = QTabWidget()
        self.canvas = PowerCanvas()
        self.canvas.elementSelected.connect(self._on_canvas_select)
        self.canvas.collapseToggled.connect(self._on_collapse_toggle)
        self.canvas.blockExpandRequested.connect(self._toggle_block_collapsed)
        self.canvas.nodeMoved.connect(self._mark_dirty)
        self.canvas.contextRequested.connect(self._canvas_context_menu)
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
        self.props.editDocsRequested.connect(self._edit_docs_for)
        self.props.draftSaved.connect(self._commit_draft)
        self.props.draftCancelled.connect(lambda: None)
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
        self.findings.setContextMenuPolicy(Qt.CustomContextMenu)
        self.findings.customContextMenuRequested.connect(
            self._findings_context_menu)
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
        act("⌸ Template", "Add a device from the template library "
            "(Zynq, DDR3, PHYs, regulator blocks…)", self._add_from_template)
        tb.addSeparator()
        act("🗑 Delete", "Delete the selected element (with its subtree)",
            self._delete_element, QKeySequence.Delete)
        tb.addSeparator()

        tb.addWidget(QLabel(" State: "))
        self.state_combo = QComboBox()
        self.state_combo.setToolTip(
            "Operating state to solve: Base, or any named state with "
            "per-element overrides (Project → Manage states…)")
        self.state_combo.currentIndexChanged.connect(self._on_state_pick)
        tb.addWidget(self.state_combo)
        self._rebuild_state_combo()
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
        zoom_in = QAction(self)
        zoom_in.setShortcuts([QKeySequence("Ctrl+="), QKeySequence("Ctrl++")])
        zoom_in.triggered.connect(lambda: self.canvas.scale(1.2, 1.2))
        self.addAction(zoom_in)
        zoom_out = QAction(self)
        zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out.triggered.connect(
            lambda: self.canvas.scale(1 / 1.2, 1 / 1.2))
        self.addAction(zoom_out)
        act("▸ Collapse", "Collapse every converter / series branch",
            lambda: self._set_all_collapsed(True))
        act("▾ Expand", "Expand everything",
            lambda: self._set_all_collapsed(False))
        self.legend_action = QAction("◨ Legend", self)
        self.legend_action.setCheckable(True)
        self.legend_action.setChecked(True)
        self.legend_action.toggled.connect(self._on_legend)
        tb.addAction(self.legend_action)
        self.heat_action = QAction("🔥 Heat", self)
        self.heat_action.setCheckable(True)
        self.heat_action.setToolTip(
            "Tint every card by its power draw: blue = cold, red = hot")
        self.heat_action.toggled.connect(self._on_heat)
        tb.addAction(self.heat_action)
        self.print_action = QAction("🖨 Print style", self)
        self.print_action.setCheckable(True)
        self.print_action.setToolTip(
            "White, ink-friendly canvas — also used by image exports "
            "while active")
        self.print_action.toggled.connect(self._on_print_style)
        tb.addAction(self.print_action)
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
        self.recent_menu = m_file.addMenu("Open &recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        add(m_file, "&Save project", self._save_project, QKeySequence.Save)
        add(m_file, "Save project &as…", lambda: self._save_project(force_dialog=True),
            QKeySequence.SaveAs)
        m_file.addSeparator()
        m_export = m_file.addMenu("&Export")
        add(m_export, "PDF report (trees + margins + notes)…", self._export_pdf)
        add(m_export, "Shareable HTML report (single file)…",
            self._export_html)
        add(m_export, "Excel macro-enabled report (.xlsm)…", self._export_excel)
        add(m_export, "Flowchart image (HD PNG)…", self._export_png)
        add(m_export, "Solved tree table (CSV)…", self._export_csv)
        m_export.addSeparator()
        add(m_export, "Everything (bundle to folder)…", self._export_bundle)
        m_export.addSeparator()
        add(m_export, "Notes → Markdown…", lambda: self._export_notes("md"))
        add(m_export, "Notes → HTML…", lambda: self._export_notes("html"))
        add(m_export, "Notes → PDF…", lambda: self._export_notes("pdf"))
        m_file.addSeparator()
        add(m_file, "E&xit", self.close, "Alt+F4")

        m_edit = self.menuBar().addMenu("&Edit")
        add(m_edit, "&Undo", self._undo, QKeySequence.Undo)
        add(m_edit, "&Redo", self._redo, QKeySequence.Redo)
        m_edit.addSeparator()
        add(m_edit, "Copy flowchart as &image", self._copy_canvas_image,
            "Ctrl+Shift+C")
        add(m_edit, "Copy solved &table", self._copy_table,
            "Ctrl+Shift+T")
        add(m_edit, "Du&plicate element (with subtree)",
            self._duplicate_element, "Ctrl+D")
        m_edit.addSeparator()
        add(m_edit, "&Delete selected element", self._delete_element)

        m_project = self.menuBar().addMenu("&Project")
        add(m_project, "Add device from &template…", self._add_from_template,
            "Ctrl+T")
        add(m_project, "Global &nets…", self._show_nets, "Ctrl+G")
        add(m_project, "Project &properties…", self._project_properties)
        m_project.addSeparator()
        add(m_project, "&Validate project (all trees + states)…",
            self._validate_project, "Ctrl+Shift+V")
        add(m_project, "&Derating policy…", self._set_derating)
        add(m_project, "Manage operating &states…", self._manage_states)
        add(m_project, "&Materialize current state as new tree",
            self._materialize_state)

        m_view = self.menuBar().addMenu("&View")
        m_view.addAction(self.legend_action)
        m_view.addAction(self.heat_action)
        m_view.addAction(self.print_action)
        m_view.addSeparator()
        add(m_view, "Collapse all &blocks to summary nodes",
            lambda: self._set_all_blocks_collapsed(True))
        add(m_view, "Expand all bloc&ks",
            lambda: self._set_all_blocks_collapsed(False))
        m_view.addSeparator()
        for dock in (self.explorer_dock, self.props_dock, self.notes_dock,
                     self.findings_dock):
            m_view.addAction(dock.toggleViewAction())
        m_view.addSeparator()
        add(m_view, "&Settings…", self._open_settings, "Ctrl+,")

        m_help = self.menuBar().addMenu("&Help")
        add(m_help, "&Quick start", self._show_quickstart, "F1")
        add(m_help, "&User guide (docs)", self._open_user_guide)
        m_help.addSeparator()
        add(m_help, "About PowerTree", self._about)

    def _build_statusbar(self):
        self.status_label = QLabel("")
        self.statusBar().addWidget(self.status_label, 1)

    # ============================================================== refresh
    def refresh(self, full: bool = False):
        """Recalculate the current tree bottom-up and repaint every view."""
        self._mark_dirty()
        tree = self.current_tree
        if self.active_scenario and self.active_scenario not in \
                self.project.scenarios:
            self.active_scenario = None
            self._rebuild_state_combo()
        self.results = solve_tree(tree, self.active_scenario) if tree else None
        self.canvas.rebuild(tree, self.results, keep_view=not full)
        self.list_view.rebuild(tree, self.results)
        self._rebuild_findings()
        self._update_status()
        if self.props.in_draft:
            pass    # never clobber an in-progress draft form
        elif self.selected_element_id and tree and \
                self.selected_element_id in tree.elements:
            self.props.set_target(self.project, tree,
                                  tree.elements[self.selected_element_id])
        else:
            self.selected_element_id = ""
            self.props.set_target(self.project, tree, None)
        if self.search_box.text():
            self._on_search(self.search_box.text())

    def _rebuild_findings(self):
        from ..api import split_waived
        self.findings.clear()
        if not self.results:
            return
        icons = {"error": "⛔", "warn": "⚠️", "info": "ℹ️"}
        active, waived = split_waived(self.project, self.results.warnings)
        for w in active:
            item = QListWidgetItem(
                f"{icons.get(w.severity, '•')}  [{w.corner}]  {w.message}")
            item.setData(Qt.UserRole, w.element_id)
            item.setData(Qt.UserRole + 1, w.message)
            item.setData(Qt.UserRole + 2, False)
            self.findings.addItem(item)
        for w, reason in waived:
            item = QListWidgetItem(
                f"◌  [{w.corner}]  {w.message}   — WAIVED: {reason}")
            item.setData(Qt.UserRole, w.element_id)
            item.setData(Qt.UserRole + 1, w.message)
            item.setData(Qt.UserRole + 2, True)
            from PySide6.QtGui import QBrush, QColor
            item.setForeground(QBrush(QColor("#667085")))
            self.findings.addItem(item)
        title = "Findings — margin analysis"
        if self.results.warnings:
            errs = sum(1 for w in active if w.severity == "error")
            warns = sum(1 for w in active if w.severity == "warn")
            extra = f", {len(waived)} waived" if waived else ""
            title += f"  ({errs} errors, {warns} warnings{extra})"
        self.findings_dock.setWindowTitle(title)

    def _findings_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        from ..api import waive_finding, unwaive_finding
        item = self.findings.itemAt(pos)
        if item is None:
            return
        element_id = item.data(Qt.UserRole)
        message = item.data(Qt.UserRole + 1)
        is_waived = item.data(Qt.UserRole + 2)
        menu = QMenu(self)
        if is_waived:
            menu.addAction(
                "Remove waiver (finding counts again)",
                lambda: (unwaive_finding(self.project, element_id, message),
                         self.refresh()))
        else:
            def do_waive():
                reason, ok = QInputDialog.getText(
                    self, "Waive finding",
                    "Engineering justification (kept as audit trail in "
                    "reports):")
                if ok and reason.strip():
                    waive_finding(self.project, element_id, message, reason)
                    self.refresh()
            menu.addAction("Waive with justification…", do_waive)
        menu.exec(self.findings.mapToGlobal(pos))

    def _update_status(self):
        tree = self.current_tree
        if not tree or not tree.source or not self.results:
            self.status_label.setText("Add a source to start building the tree.")
            return
        src = tree.source
        typ = self.results.get(src.id, "typ")
        mx = self.results.get(src.id, "max")
        mn = self.results.get(src.id, "min")
        from ..api import split_waived
        active, waived = split_waived(self.project, self.results.warnings)
        errs = sum(1 for w in active if w.severity == "error")
        warns = sum(1 for w in active if w.severity == "warn")
        health = "✅ all margins healthy" if not (errs or warns) else \
            f"⛔ {errs} violations · ⚠️ {warns} low margins"
        if waived:
            health += f" · ◌ {len(waived)} waived"
        state = f" · state: ◈ {self.active_scenario}" \
            if self.active_scenario else ""
        from ..api import tree_metrics
        metrics = tree_metrics(tree, self.results)
        eff = f" · η {metrics['efficiency_pct']:g} % · " \
              f"loss {fmt_si(metrics['p_loss_typ'], 'W')}" \
            if metrics["efficiency_pct"] is not None else ""
        self.status_label.setText(
            f"{tree.name}{state} — source power: {fmt_si(mn.p_out, 'W')} min / "
            f"{fmt_si(typ.p_out, 'W')} typ / {fmt_si(mx.p_out, 'W')} max"
            f"{eff} · {len(tree.elements)} elements · {health}")

    def _mark_dirty(self):
        self.dirty = True
        self._update_title()
        self._capture_snapshot()

    # ------------------------------------------------------------ undo/redo
    def _capture_snapshot(self):
        if self._restoring:
            return
        snap = serialization.project_to_dict(self.project)
        if snap == self._last_snapshot:
            return
        now = time.monotonic()
        # push the pre-change state once per edit burst
        if now - self._last_snap_time > 1.2 or not self._undo_stack:
            self._undo_stack.append(self._last_snapshot)
            del self._undo_stack[:-50]
            self._redo_stack.clear()
        self._last_snapshot = snap
        self._last_snap_time = now

    def _restore_snapshot(self, snap: dict):
        self._restoring = True
        try:
            path = self.project.file_path
            current_tree_id = self.current_tree.id if self.current_tree \
                else None
            self.project = serialization.project_from_dict(snap)
            self.project.file_path = path
            self.current_tree = self.project.tree_by_id(current_tree_id) \
                or (self.project.trees[0] if self.project.trees else None)
            self.selected_element_id = ""
            self._last_snapshot = snap
            self.notes.set_project(self.project)
            self._rebuild_state_combo()
            self._rebuild_tree_list()
            self.refresh(full=True)
        finally:
            self._restoring = False

    def _undo(self):
        if not self._undo_stack:
            self.statusBar().showMessage("Nothing to undo", 2500)
            return
        self._redo_stack.append(serialization.project_to_dict(self.project))
        self._restore_snapshot(self._undo_stack.pop())
        self.statusBar().showMessage(
            f"Undo ({len(self._undo_stack)} steps left)", 2500)

    def _redo(self):
        if not self._redo_stack:
            self.statusBar().showMessage("Nothing to redo", 2500)
            return
        self._undo_stack.append(serialization.project_to_dict(self.project))
        self._restore_snapshot(self._redo_stack.pop())
        self.statusBar().showMessage("Redo", 2500)

    def _reset_undo(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._last_snapshot = serialization.project_to_dict(self.project)

    def _update_title(self):
        from .. import __version__
        star = " •" if self.dirty else ""
        path = f" — {os.path.basename(self.project.file_path)}" \
            if self.project.file_path else f" — {self.project.name}"
        self.setWindowTitle(f"{APP_NAME} {__version__}{path}{star}")

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
        """Open a DRAFT in the properties panel — the element is only added
        to the tree when the user presses Save."""
        tree = self.current_tree
        if tree is None:
            QMessageBox.information(self, "Add element",
                                    "Create a power tree first (＋ Tree).")
            return
        classes = {ElementKind.SOURCE: Source, ElementKind.CONVERTER: Converter,
                   ElementKind.LOAD: Load, ElementKind.SERIES: SeriesElement}
        parent = None
        if kind == ElementKind.SOURCE:
            if tree.source is not None:
                QMessageBox.warning(
                    self, "Add source",
                    "This tree already has its source — a power tree has "
                    "exactly one.")
                return
        else:
            parent = self._selected_element()
            if parent is not None and parent.kind == ElementKind.LOAD:
                parent = tree.parent_of(parent)
            if parent is None and tree.source is not None:
                parent = tree.source
            if parent is None:
                QMessageBox.information(
                    self, "Add element",
                    "Start the tree with a ⊕ Source — every power tree has "
                    "exactly one.")
                return
        names = {ElementKind.SOURCE: "New Source",
                 ElementKind.CONVERTER: "New Converter",
                 ElementKind.LOAD: "New Load",
                 ElementKind.SERIES: "New Series R"}
        draft = classes[kind](name=names[kind])
        self.props_dock.show()
        self.props_dock.raise_()
        self.props.begin_draft(self.project, tree, draft,
                               parent.id if parent else None)
        self.statusBar().showMessage(
            "Fill in the new element, then press Save in the Properties "
            "panel to add it (or Cancel).", 6000)

    def _commit_draft(self):
        tree = self.tree_for_draft = self.current_tree
        el = self.props.element
        parent_id = self.props.draft_parent_id
        if tree is None or el is None:
            return
        try:
            tree.add_element(el, parent_id=parent_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Add element", str(exc))
            return
        self.selected_element_id = el.id
        self._rebuild_tree_list()
        self.refresh(full=True)
        self.canvas.select_element(el.id)
        self.statusBar().showMessage(f"Added '{el.name}'", 4000)

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

    def _add_from_template(self):
        tree = self.current_tree
        if tree is None or tree.source is None:
            QMessageBox.information(
                self, "Add from template",
                "Create a tree with a source first — templates attach to "
                "existing rails.")
            return
        from .template_dialog import TemplateDialog
        dlg = TemplateDialog(tree, self)
        if dlg.exec() and dlg.created:
            self.selected_element_id = dlg.created[0].id
            self._rebuild_tree_list()
            self.refresh(full=True)
            self.canvas.select_element(self.selected_element_id)
            self.statusBar().showMessage(
                f"Added {len(dlg.created)} elements from template", 5000)

    def _show_nets(self):
        from .nets_dialog import NetsDialog
        NetsDialog(self.project, self).exec()

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
        self.settings.set("legend", checked)
        self.canvas.viewport().update()

    def _on_heat(self, checked: bool):
        self.canvas.heat_mode = checked
        self.settings.set("heat_mode", checked)
        self.refresh()

    def _on_print_style(self, checked: bool):
        style = "print" if checked else "dark"
        Theme.set_style(style)
        self.settings.set("canvas_style", style)
        self.canvas.setBackgroundBrush(Theme.bg)
        self.refresh(full=True)

    def _open_settings(self):
        from .settings_dialog import SettingsDialog
        if SettingsDialog(self.settings, self).exec():
            self._apply_settings()

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

    # ============================================================= states
    def _rebuild_state_combo(self):
        self.state_combo.blockSignals(True)
        self.state_combo.clear()
        self.state_combo.addItem("Base", None)
        for s in self.project.scenarios:
            self.state_combo.addItem(f"◈ {s}", s)
        idx = self.state_combo.findData(self.active_scenario)
        self.state_combo.setCurrentIndex(max(idx, 0))
        self.state_combo.blockSignals(False)

    def _on_state_pick(self, _idx: int):
        self.active_scenario = self.state_combo.currentData()
        self.refresh()
        label = self.active_scenario or "Base"
        self.statusBar().showMessage(f"Solving state: {label}", 3000)

    def _manage_states(self):
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
            QDialogButtonBox)
        from ..model.scenarios import rename_scenario, delete_scenario
        dlg = QDialog(self)
        dlg.setWindowTitle("Operating states")
        lay = QVBoxLayout(dlg)
        info = QLabel(
            "States let elements override values per operating mode (sleep "
            "current, boost efficiency, battery sag…). Edit overrides in an "
            "element's Properties under 'Operating states'.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #98a3b8;")
        lay.addWidget(info)
        lst = QListWidget()
        lst.addItems(self.project.scenarios)
        lay.addWidget(lst, 1)
        row = QHBoxLayout()

        def add_state():
            name, ok = QInputDialog.getText(dlg, "New state",
                                            "State name (e.g. 'Low Power'):")
            if ok and name and name not in self.project.scenarios:
                self.project.scenarios.append(name)
                lst.addItem(name)

        def rename_state():
            item = lst.currentItem()
            if not item:
                return
            name, ok = QInputDialog.getText(dlg, "Rename state", "New name:",
                                            text=item.text())
            if ok and name and name != item.text():
                rename_scenario(self.project, item.text(), name)
                item.setText(name)

        def delete_state():
            item = lst.currentItem()
            if not item:
                return
            if QMessageBox.question(
                    dlg, "Delete state",
                    f"Delete state '{item.text()}' and every element "
                    "override stored for it?") == \
                    QMessageBox.StandardButton.Yes:
                delete_scenario(self.project, item.text())
                lst.takeItem(lst.row(item))

        for text, fn in (("＋ Add", add_state), ("Rename", rename_state),
                         ("✕ Delete", delete_state)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.clicked.connect(dlg.accept)
        lay.addWidget(buttons)
        dlg.exec()
        self._rebuild_state_combo()
        self.refresh()

    def _materialize_state(self):
        from ..model.scenarios import materialize_scenario
        if not self.active_scenario:
            QMessageBox.information(
                self, "Materialize state",
                "Select a state (not Base) in the toolbar first — the "
                "current state is baked into a new standalone tree.")
            return
        tree = self.current_tree
        if tree is None:
            return
        baked = materialize_scenario(self.project, tree, self.active_scenario)
        self.current_tree = baked
        self.active_scenario = None
        self._rebuild_state_combo()
        self._rebuild_tree_list()
        self.refresh(full=True)
        self.canvas.fit()
        self.statusBar().showMessage(
            f"Created '{baked.name}' with the state baked in", 6000)

    # ============================================================== notes
    def _edit_docs_for(self, element_id: str):
        tree = self.current_tree
        el = tree.elements.get(element_id) if tree else None
        if el is None:
            return
        from .note_edit_dialog import NoteEditDialog
        dlg = NoteEditDialog(self.project, el, self)
        dlg.exec()
        self.notes.rebuild()
        self._mark_dirty()
        if not self.props.in_draft:
            self.props.set_target(self.project, tree, el)

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

    def _toggle_block_collapsed(self, block_id: str, collapsed=None):
        tree = self.current_tree
        block = tree.blocks.get(block_id) if tree else None
        if block is None:
            return
        block.collapsed = (not block.collapsed) if collapsed is None \
            else collapsed
        self.refresh(full=True)
        state = "collapsed to summary node" if block.collapsed else "expanded"
        self.statusBar().showMessage(f"Block '{block.name}' {state}", 4000)

    def _set_all_blocks_collapsed(self, collapsed: bool):
        tree = self.current_tree
        if not tree:
            return
        for block in tree.blocks.values():
            block.collapsed = collapsed
        self.refresh(full=True)
        self.canvas.fit()

    def _add_view_settings_menu(self, menu):
        """'View settings' submenu — reachable from any right-click."""
        sub = menu.addMenu("👁 View settings")
        sub.addAction(self.legend_action)
        sub.addAction(self.heat_action)
        sub.addAction(self.print_action)
        sub.addSeparator()
        lay_menu = sub.addMenu("Layout")
        for i, label in enumerate(["Top-down", "Left-right", "Custom (drag)"]):
            act = lay_menu.addAction(
                label, lambda idx=i: self.orient_combo.setCurrentIndex(idx))
            act.setCheckable(True)
            act.setChecked(self.orient_combo.currentIndex() == i)
        detail_menu = sub.addMenu("Card detail (app default)")
        current = self.settings.get("detail_default")
        for level in DETAIL_LEVELS:
            act = detail_menu.addAction(
                level, lambda lv=level: self._set_app_detail(lv))
            act.setCheckable(True)
            act.setChecked(current == level)
        sub.addSeparator()
        sub.addAction("Collapse all blocks",
                      lambda: self._set_all_blocks_collapsed(True))
        sub.addAction("Expand all blocks",
                      lambda: self._set_all_blocks_collapsed(False))
        sub.addSeparator()
        sub.addAction("All settings… (Ctrl+,)", self._open_settings)
        return sub

    def _set_app_detail(self, level: str):
        self.settings.set("detail_default", level)
        self._apply_settings()

    def _build_canvas_menu(self, rid: str):
        """Context menu for a canvas right-click: item-specific actions when
        over an element or a collapsed-block node, view/general actions on
        the background — View settings are available everywhere."""
        from PySide6.QtWidgets import QMenu
        tree = self.current_tree
        if tree is None:
            return None
        menu = QMenu(self)

        if rid.startswith("blk:"):
            block = tree.blocks.get(rid[4:])
            if block is not None:
                menu.addAction(f"⤢ Expand block '{block.name}'",
                               lambda: self._toggle_block_collapsed(block.id))

                def rename():
                    name, ok = QInputDialog.getText(
                        self, "Rename block", "Name:", text=block.name)
                    if ok and name:
                        block.name = name
                        self.refresh(full=True)
                menu.addAction("Rename block…", rename)
                menu.addSeparator()
            self._add_view_settings_menu(menu)
            return menu

        el = tree.elements.get(rid) if rid else None
        if el is None:
            if tree.source is None:
                menu.addAction("⊕ Add source…",
                               lambda: self._add_element(ElementKind.SOURCE))
            menu.addAction("⌸ Add device from template…",
                           self._add_from_template)
            menu.addAction("⛶ Fit view", self.canvas.fit)
            menu.addSeparator()
            self._add_view_settings_menu(menu)
            return menu

        self.selected_element_id = el.id
        if tree.can_parent(el):
            menu.addAction("⊞ Add converter under this",
                           lambda: self._add_element(ElementKind.CONVERTER))
            menu.addAction("◎ Add load under this",
                           lambda: self._add_element(ElementKind.LOAD))
            menu.addAction("≡ Add series element under this",
                           lambda: self._add_element(ElementKind.SERIES))
            menu.addSeparator()
        if el.kind != ElementKind.SOURCE:
            menu.addAction("Duplicate (with subtree)",
                           self._duplicate_element)
        if tree.children_of(el.id):
            label = "Expand" if el.collapsed else "Collapse"
            menu.addAction(f"{label} branch",
                           lambda: self._on_collapse_toggle(el.id))
        if el.block_id and el.block_id in tree.blocks:
            block = tree.blocks[el.block_id]
            menu.addAction(
                f"▣ Collapse block '{block.name}' to summary node",
                lambda: self._toggle_block_collapsed(block.id, True))
        # item-specific display settings
        item_menu = menu.addMenu("⚙ Item settings")
        detail_menu = item_menu.addMenu("Card detail")
        for value, label in [(None, "(inherit)"), ("minimal", "minimal"),
                             ("standard", "standard"),
                             ("exhaustive", "exhaustive")]:
            act = detail_menu.addAction(
                label, lambda v=value: (setattr(el, "display_detail", v),
                                        self.refresh(full=True)))
            act.setCheckable(True)
            act.setChecked(el.display_detail == value)
        menu.addSeparator()
        menu.addAction("📝 Edit documentation…",
                       lambda: self._edit_docs_for(el.id))
        menu.addAction("🗑 Delete…", self._delete_element)
        menu.addSeparator()
        self._add_view_settings_menu(menu)
        return menu

    def _canvas_context_menu(self, rid: str, global_pos):
        menu = self._build_canvas_menu(rid)
        if menu is not None:
            menu.exec(global_pos)

    def _duplicate_element(self):
        el = self._selected_element()
        tree = self.current_tree
        if el is None or tree is None:
            self.statusBar().showMessage("Select an element to duplicate",
                                         3000)
            return
        try:
            dup = tree.duplicate_subtree(el.id)
        except ValueError as exc:
            QMessageBox.warning(self, "Duplicate", str(exc))
            return
        self.selected_element_id = dup.id
        self.refresh(full=True)
        self.canvas.select_element(dup.id)
        self.statusBar().showMessage(f"Duplicated as '{dup.name}'", 4000)

    def _project_properties(self):
        from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                                       QPlainTextEdit, QDialogButtonBox)
        dlg = QDialog(self)
        dlg.setWindowTitle("Project properties")
        dlg.setMinimumWidth(420)
        form = QFormLayout(dlg)
        name = QLineEdit(self.project.name)
        form.addRow("Project name", name)
        author = QLineEdit(self.project.author)
        author.setToolTip("Shown on report title pages")
        form.addRow("Author / team", author)
        desc = QPlainTextEdit(self.project.description)
        desc.setMaximumHeight(90)
        form.addRow("Description", desc)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec():
            self.project.name = name.text().strip() or self.project.name
            self.project.author = author.text().strip()
            self.project.description = desc.toPlainText()
            self._mark_dirty()
            self._update_title()

    def _validate_project(self):
        """CLI `validate` parity in the GUI: every tree, Base + every state,
        net conflicts and the derating policy, in one dialog."""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTreeWidget,
                                       QTreeWidgetItem, QDialogButtonBox)
        from ..api import validate
        result = validate(self.project)
        dlg = QDialog(self)
        dlg.setWindowTitle("Project validation")
        dlg.resize(860, 480)
        lay = QVBoxLayout(dlg)
        verdict = QLabel(
            f"{'✅ PASS' if result['ok'] else '⛔ FAIL'} — "
            f"{result['errors']} error(s), {result['warnings']} warning(s) "
            f"across {len(self.project.trees)} tree(s), Base + "
            f"{len(self.project.scenarios)} state(s), nets and the "
            f"{self.project.derating_pct:g} % derating policy.")
        verdict.setStyleSheet(
            f"font-weight: 700; color: "
            f"{'#10b981' if result['ok'] else '#f43f5e'}; font-size: 13px;")
        lay.addWidget(verdict)
        table = QTreeWidget()
        table.setColumnCount(5)
        table.setHeaderLabels(["Severity", "Tree", "State", "Element",
                               "Message"])
        table.setRootIsDecorated(False)
        table.setAlternatingRowColors(True)
        for i, w in enumerate([76, 130, 90, 150, 380]):
            table.setColumnWidth(i, w)
        from PySide6.QtGui import QBrush, QColor
        for f in result["findings"]:
            sev = "WAIVED" if f.get("waived") else f["severity"].upper()
            item = QTreeWidgetItem(table, [
                sev, f["tree"] or "project",
                f.get("state", "Base"), f["element"] or "—", f["message"]])
            if f.get("waived"):
                color = QColor("#667085")
            else:
                color = QColor("#f43f5e") if f["severity"] == "error" \
                    else QColor("#fbbf24")
            item.setForeground(0, QBrush(color))
            item.setData(0, Qt.UserRole, (f["tree"], f["element"]))

        def jump(item, _col):
            tree_name, el_name = item.data(0, Qt.UserRole) or (None, None)
            if not tree_name or not el_name:
                return
            from .. import api as _api
            try:
                t = _api.find_tree(self.project, tree_name)
                el = _api.find_element(t, el_name)
            except ValueError:
                return
            dlg.accept()
            self.current_tree = t
            self._rebuild_tree_list()
            self.selected_element_id = el.id
            self.refresh(full=True)
            self.canvas.select_element(el.id)

        table.itemDoubleClicked.connect(jump)
        hint = QLabel("Double-click a finding to jump to its element.")
        hint.setStyleSheet("color: #98a3b8; font-size: 11px;")
        lay.addWidget(table, 1)
        lay.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.clicked.connect(dlg.accept)
        lay.addWidget(buttons)
        dlg.exec()

    def _set_derating(self):
        value, ok = QInputDialog.getDouble(
            self, "Derating policy",
            "Flag rails loaded above this % of their limit\n"
            "(industry practice ≈ 80; 0 disables the check):",
            self.project.derating_pct, 0.0, 100.0, 1)
        if ok:
            self.project.derating_pct = value
            self._mark_dirty()
            self.statusBar().showMessage(
                f"Derating policy: {value:g} % (checked by validate/reports)",
                5000)

    def _fill_recent_menu(self):
        self.recent_menu.clear()
        recent = [p for p in self.settings.recent_files() if os.path.exists(p)]
        if not recent:
            a = QAction("(no recent projects)", self)
            a.setEnabled(False)
            self.recent_menu.addAction(a)
            return
        for path in recent:
            a = QAction(os.path.basename(path), self)
            a.setToolTip(path)
            a.triggered.connect(
                lambda _=False, p=path: self._open_project_path(p))
            self.recent_menu.addAction(a)

    def _open_project_path(self, path: str):
        if not self._confirm_discard():
            return
        load_path = path
        autosave = f"{path}.autosave"
        if os.path.exists(autosave) and os.path.exists(path) and \
                os.path.getmtime(autosave) > os.path.getmtime(path):
            if QMessageBox.question(
                    self, "Recover autosave",
                    "A newer autosaved recovery copy of this project exists "
                    "(the app may have closed unexpectedly). Load the "
                    "recovered version instead?") == \
                    QMessageBox.StandardButton.Yes:
                load_path = autosave
        try:
            self.project = serialization.load_project(load_path)
            self.project.file_path = path
        except Exception as exc:
            QMessageBox.critical(self, "Open project",
                                 f"Could not open project:\n{exc}")
            return
        self.settings.push_recent(path)
        self.current_tree = self.project.trees[0] if self.project.trees \
            else None
        self.selected_element_id = ""
        self.active_scenario = None
        self._rebuild_state_combo()
        self.notes.set_project(self.project)
        self._rebuild_tree_list()
        self.refresh(full=True)
        self.canvas.fit()
        self._reset_undo()
        self.dirty = False
        self._update_title()

    # ============================================================ clipboard
    def _copy_canvas_image(self):
        """Copy the current tree's flowchart to the clipboard — paste
        straight into slides, mails or wikis."""
        tree = self.current_tree
        if not tree or not self.results:
            return
        from .canvas import render_tree_image
        img = render_tree_image(
            tree, self.results, scale=2.0,
            detail_default=self.settings.get("detail_default"),
            heat=self.canvas.heat_mode)
        QApplication.clipboard().setImage(img)
        self.statusBar().showMessage(
            "Flowchart image copied — paste into slides / mail / wiki", 4000)

    def _copy_table(self):
        """Copy the solved hierarchy as a tab-separated table (Excel-ready)."""
        tree = self.current_tree
        if not tree or not self.results or not tree.source:
            return
        r = self.results
        p_src = r.get(tree.source.id, "typ").p_out
        lines = ["\t".join(["Element", "Type", "RefDes", "Signal", "Block",
                            "V in", "I in", "P in", "% of tree", "P out",
                            "Loss", "P in (max)", "Status"])]

        def emit(el, depth):
            typ = r.get(el.id, "typ")
            mx = r.get(el.id, "max")
            block = tree.blocks.get(el.block_id) if el.block_id else None
            warns = r.warnings_for(el.id)
            status = "OK" if not warns else (
                "VIOLATION" if r.worst_severity(el.id) == "error"
                else "LOW MARGIN")
            pct = f"{typ.p_in / p_src * 100:.1f}%" if p_src > 1e-12 else ""
            lines.append("\t".join([
                ("  " * depth) + el.name, el.kind, el.refdes, el.signal_name,
                block.name if block else "",
                fmt_si(typ.v_in, "V"), fmt_si(typ.i_in, "A"),
                fmt_si(typ.p_in, "W"), pct, fmt_si(typ.p_out, "W"),
                fmt_si(typ.p_loss, "W"), fmt_si(mx.p_in, "W"), status]))
            for child in tree.children_of(el.id):
                emit(child, depth + 1)

        emit(tree.source, 0)
        QApplication.clipboard().setText("\n".join(lines))
        self.statusBar().showMessage(
            f"Copied {len(lines) - 1} rows as a table — paste into Excel",
            4000)

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
        self.active_scenario = None
        self._rebuild_state_combo()
        self.notes.set_project(self.project)
        self._rebuild_tree_list()
        self.dirty = False
        self.refresh(full=True)
        self._reset_undo()
        self.dirty = False
        self._update_title()

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open project", "",
            f"PowerTree project (*{FILE_EXT});;All files (*)")
        if path:
            self._open_project_path(path)

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
        self.settings.push_recent(path)
        autosave = self._autosave_path()
        if autosave and os.path.exists(autosave):
            try:
                os.remove(autosave)     # clean save supersedes recovery copy
            except OSError:
                pass
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
            export_pdf_report(
                self.project, path,
                include_notes=self.settings.get("pdf_include_notes"),
                include_images=self.settings.get("pdf_include_images"),
                image_style=Theme.style)
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
            export_tree_png(tree, path, scale=self.settings.get("png_scale"),
                            style=Theme.style,
                            detail_default=self.settings.get("detail_default"),
                            heat=self.canvas.heat_mode)
        except Exception as exc:
            QMessageBox.critical(self, "Image export", f"Export failed:\n{exc}")
            return
        self.statusBar().showMessage(f"HD flowchart image written: {path}", 6000)

    def _export_html(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export shareable HTML report",
            f"{self.project.name}_report.html", "HTML (*.html)")
        if not path:
            return
        from ..export.html_report import export_html_report
        try:
            export_html_report(self.project, path, image_style=Theme.style)
        except Exception as exc:
            QMessageBox.critical(self, "HTML export", f"Export failed:\n{exc}")
            return
        self.statusBar().showMessage(
            f"Shareable HTML report written: {path} — one file, opens in any "
            "browser", 6000)

    def _export_bundle(self):
        out_dir = QFileDialog.getExistingDirectory(
            self, "Export everything (PDF + HTML + Excel + CSV + PNGs) into…")
        if not out_dir:
            return
        from ..api import export_bundle
        try:
            written = export_bundle(self.project, out_dir, style=Theme.style)
        except Exception as exc:
            QMessageBox.critical(self, "Bundle export",
                                 f"Export failed:\n{exc}")
            return
        self.statusBar().showMessage(
            f"Bundle written: {len(written)} files in {out_dir}", 8000)
        os.startfile(out_dir)

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export solved table (CSV)",
            f"{self.project.name}_table.csv", "CSV (*.csv)")
        if not path:
            return
        from ..api import export_csv
        try:
            export_csv(self.project, path)
        except Exception as exc:
            QMessageBox.critical(self, "CSV export", f"Export failed:\n{exc}")
            return
        self.statusBar().showMessage(f"CSV table written: {path}", 6000)

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

    def _docs_dir(self) -> str:
        import sys
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
        return os.path.join(base, "docs")

    def _show_quickstart(self, modal: bool = True):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, \
            QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Quick start")
        dlg.resize(720, 560)
        lay = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        path = os.path.join(self._docs_dir(), "QUICKSTART.md")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                browser.setMarkdown(fh.read())
        else:
            browser.setMarkdown(
                "# Quick start\n\n1. **＋ Tree**, then **⊕ Source** — fill "
                "the form, press **Save**.\n2. Add converters / series "
                "elements / loads under it (drafts save the same way), or "
                "**Ctrl+T** for whole-device templates.\n3. Loads carry an "
                "allowed Vin window — violations appear as red badges and in "
                "**Findings**.\n4. States: Project menu. Nets: **Ctrl+G**. "
                "Search: **Ctrl+F**.\n5. Export PDF / Excel / PNG / notes "
                "from the File menu.")
        lay.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.clicked.connect(dlg.accept)
        lay.addWidget(buttons)
        if modal:
            dlg.exec()
        else:               # first-run welcome: never block startup
            dlg.setAttribute(Qt.WA_DeleteOnClose)
            dlg.show()

    def _open_user_guide(self):
        path = os.path.join(self._docs_dir(), "USER_GUIDE.md")
        if os.path.exists(path):
            os.startfile(path)      # noqa: S606 — local file, user-initiated
        else:
            QMessageBox.information(
                self, "User guide",
                "docs/USER_GUIDE.md was not found next to the application.")

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
