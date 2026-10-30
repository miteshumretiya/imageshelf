"""Tests for the thread-safe ResultsStore (Task 7)."""
import threading

from app.services.results_store import ResultsStore
from tests.conftest import make_item


def test_add_item_and_error_update_counts():
    store = ResultsStore()
    assert store.add_item(make_item("a")) == 1
    assert store.add_error("/x/b.png", "Permission denied") == 2
    items, errors = store.snapshot()
    assert [i.name for i in items] == ["a"]
    assert errors == [("/x/b.png", "Permission denied")]
    assert store.processed == 2


def test_snapshot_is_a_copy():
    store = ResultsStore()
    store.add_item(make_item("a"))
    items, _ = store.snapshot()
    items.clear()
    assert store.processed == 1
    assert len(store.snapshot()[0]) == 1


def test_reset_clears_everything():
    store = ResultsStore()
    store.add_item(make_item("a"))
    store.add_error("p", "e")
    store.reset()
    assert store.processed == 0
    assert store.snapshot() == ([], [])


def test_concurrent_writers_lose_no_updates():
    """8 threads x 2000 writes at the same time: every single one must be counted."""
    store = ResultsStore()
    threads_count, per_thread = 8, 2000
    start = threading.Barrier(threads_count)

    def writer(n):
        start.wait()  # release all threads together to maximise contention
        for i in range(per_thread):
            if i % 10 == 0:
                store.add_error(f"t{n}-{i}", "err")
            else:
                store.add_item(make_item(f"t{n}-{i}"))

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(threads_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    items, errors = store.snapshot()
    assert store.processed == threads_count * per_thread
    assert len(items) + len(errors) == threads_count * per_thread
    assert len(errors) == threads_count * per_thread // 10
