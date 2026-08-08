"""Background execution for long operations (exports, renders) so the GUI
never freezes — with a small busy dialog and a completion callback on the
GUI thread."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import QProgressDialog


class _Worker(QObject):
    finished = Signal(object, object)     # (result, exception_or_None)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        result, exc = None, None
        com_initialized = False
        try:
            try:                           # Excel COM needs per-thread init
                import pythoncom
                pythoncom.CoInitialize()
                com_initialized = True
            except ImportError:
                pass
            result = self._fn()
        except BaseException as e:         # surfaced to the GUI callback
            e.traceback_text = traceback.format_exc()
            exc = e
        finally:
            if com_initialized:
                import pythoncom
                pythoncom.CoUninitialize()
        self.finished.emit(result, exc)


def run_async(parent, title: str, fn, on_done):
    """Run fn() in a worker thread; show a busy dialog; call
    on_done(result, exception) back on the GUI thread."""
    dialog = QProgressDialog(title, "", 0, 0, parent)
    dialog.setWindowTitle("PowerTree")
    dialog.setWindowModality(Qt.WindowModal)
    dialog.setCancelButton(None)
    dialog.setMinimumDuration(400)        # only appears if it takes a while

    thread = QThread(parent)
    worker = _Worker(fn)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    def _finish(result, exc):
        dialog.reset()
        dialog.deleteLater()
        thread.quit()
        thread.wait(5000)
        worker.deleteLater()
        thread.deleteLater()
        on_done(result, exc)

    worker.finished.connect(_finish, Qt.QueuedConnection)
    thread.start()
    return thread
