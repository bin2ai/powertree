"""PowerTree launcher.

Usage:
    .venv\\Scripts\\python.exe main.py            # open with the demo project
    .venv\\Scripts\\python.exe main.py file.ptproj
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from PySide6.QtWidgets import QApplication

from powertree import APP_NAME
from powertree.ui.theme import apply_theme
from powertree.ui.mainwindow import MainWindow
from powertree.model import serialization


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("PowerTree")
    apply_theme(app)

    win = MainWindow()
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        try:
            win.project = serialization.load_project(sys.argv[1])
            win.current_tree = win.project.trees[0] if win.project.trees else None
            win.notes.set_project(win.project)
            win._rebuild_tree_list()
            win.refresh(full=True)
            win.dirty = False
            win._update_title()
        except Exception as exc:
            print(f"Could not open {sys.argv[1]}: {exc}", file=sys.stderr)
    win.showMaximized()
    win.canvas.fit()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
