"""Property editor panel — edits the selected element, block or tree.

Every commit emits `changed`, which the main window turns into an automatic
recalculation + view refresh (the "auto-refresh" contract).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QDoubleSpinBox, QComboBox,
    QPlainTextEdit, QLabel, QScrollArea, QFrame, QPushButton, QHBoxLayout,
)

from ..model.elements import (
    Project, PowerTree, Element, Source, Converter, Load, SeriesElement,
    ElementKind, LimitType, LoadType,
)

TOPOLOGIES = ["buck", "boost", "buck-boost", "ldo", "isolated", "generic"]


class OptionalFloatEdit(QLineEdit):
    """Blank means 'not set' (None); otherwise a float."""

    committed = Signal()

    def __init__(self, value, placeholder="not set"):
        super().__init__()
        self.setPlaceholderText(placeholder)
        if value is not None:
            self.setText(f"{value:g}")
        self.editingFinished.connect(self.committed)

    def value(self):
        text = self.text().strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None


class PropertyPanel(QScrollArea):
    changed = Signal()          # model data changed -> recalc + refresh views
    structureChanged = Signal()  # parent/block layout changed -> full rebuild
    openNotesRequested = Signal(str)   # element id
    editDocsRequested = Signal(str)    # element id
    draftSaved = Signal()
    draftCancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.project: Project | None = None
        self.tree: PowerTree | None = None
        self.element: Element | None = None
        self.in_draft = False
        self.draft_parent_id: str | None = None
        self._body = QWidget()
        self.setWidget(self._body)
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._show_placeholder()

    # ------------------------------------------------------------------ util
    def _clear(self):
        def wipe(layout):
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
                elif item.layout() is not None:
                    wipe(item.layout())
                    item.layout().deleteLater()
        wipe(self._layout)

    def _show_placeholder(self):
        self._clear()
        lbl = QLabel("Select an element in the flowchart or list\n"
                     "to edit its properties.")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #98a3b8; padding: 24px;")
        self._layout.addWidget(lbl)
        self._layout.addStretch(1)

    def _spin(self, value, lo=-1e9, hi=1e9, decimals=6, suffix="", step=0.1):
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setDecimals(decimals)
        sb.setSingleStep(step)
        sb.setValue(value)
        if suffix:
            sb.setSuffix(f" {suffix}")
        sb.setKeyboardTracking(False)
        return sb

    def _text(self, value, setter, form, label):
        edit = QLineEdit(value or "")
        edit.editingFinished.connect(
            lambda e=edit: self._commit(setter, e.text()))
        form.addRow(label, edit)
        return edit

    def _commit(self, setter, value):
        setter(value)
        if not self.in_draft:       # drafts only touch the model on Save
            self.changed.emit()

    def _header(self, text, color="#e8ecf5"):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-weight: 700; font-size: 12px; color: {color};"
            "padding: 2px 0 4px 0; border-bottom: 1px solid #2c3650;")
        self._layout.addWidget(lbl)

    # ------------------------------------------------------------------- api
    def set_target(self, project: Project, tree: PowerTree | None,
                   element: Element | None):
        if self.in_draft:
            self.in_draft = False
            self.draft_parent_id = None
            self.draftCancelled.emit()
        self.project, self.tree, self.element = project, tree, element
        self._clear()
        if tree is None:
            self._show_placeholder()
            return
        if element is None:
            self._build_tree_form(tree)
        else:
            self._build_element_form(tree, element)
        self._layout.addStretch(1)

    def begin_draft(self, project: Project, tree: PowerTree,
                    element: Element, parent_id: str | None):
        """Show a not-yet-added element for editing; the caller adds it to the
        tree only when the user presses Save."""
        self.project, self.tree, self.element = project, tree, element
        self.in_draft = True
        self.draft_parent_id = parent_id
        self._clear()
        banner = QLabel(f"NEW {element.kind.upper()} — not added yet")
        banner.setStyleSheet(
            "background: #2c3a58; color: #ffffff; font-weight: 700;"
            "padding: 6px 10px; border-radius: 6px;")
        self._layout.addWidget(banner)
        if parent_id and parent_id in tree.elements:
            parent_lbl = QLabel(f"will attach under: "
                                f"{tree.elements[parent_id].name}")
            parent_lbl.setStyleSheet("color: #98a3b8; padding: 0 2px;")
            self._layout.addWidget(parent_lbl)
        row = QHBoxLayout()
        save = QPushButton("✔ Save — add to tree")
        save.setStyleSheet("background: #1d4ed8; font-weight: 600;")
        save.clicked.connect(self._save_draft)
        cancel = QPushButton("✕ Cancel")
        cancel.clicked.connect(self._cancel_draft)
        row.addWidget(save, 1)
        row.addWidget(cancel)
        self._layout.addLayout(row)
        self._build_element_form(tree, element)
        self._layout.addStretch(1)

    def _save_draft(self):
        self.in_draft = False
        self.draftSaved.emit()

    def _cancel_draft(self):
        self.in_draft = False
        self.draft_parent_id = None
        self.draftCancelled.emit()
        self.set_target(self.project, self.tree, None)

    # ------------------------------------------------------- tree properties
    def _build_tree_form(self, tree: PowerTree):
        self._header(f"Power tree — {tree.name}")
        form = QFormLayout()
        self._layout.addLayout(form)
        name = QLineEdit(tree.name)
        name.editingFinished.connect(
            lambda: self._commit(lambda v: setattr(tree, "name", v), name.text()))
        form.addRow("Name", name)
        desc = QPlainTextEdit(tree.description)
        desc.setMaximumHeight(70)
        desc.textChanged.connect(
            lambda: setattr(tree, "description", desc.toPlainText()))
        form.addRow("Description", desc)
        detail_combo = QComboBox()
        detail_combo.addItem("(inherit app setting)", "")
        for level in ("minimal", "standard", "exhaustive"):
            detail_combo.addItem(level, level)
        idx = detail_combo.findData(tree.detail_default)
        detail_combo.setCurrentIndex(max(idx, 0))
        detail_combo.setToolTip("Default card detail for every element in "
                                "this tree (elements can still override)")
        detail_combo.currentIndexChanged.connect(
            lambda _: self._commit(
                lambda x: setattr(tree, "detail_default", x),
                detail_combo.currentData() or ""))
        form.addRow("Card detail", detail_combo)

        if tree.blocks:
            self._header("Blocks")
            bform = QFormLayout()
            self._layout.addLayout(bform)
            for block in list(tree.blocks.values()):
                row = QHBoxLayout()
                bname = QLineEdit(block.name)
                bname.editingFinished.connect(
                    lambda b=block, e=bname:
                    self._commit(lambda v: setattr(b, "name", v), e.text()))
                row.addWidget(bname, 1)
                rm = QPushButton("Remove")
                rm.setFixedWidth(64)
                rm.clicked.connect(lambda _, b=block: self._remove_block(b))
                row.addWidget(rm)
                bform.addRow(f"{len(self.tree.block_members(block.id))} member(s)",
                             row)

    def _remove_block(self, block):
        self.tree.remove_block(block.id)
        self.structureChanged.emit()
        self.set_target(self.project, self.tree, None)

    # ---------------------------------------------------- element properties
    def _build_element_form(self, tree: PowerTree, el: Element):
        kind_names = {ElementKind.SOURCE: "Source", ElementKind.CONVERTER:
                      "Converter", ElementKind.LOAD: "Load",
                      ElementKind.SERIES: "Series element"}
        colors = {ElementKind.SOURCE: "#f59e0b", ElementKind.CONVERTER: "#3b82f6",
                  ElementKind.LOAD: "#10b981", ElementKind.SERIES: "#94a3b8"}
        self._header(kind_names.get(el.kind, "Element"),
                     colors.get(el.kind, "#e8ecf5"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self._layout.addLayout(form)

        self._text(el.name, lambda v: setattr(el, "name", v), form, "Name")

        # ---- electrical, per kind ----
        if isinstance(el, Source):
            for attr, label in (("v_min", "V min"), ("v_typ", "V typ"),
                                ("v_max", "V max")):
                sb = self._spin(getattr(el, attr), 0, 10000, 4, "V")
                sb.valueChanged.connect(
                    lambda v, a=attr: self._commit(
                        lambda x: setattr(el, a, x), v))
                form.addRow(label, sb)
            self._limit_rows(el, form, "Supply limit")
        elif isinstance(el, Converter):
            topo = QComboBox()
            topo.addItems(TOPOLOGIES)
            topo.setCurrentText(el.topology)
            topo.currentTextChanged.connect(
                lambda v: self._commit(lambda x: setattr(el, "topology", x), v))
            form.addRow("Topology", topo)
            eff = self._spin(el.efficiency_pct, 1, 100, 2, "%", 1.0)
            eff.setToolTip("Flat efficiency — used when no curve is entered "
                           "below")
            eff.valueChanged.connect(
                lambda v: self._commit(lambda x: setattr(el, "efficiency_pct", x), v))
            form.addRow("Efficiency", eff)
            curve = QLineEdit(", ".join(f"{i:g}:{e:g}"
                                        for i, e in (el.eff_points or [])))
            curve.setPlaceholderText("e.g. 0.1:85, 0.5:91, 1:93, 3:90")
            curve.setToolTip(
                "Efficiency-vs-load curve from the datasheet plot: "
                "Iout(A):eff(%) pairs, comma-separated. Linearly "
                "interpolated at the solved output current; blank = flat "
                "efficiency above.")
            def _commit_curve(edit=curve, ele=el):
                points = []
                try:
                    for chunk in edit.text().replace(";", ",").split(","):
                        chunk = chunk.strip()
                        if not chunk:
                            continue
                        i_s, e_s = chunk.split(":")
                        points.append([float(i_s), float(e_s)])
                except ValueError:
                    edit.setStyleSheet("border-color: #f43f5e;")
                    return
                edit.setStyleSheet("")
                self._commit(lambda x: setattr(ele, "eff_points", x),
                             sorted(points))
            curve.editingFinished.connect(_commit_curve)
            form.addRow("η curve (I:η)", curve)
            for attr, label in (("vout_min", "Vout min"), ("vout_typ", "Vout typ"),
                                ("vout_max", "Vout max")):
                sb = self._spin(getattr(el, attr), 0, 10000, 4, "V")
                sb.valueChanged.connect(
                    lambda v, a=attr: self._commit(lambda x: setattr(el, a, x), v))
                form.addRow(label, sb)
            iq = self._spin(el.quiescent_ma, 0, 1e6, 4, "mA", 0.1)
            iq.valueChanged.connect(
                lambda v: self._commit(lambda x: setattr(el, "quiescent_ma", x), v))
            form.addRow("Quiescent I", iq)
            self._limit_rows(el, form, "Output limit")
        elif isinstance(el, Load):
            lt = QComboBox()
            lt.addItems([LoadType.CURRENT, LoadType.POWER])
            lt.setCurrentText(el.load_type)
            lt.currentTextChanged.connect(
                lambda v: self._commit(lambda x: setattr(el, "load_type", x), v))
            form.addRow("Load type", lt)
            unit = "A" if el.load_type == LoadType.CURRENT else "W"
            val = self._spin(el.value_typ, 0, 1e6, 6, unit, 0.01)
            val.valueChanged.connect(
                lambda v: self._commit(lambda x: setattr(el, "value_typ", x), v))
            form.addRow("Value (typ)", val)
            vmax = OptionalFloatEdit(el.value_max, "same as typ")
            vmax.committed.connect(
                lambda: self._commit(
                    lambda x: setattr(el, "value_max", x), vmax.value()))
            form.addRow("Value (peak)", vmax)
            lo = OptionalFloatEdit(el.v_in_min, "no check")
            lo.committed.connect(
                lambda: self._commit(lambda x: setattr(el, "v_in_min", x), lo.value()))
            form.addRow("Allowed Vin min", lo)
            hi = OptionalFloatEdit(el.v_in_max, "no check")
            hi.committed.connect(
                lambda: self._commit(lambda x: setattr(el, "v_in_max", x), hi.value()))
            form.addRow("Allowed Vin max", hi)
        elif isinstance(el, SeriesElement):
            from ..model.elements import SeriesType
            st = QComboBox()
            st.addItems(list(SeriesType.ALL))
            st.setCurrentText(el.series_type)
            st.currentTextChanged.connect(
                lambda v: self._commit(lambda x: setattr(el, "series_type", x), v))
            form.addRow("Type", st)
            res = self._spin(el.resistance_ohm, 1e-6, 1e9, 6, "Ω", 0.001)
            res.setToolTip("DC resistance (DCR for ferrite beads / inductors) "
                           "— this is what the DC solver uses")
            res.valueChanged.connect(
                lambda v: self._commit(
                    lambda x: setattr(el, "resistance_ohm", x), v))
            form.addRow("Resistance", res)
            ind = self._spin(el.inductance_uh, 0, 1e9, 4, "µH", 0.1)
            ind.setToolTip("Informational — ignored by the DC solver, shown "
                           "on the card for AC/filtering awareness")
            ind.valueChanged.connect(
                lambda v: self._commit(
                    lambda x: setattr(el, "inductance_uh", x), v))
            form.addRow("Inductance", ind)
            self._text(el.rating, lambda v: setattr(el, "rating", v),
                       form, "Rating (text)")
            for attr, label, tip in (
                    ("i_max", "Current rating", "continuous current rating "
                     "(A) — margin analysis flags >90 % and breaches"),
                    ("p_max", "Dissipation rating", "power rating (W) — "
                     "checked against I²R loss"),
                    ("v_in_min", "Allowed Vin min", "input undervoltage check"),
                    ("v_in_max", "Allowed Vin max", "input overvoltage check")):
                opt = OptionalFloatEdit(getattr(el, attr), "no check")
                opt.setToolTip(tip)
                opt.committed.connect(
                    lambda a=attr, o=opt: self._commit(
                        lambda x: setattr(el, a, x), o.value()))
                form.addRow(label, opt)

        # ---- block assignment ----
        if el.kind != ElementKind.SOURCE or True:
            combo = QComboBox()
            combo.addItem("(no block)", None)
            for bid, block in tree.blocks.items():
                combo.addItem(block.name, bid)
            combo.addItem("+ New block…", "__new__")
            idx = combo.findData(el.block_id) if el.block_id else 0
            combo.setCurrentIndex(max(idx, 0))
            combo.currentIndexChanged.connect(
                lambda _: self._assign_block(el, combo))
            form.addRow("Block", combo)

        # ---- operating states (scenario overrides) ----
        from ..model.scenarios import SCENARIO_FIELDS, FIELD_LABELS
        fields = SCENARIO_FIELDS.get(el.kind, ())
        if self.project and self.project.scenarios and fields \
                and not self.in_draft:
            self._header("Operating states")
            hint = QLabel("Blank = inherit base value. Solve any state from "
                          "the toolbar State selector.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #98a3b8; font-size: 11px;")
            self._layout.addWidget(hint)
            for scenario in self.project.scenarios:
                sform = QFormLayout()
                sform.setLabelAlignment(Qt.AlignRight)
                title = QLabel(f"◈ {scenario}")
                title.setStyleSheet("font-weight: 600; color: #22d3ee;"
                                    "padding-top: 4px;")
                self._layout.addWidget(title)
                self._layout.addLayout(sform)
                overrides = el.scenario_overrides.setdefault(scenario, {}) \
                    if el.scenario_overrides is not None else {}
                for field_name in fields:
                    opt = OptionalFloatEdit(overrides.get(field_name),
                                            f"base: {getattr(el, field_name)}")
                    opt.committed.connect(
                        lambda s=scenario, f=field_name, o=opt:
                        self._set_override(el, s, f, o.value()))
                    sform.addRow(FIELD_LABELS.get(field_name, field_name), opt)

        # ---- per-element display detail (cascade: app -> tree -> element) --
        detail_combo = QComboBox()
        detail_combo.addItem("(inherit)", None)
        for level in ("minimal", "standard", "exhaustive"):
            detail_combo.addItem(level, level)
        idx = detail_combo.findData(el.display_detail)
        detail_combo.setCurrentIndex(max(idx, 0))
        detail_combo.setToolTip(
            "How much this card shows on the flowchart — overrides the "
            "tree/app default for just this element")
        detail_combo.currentIndexChanged.connect(
            lambda _: self._commit(
                lambda x: setattr(el, "display_detail", x),
                detail_combo.currentData()))
        form.addRow("Card detail", detail_combo)

        # ---- metadata ----
        self._header("Metadata")
        mform = QFormLayout()
        mform.setLabelAlignment(Qt.AlignRight)
        self._layout.addLayout(mform)
        self._text(el.signal_name, lambda v: setattr(el, "signal_name", v),
                   mform, "Signal name")
        self._text(el.refdes, lambda v: setattr(el, "refdes", v), mform, "RefDes")
        self._text(el.part_number, lambda v: setattr(el, "part_number", v),
                   mform, "Part number")
        self._text(el.pins, lambda v: setattr(el, "pins", v), mform, "Pin(s)")
        self._text(el.datasheet, lambda v: setattr(el, "datasheet", v),
                   mform, "Datasheet")
        desc = QPlainTextEdit(el.description)
        desc.setMaximumHeight(64)
        desc.textChanged.connect(
            lambda: setattr(el, "description", desc.toPlainText()))
        mform.addRow("Notes", desc)

        if not self.in_draft:
            linked = self.project.notes_for_element(el.id) if self.project \
                else []
            row = QHBoxLayout()
            edit_btn = QPushButton("📝 Edit documentation…")
            edit_btn.setToolTip(
                "Edit this element's markdown documentation (with image "
                "import) right here — it stays part of the central, "
                "searchable notes vault")
            edit_btn.clicked.connect(
                lambda: self.editDocsRequested.emit(el.id))
            row.addWidget(edit_btn, 1)
            open_btn = QPushButton(f"🗂 Vault ({len(linked)})")
            open_btn.setToolTip("Open the central Documentation Notes panel "
                                "focused on this element's notes")
            open_btn.clicked.connect(
                lambda: self.openNotesRequested.emit(el.id))
            row.addWidget(open_btn)
            self._layout.addLayout(row)

    def _set_override(self, el: Element, scenario: str, field_name: str,
                      value):
        if el.scenario_overrides is None:
            el.scenario_overrides = {}
        bucket = el.scenario_overrides.setdefault(scenario, {})
        if value is None:
            bucket.pop(field_name, None)
        else:
            bucket[field_name] = value
        self.changed.emit()

    def _limit_rows(self, el, form, label):
        combo = QComboBox()
        combo.addItems([LimitType.NONE, LimitType.CURRENT, LimitType.POWER])
        combo.setCurrentText(el.limit_type)
        combo.currentTextChanged.connect(
            lambda v: self._commit(lambda x: setattr(el, "limit_type", x), v))
        form.addRow(label, combo)
        sb = self._spin(el.limit_value, 0, 1e9, 4, "A / W", 0.1)
        sb.valueChanged.connect(
            lambda v: self._commit(lambda x: setattr(el, "limit_value", x), v))
        form.addRow("Limit value", sb)

    def _assign_block(self, el: Element, combo: QComboBox):
        data = combo.currentData()
        if data == "__new__":
            block = self.tree.add_block(f"Block {len(self.tree.blocks) + 1}")
            el.block_id = block.id
        else:
            el.block_id = data
        self.structureChanged.emit()
