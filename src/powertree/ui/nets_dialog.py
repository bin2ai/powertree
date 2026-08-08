"""Project-wide net registry dialog: every named rail, who defines it,
its nominal voltage, how many loads it feeds, and any conflicts."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel,
    QDialogButtonBox,
)

from ..model.elements import Project
from ..model.calc import fmt_si
from ..model.nets import collect_nets


class NetsDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Global nets — project-wide signal registry")
        self.resize(700, 460)
        lay = QVBoxLayout(self)

        info = QLabel(
            "Net (signal) names are global to the project: the same name in "
            "any tree is the same electrical node. Sources, converter outputs "
            "and series-element outputs define nets; loads consume them. "
            "Scope note: this registry checks NAMES and definitions — trees "
            "are still solved independently (cross-tree merged solving is on "
            "the roadmap), so a shared net's loads in another tree do not "
            "yet burden this tree's source.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #98a3b8;")
        lay.addWidget(info)

        tree = QTreeWidget()
        tree.setColumnCount(4)
        tree.setHeaderLabels(["Net", "V typ", "Defined by", "Loads fed"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        for i, w in enumerate([160, 80, 330, 80]):
            tree.setColumnWidth(i, w)
        nets, conflicts = collect_nets(project)
        mono = QFont("Consolas", 9)
        for name in sorted(nets):
            net = nets[name]
            definers = "; ".join(f"{d.element_name} ({d.tree_name})"
                                 for d in net.definers)
            item = QTreeWidgetItem(tree, [
                name, fmt_si(net.v_typ, "V") if net.v_typ is not None else "—",
                definers, str(net.consumers)])
            item.setFont(0, mono)
            item.setTextAlignment(3, Qt.AlignCenter)
        lay.addWidget(tree, 1)

        if conflicts:
            for c in conflicts:
                lbl = QLabel(f"⚠ {c}")
                lbl.setWordWrap(True)
                lbl.setStyleSheet("color: #f43f5e;")
                lay.addWidget(lbl)
        else:
            ok = QLabel("✅ No net conflicts — every net has a single "
                        "consistent definition.")
            ok.setStyleSheet("color: #10b981;")
            lay.addWidget(ok)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        lay.addWidget(buttons)
