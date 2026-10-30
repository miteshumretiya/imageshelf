"""Thread-safe store for scan results (Task 7 - synchronisation).

SHARED RESOURCE
    During a scan, several hash-worker threads finish files at the same time and
    each one records its result here: the list of items, the list of errors and
    the "processed" counter used for the progress bar.

WHAT WOULD GO WRONG WITHOUT A LOCK
    `self._processed += 1` is really three steps: read, add, write. If two threads
    read the same old value, both write old+1 and one update is lost, so the
    progress bar never reaches 100 % and the summary under-counts. A reader could
    also copy the item list while another thread is appending to it, getting a
    half-updated view (e.g. counter says 10 but only 9 items).

HOW THE LOCK PROTECTS IT
    Every read and write happens inside `with self._lock:`. Only one thread can
    hold the lock, so each "append item + increment counter" happens as one
    indivisible step, and snapshot() always returns a consistent copy.
    See benchmarks/race_condition_demo.py for a runnable demonstration.
"""
from __future__ import annotations

import threading

from app.models.image_item import ImageItem


class ResultsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[ImageItem] = []
        self._errors: list[tuple[str, str]] = []
        self._processed = 0

    def add_item(self, item: ImageItem) -> int:
        """Record a successful result; returns the new processed count."""
        with self._lock:
            self._items.append(item)
            self._processed += 1
            return self._processed

    def add_error(self, path: str, message: str) -> int:
        """Record a file that could not be read; returns the new processed count."""
        with self._lock:
            self._errors.append((path, message))
            self._processed += 1
            return self._processed

    @property
    def processed(self) -> int:
        with self._lock:
            return self._processed

    def snapshot(self) -> tuple[list[ImageItem], list[tuple[str, str]]]:
        """Return consistent copies of the items and errors."""
        with self._lock:
            return list(self._items), list(self._errors)

    def reset(self) -> None:
        with self._lock:
            self._items.clear()
            self._errors.clear()
            self._processed = 0
