"""GUI entry point shared by main.py, the CLI (`powertree gui`) and the
installer shortcut."""

from __future__ import annotations

import os
import sys


def gui_main() -> int:
    """Console-script entry point (`powertree-gui [project.ptproj]`)."""
    return run_gui(sys.argv[1] if len(sys.argv) > 1 else None)


def run_gui(project_path: str | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from .. import APP_NAME
    from ..logging_setup import setup_logging, install_gui_excepthook
    from ..model import serialization
    from .theme import apply_theme
    from .mainwindow import MainWindow

    setup_logging()
    install_gui_excepthook()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("PowerTree")
    apply_theme(app)

    win = MainWindow()
    if project_path and os.path.exists(project_path):
        try:
            win.project = serialization.load_project(project_path)
            win.current_tree = win.project.trees[0] if win.project.trees \
                else None
            win.notes.set_project(win.project)
            win._rebuild_tree_list()
            win.refresh(full=True)
            win.dirty = False
            win._update_title()
        except Exception as exc:
            print(f"Could not open {project_path}: {exc}", file=sys.stderr)
    win.showMaximized()
    win.canvas.fit()
    win.dirty = False
    return app.exec()
