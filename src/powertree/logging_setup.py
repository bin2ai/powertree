"""Application logging: rotating file log in the per-user app-data dir plus
a GUI excepthook so crashes are captured with a pointer to the log."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys

log = logging.getLogger("powertree")


def app_data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "PowerTree")
    os.makedirs(path, exist_ok=True)
    return path


def log_path() -> str:
    return os.path.join(app_data_dir(), "powertree.log")


def setup_logging(level=logging.INFO) -> str:
    if any(isinstance(h, logging.handlers.RotatingFileHandler)
           for h in log.handlers):
        return log_path()
    handler = logging.handlers.RotatingFileHandler(
        log_path(), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(level)
    from . import __version__
    log.info("PowerTree %s starting (python %s)", __version__,
             sys.version.split()[0])
    return log_path()


def install_gui_excepthook():
    """Uncaught exceptions: log the traceback, show a dialog with the log
    location, keep the app alive when possible."""
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        import traceback
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("UNCAUGHT EXCEPTION:\n%s", text)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None, "PowerTree — unexpected error",
                    f"An unexpected error occurred:\n\n{exc}\n\n"
                    f"Details were written to:\n{log_path()}\n\n"
                    "Your work is autosaved; please report this with the "
                    "log attached.")
                return
        except Exception:
            pass
        previous(exc_type, exc, tb)

    sys.excepthook = hook
