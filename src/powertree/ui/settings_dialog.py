"""Application settings dialog (persisted via QSettings).

App-level defaults only — trees and individual elements can override display
detail from their own property forms (the cascade is app → tree → element)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QCheckBox, QDoubleSpinBox,
    QDialogButtonBox, QLabel,
)

from ..settings import AppSettings, DETAIL_LEVELS


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        note = QLabel("Display detail cascades: app default → per-tree "
                      "(tree properties) → per-element (element properties).")
        note.setWordWrap(True)
        note.setStyleSheet("color: #98a3b8;")
        form.addRow(note)

        self.style_combo = QComboBox()
        self.style_combo.addItem("Dark (screen)", "dark")
        self.style_combo.addItem("Print (white, ink-friendly)", "print")
        self.style_combo.setCurrentIndex(
            0 if settings.get("canvas_style") == "dark" else 1)
        form.addRow("Canvas style", self.style_combo)

        self.detail_combo = QComboBox()
        self.detail_combo.addItems(list(DETAIL_LEVELS))
        self.detail_combo.setCurrentText(settings.get("detail_default"))
        self.detail_combo.setToolTip(
            "How much each card shows: minimal (power only), standard, "
            "exhaustive (corners, ratings, part numbers, pins, states)")
        form.addRow("Card detail (default)", self.detail_combo)

        self.heat_check = QCheckBox("Tint cards by power draw (cold → hot)")
        self.heat_check.setChecked(settings.get("heat_mode"))
        form.addRow("Heat map", self.heat_check)

        self.legend_check = QCheckBox("Show legend overlay")
        self.legend_check.setChecked(settings.get("legend"))
        form.addRow("Legend", self.legend_check)

        self.minimap_check = QCheckBox("Show navigation minimap")
        self.minimap_check.setChecked(settings.get("minimap"))
        form.addRow("Minimap", self.minimap_check)

        self.grid_spin = QDoubleSpinBox()
        self.grid_spin.setRange(0, 50)
        self.grid_spin.setDecimals(0)
        self.grid_spin.setValue(settings.get("grid_threshold"))
        self.grid_spin.setSpecialValueText("off")
        self.grid_spin.setToolTip(
            "When one rail feeds at least this many leaf loads, they wrap "
            "into a compact grid instead of an endless row (0 = off)")
        form.addRow("Rail-grid wrap at", self.grid_spin)

        self.autofit_check = QCheckBox("Fit view when switching trees")
        self.autofit_check.setChecked(settings.get("autofit_on_switch"))
        form.addRow("Auto-fit", self.autofit_check)

        self.orient_combo = QComboBox()
        self.orient_combo.addItem("Top-down", "TD")
        self.orient_combo.addItem("Left-right", "LR")
        idx = 0 if settings.get("default_orientation") == "TD" else 1
        self.orient_combo.setCurrentIndex(idx)
        form.addRow("New-tree layout", self.orient_combo)

        self.png_scale = QDoubleSpinBox()
        self.png_scale.setRange(1.0, 8.0)
        self.png_scale.setSingleStep(0.5)
        self.png_scale.setValue(settings.get("png_scale"))
        self.png_scale.setToolTip("Render scale for HD flowchart image "
                                  "exports (3.0 ≈ 300 dpi)")
        form.addRow("PNG export scale", self.png_scale)

        self.si_digits = QDoubleSpinBox()
        self.si_digits.setRange(3, 6)
        self.si_digits.setDecimals(0)
        self.si_digits.setValue(settings.get("si_digits"))
        self.si_digits.setToolTip("Significant digits for every displayed "
                                  "value (cards, list, status, reports)")
        form.addRow("Significant digits", self.si_digits)

        self.pdf_images = QCheckBox("Embed flowchart images")
        self.pdf_images.setChecked(settings.get("pdf_include_images"))
        form.addRow("PDF report", self.pdf_images)
        self.pdf_notes = QCheckBox("Append documentation notes")
        self.pdf_notes.setChecked(settings.get("pdf_include_notes"))
        form.addRow("", self.pdf_notes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _save(self):
        s = self.settings
        s.set("canvas_style", self.style_combo.currentData())
        s.set("detail_default", self.detail_combo.currentText())
        s.set("heat_mode", self.heat_check.isChecked())
        s.set("legend", self.legend_check.isChecked())
        s.set("autofit_on_switch", self.autofit_check.isChecked())
        s.set("default_orientation", self.orient_combo.currentData())
        s.set("png_scale", self.png_scale.value())
        s.set("si_digits", self.si_digits.value())
        s.set("minimap", self.minimap_check.isChecked())
        s.set("grid_threshold", self.grid_spin.value())
        s.set("pdf_include_images", self.pdf_images.isChecked())
        s.set("pdf_include_notes", self.pdf_notes.isChecked())
        self.accept()
