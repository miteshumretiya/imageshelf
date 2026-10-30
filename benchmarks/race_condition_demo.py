"""Task 7 evidence - what goes wrong WITHOUT a lock, and how the lock fixes it.

Eight threads each record 2,000 results in a shared counter, like ImageShelf's hash
workers updating the "processed" count. The unsafe version does read -> add -> write
without a lock; time.sleep(0) lets another thread run in between (as the OS may do at
any moment), so updates get lost. The safe version wraps the same steps in a lock.

    python benchmarks/race_condition_demo.py
"""
from __future__ import annotations

import threading
import time

THREADS = 8
PER_THREAD = 2_000


class UnsafeCounter:
    def __init__(self) -> None:
        self.value = 0

    def increment(self) -> None:
        current = self.value      # 1. read
        time.sleep(0)             #    another thread may run here
        self.value = current + 1  # 2. write (may overwrite another thread's update)


class SafeCounter(UnsafeCounter):
    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()

    def increment(self) -> None:
        with self._lock:          # only one thread at a time can do read + write
            super().increment()


def run(counter: UnsafeCounter) -> tuple[int, float]:
    start_line = threading.Barrier(THREADS)

    def work() -> None:
        start_line.wait()
        for _ in range(PER_THREAD):
            counter.increment()

    threads = [threading.Thread(target=work) for _ in range(THREADS)]
    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counter.value, time.perf_counter() - started


if __name__ == "__main__":
    expected = THREADS * PER_THREAD
    for label, counter in (("WITHOUT lock", UnsafeCounter()), ("WITH lock   ", SafeCounter())):
        value, seconds = run(counter)
        lost = expected - value
        print(f"{label}: expected {expected}, got {value}  -> {lost} updates lost "
              f"({seconds:.2f} s)")
