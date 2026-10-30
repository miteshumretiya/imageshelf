"""Controller: coordinates the view, the data model and the background workers.

The view (MainWindow) only calls controller methods and listens to controller
signals. It never touches threads, the ResultsStore or the file-processing code.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal, pyqtSlot

from app.models.image_item import AppSettings, ImageItem
from app.models.image_table_model import ImageTableModel
from app.services import image_service
from app.services.results_store import ResultsStore
from app.workers.scan_worker import ScanJob


class MainController(QObject):
    # Custom signals the view listens to.
    scan_started = pyqtSignal(str)            # folder path
    files_listed = pyqtSignal(int)            # number of files that will be analysed
    progress_changed = pyqtSignal(int, int)   # processed, total
    file_error = pyqtSignal(str, str)         # path, message
    scan_finished = pyqtSignal(object)        # ScanSummary
    scan_failed = pyqtSignal(str)             # user-facing error message
    busy_changed = pyqtSignal(bool)

    def __init__(self, model: ImageTableModel, settings: AppSettings | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.settings = settings or AppSettings()
        self.store = ResultsStore()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)       # one scan at a time
        self._cancel_event = threading.Event()
        self._job: ScanJob | None = None
        self._busy = False
        self._folder = ""

    # ---- state ------------------------------------------------------------------------
    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def current_folder(self) -> str:
        return self._folder

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)

    # ---- commands called by the view -------------------------------------------------
    def start_scan(self, folder: str) -> bool:
        """Validate input and start a background scan. Returns False if it could not start."""
        if self._busy:
            self.scan_failed.emit("A scan is already running. Cancel it or wait for it to finish.")
            return False
        try:
            root = image_service.validate_folder(folder)
            workers = image_service.validate_worker_count(self.settings.worker_count)
        except ValueError as exc:
            self.scan_failed.emit(str(exc))
            return False

        self._folder = str(root)
        self.model.clear()
        self.store.reset()
        self._cancel_event = threading.Event()

        job = ScanJob(root, self.store, self._cancel_event, worker_count=workers,
                      recursive=self.settings.recursive,
                      max_size_bytes=self.settings.max_size_bytes)
        job.signals.files_listed.connect(self.files_listed)
        job.signals.item_ready.connect(self._on_item_ready)
        job.signals.file_failed.connect(self.file_error)
        job.signals.progress.connect(self.progress_changed)
        job.signals.finished.connect(self._on_finished)
        job.signals.failed.connect(self._on_failed)
        self._job = job

        self._set_busy(True)
        self.scan_started.emit(self._folder)
        self._pool.start(job)
        return True

    def cancel_scan(self) -> bool:
        if not self._busy:
            return False
        self._cancel_event.set()
        return True

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        """Cancel any scan and wait for the worker threads to stop (used on exit)."""
        self._cancel_event.set()
        return self._pool.waitForDone(timeout_ms)

    def export_csv(self, path: str) -> int:
        return image_service.export_csv(self.model.items(), path, self.model.duplicate_hashes)

    # ---- slots: these run in the GUI thread (queued from the worker threads) ----------
    @pyqtSlot(object)
    def _on_item_ready(self, item: ImageItem) -> None:
        self.model.add_item(item)

    @pyqtSlot(bool, float)
    def _on_finished(self, cancelled: bool, elapsed: float) -> None:
        items, errors = self.store.snapshot()
        groups = image_service.find_duplicates(items)
        self.model.set_duplicate_hashes(groups.keys())
        summary = image_service.build_summary(self._folder, items, len(errors), elapsed, cancelled)
        self._set_busy(False)
        self.scan_finished.emit(summary)

    @pyqtSlot(str)
    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.scan_failed.emit(message)
