"""PyInstaller GUI entry point."""
import os
import sys

if getattr(sys, "frozen", False):
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

from powertree.ui.app_entry import run_gui

if __name__ == "__main__":
    sys.exit(run_gui(sys.argv[1] if len(sys.argv) > 1 else None))
