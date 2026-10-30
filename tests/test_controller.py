"""Integration tests: the controller running real background scans.

SignalCatcher.wait() runs the Qt event loop until the signal arrives, which is how the
queued signals from the worker threads get delivered during a test.
"""
from tests.conftest import SignalCatcher

from app.controllers.main_controller import MainController
from app.models.image_item import AppSettings
from app.models.image_table_model import ImageTableModel


def make_controller(**settings):
    model = ImageTableModel()
    return MainController(model, AppSettings(**settings)), model


def test_scan_completes_and_fills_model(image_folder):
    controller, model = make_controller(worker_count=4)
    finished = SignalCatcher(controller.scan_finished)
    assert controller.start_scan(str(image_folder))
    assert controller.is_busy
    assert finished.wait(10_000)

    summary = finished[0][0]
    assert summary.total_images == 4
    assert summary.error_count == 2               # broken.jpg and empty.png
    assert summary.duplicate_groups == 1          # a.png and b.png
    assert not summary.cancelled
    assert model.rowCount() == 4
    assert all(item.thumbnail is not None for item in model.items())
    assert not controller.is_busy


def test_errors_reported_with_file_names(image_folder):
    controller, _ = make_controller()
    errors = SignalCatcher(controller.file_error)
    finished = SignalCatcher(controller.scan_finished)
    controller.start_scan(str(image_folder))
    assert finished.wait(10_000)
    failed_files = sorted(errors[i][0].replace("\\", "/").split("/")[-1] for i in range(len(errors)))
    assert failed_files == ["broken.jpg", "empty.png"]


def test_progress_reaches_total(image_folder):
    controller, _ = make_controller()
    progress = SignalCatcher(controller.progress_changed)
    finished = SignalCatcher(controller.scan_finished)
    controller.start_scan(str(image_folder))
    assert finished.wait(10_000)
    values = sorted(progress[i][0] for i in range(len(progress)))
    assert values == [1, 2, 3, 4, 5, 6]            # every file reported exactly once


def test_non_recursive_setting(image_folder):
    controller, _ = make_controller(recursive=False)
    finished = SignalCatcher(controller.scan_finished)
    controller.start_scan(str(image_folder))
    assert finished.wait(10_000)
    assert finished[0][0].total_images == 3        # d.png in sub/ is skipped


def test_invalid_folder_reports_error_without_starting(tmp_path):
    controller, _ = make_controller()
    failed = SignalCatcher(controller.scan_failed)
    assert not controller.start_scan(str(tmp_path / "missing"))
    assert len(failed) == 1
    assert "does not exist" in failed[0][0]
    assert not controller.is_busy


def test_invalid_worker_setting_rejected(image_folder):
    controller, _ = make_controller(worker_count=0)
    failed = SignalCatcher(controller.scan_failed)
    assert not controller.start_scan(str(image_folder))
    assert "Worker count" in failed[0][0]


def test_second_scan_rejected_while_busy(image_folder):
    controller, _ = make_controller()
    failed = SignalCatcher(controller.scan_failed)
    finished = SignalCatcher(controller.scan_finished)
    controller.start_scan(str(image_folder))
    assert not controller.start_scan(str(image_folder))
    assert "already running" in failed[0][0]
    assert finished.wait(10_000)


def test_cancel_stops_scan(tmp_path):
    for i in range(200):
        (tmp_path / f"f{i:03d}.png").write_bytes(bytes([i % 256]) * 200_000)
    controller, _ = make_controller(worker_count=1)
    finished = SignalCatcher(controller.scan_finished)
    controller.start_scan(str(tmp_path))
    controller.cancel_scan()
    assert finished.wait(10_000)
    summary = finished[0][0]
    assert summary.cancelled
    assert summary.total_images + summary.error_count < 200


def test_export_after_scan(image_folder, tmp_path_factory):
    controller, _ = make_controller()
    finished = SignalCatcher(controller.scan_finished)
    controller.start_scan(str(image_folder))
    assert finished.wait(10_000)
    out = tmp_path_factory.mktemp("export") / "catalogue.csv"
    assert controller.export_csv(str(out)) == 4
