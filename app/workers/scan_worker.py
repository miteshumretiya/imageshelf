"""Background scanning (Task 6 - concurrent processing).

How it works
------------
1. The controller starts a ScanJob on a QThreadPool, so the GUI thread is never blocked.
2. ScanJob lists the folder, then hashes each image and makes its thumbnail in parallel using a
   ThreadPoolExecutor with `worker_count` threads. hashlib releases Python's GIL
   while hashing large blocks and file reading is I/O, so threads give a real speed-up.
3. Each hash thread stores its result in the shared ResultsStore (protected by a lock)
   and emits Qt signals. The signals object lives in the GUI thread, so Qt delivers them
   as *queued* events: the slots run in the GUI thread and only that thread ever touches
   widgets or the table model. Worker threads never touch the GUI directly.
4. Cancelling sets a threading.Event. Every task checks it before starting and while
   reading each 1 MB chunk, so cancellation is quick even for very large files.
"""
from __future__ import annotations

import functools
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from app.services.image_service import ScanCancelled, analyse_file, scan_folder
from app.services.results_store import ResultsStore


class ScanSignals(QObject):
    """Signals emitted by a ScanJob (a QRunnable cannot define signals itself)."""
    files_listed = pyqtSignal(int)          # total number of files to analyse
    item_ready = pyqtSignal(object)         # ImageItem
    file_failed = pyqtSignal(str, str)      # path, error message
    progress = pyqtSignal(int, int)         # processed, total
    finished = pyqtSignal(bool, float)      # cancelled?, elapsed seconds
    failed = pyqtSignal(str)                # the whole scan could not run


class ScanJob(QRunnable):
    def __init__(self, folder: Path, store: ResultsStore, cancel_event: threading.Event,
                 worker_count: int = 4, recursive: bool = True,
                 max_size_bytes: int | None = None) -> None:
        super().__init__()
        self.setAutoDelete(False)  # the controller keeps a reference instead
        self.folder = folder
        self.store = store
        self.cancel_event = cancel_event
        self.worker_count = worker_count
        self.recursive = recursive
        self.max_size_bytes = max_size_bytes
        self.signals = ScanSignals()  # created in the GUI thread

    def run(self) -> None:  # runs in a QThreadPool thread
        started = time.perf_counter()
        try:
            paths = scan_folder(self.folder, self.recursive, self.max_size_bytes)
            total = len(paths)
            self.signals.files_listed.emit(total)

            if total and not self.cancel_event.is_set():
                task = functools.partial(self._process_one, total=total)
                with ThreadPoolExecutor(max_workers=self.worker_count,
                                        thread_name_prefix="hash-worker") as pool:
                    for _ in pool.map(task, paths):
                        pass

            self.signals.finished.emit(self.cancel_event.is_set(),
                                       time.perf_counter() - started)
        except Exception as exc:  # noqa: BLE001 - any failure must reach the GUI
            self.signals.failed.emit(f"The scan stopped because of an error:\n{exc}")

    def _process_one(self, path: Path, total: int) -> None:  # runs in a hash-worker thread
        if self.cancel_event.is_set():
            return
        try:
            item = analyse_file(path, self.cancel_event)
        except ScanCancelled:
            return
        except OSError as exc:
            done = self.store.add_error(str(path), exc.strerror or str(exc))
            self.signals.file_failed.emit(str(path), exc.strerror or str(exc))
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the scan
            done = self.store.add_error(str(path), str(exc))
            self.signals.file_failed.emit(str(path), str(exc))
        else:
            done = self.store.add_item(item)
            self.signals.item_ready.emit(item)
        self.signals.progress.emit(done, total)
