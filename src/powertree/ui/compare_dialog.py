"""Architecture comparison dialog: every tree side by side on the axes that
decide architecture reviews — power, efficiency, loss, cost, area, growth
capacity and findings."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel,
    QDialogButtonBox,
)

from ..model.elements import Project
from ..model.calc import fmt_si
from .. import api

ROWS = [
    ("Elements", lambda r: str(r["elements"])),
    ("P typ", lambda r: fmt_si(r["p_typ_w"], "W")),
    ("P max (worst corner)", lambda r: fmt_si(r["p_max_w"], "W")),
    ("Efficiency (end-to-end)",
     lambda r: f"{r['efficiency_pct']:g} %"
     if r["efficiency_pct"] is not None else "—"),
    ("Loss (typ)", lambda r: fmt_si(r["p_loss_typ_w"], "W")),
    ("Cost (entered items)",
     lambda r: f"{r['cost_total']:g}" if r["cost_total"] is not None else "—"),
    ("Board area",
     lambda r: f"{r['area_total_mm2']:g} mm²"
     if r["area_total_mm2"] is not None else "—"),
    ("Load growth capacity",
     lambda r: f"+{r['growth_pct']:g} %"
     if r["growth_pct"] is not None else "—"),
    ("Growth bottleneck", lambda r: r["bottleneck"] or "—"),
    ("Findings",
     lambda r: ("clean" if not (r["errors"] or r["warnings"])
                else f"{r['errors']} err / {r['warnings']} warn")
     + (f" · {r['waived']} waived" if r["waived"] else "")),
]


class CompareDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare architectures")
        self.resize(240 + 190 * len(project.trees), 460)
        lay = QVBoxLayout(self)
        info = QLabel(
            "Trees compared side by side — model architecture variants as "
            "separate trees (duplicate one, change the regulator scheme) and "
            "let the numbers decide.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #98a3b8;")
        lay.addWidget(info)

        rows = api.compare_trees(project)
        table = QTableWidget(len(ROWS), len(rows))
        table.setHorizontalHeaderLabels([r["tree"] for r in rows])
        table.setVerticalHeaderLabels([label for label, _ in ROWS])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        mono = QFont("Consolas", 9)
        for col, r in enumerate(rows):
            for row_i, (_label, fn) in enumerate(ROWS):
                item = QTableWidgetItem(fn(r))
                item.setFont(mono)
                item.setTextAlignment(Qt.AlignCenter)
                if _label == "Findings":
                    if r["errors"]:
                        item.setForeground(QBrush(QColor("#f43f5e")))
                    elif r["warnings"]:
                        item.setForeground(QBrush(QColor("#fbbf24")))
                    else:
                        item.setForeground(QBrush(QColor("#10b981")))
                table.setItem(row_i, col, item)
        table.resizeColumnsToContents()
        lay.addWidget(table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        lay.addWidget(buttons)
