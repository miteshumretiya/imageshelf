"""ImageShelf entry point: creates the model, controller and main window, then starts Qt."""
from __future__ import annotations

import logging
import multiprocessing
import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.controllers.main_controller import MainController
from app.models.image_item import AppSettings
from app.models.image_table_model import ImageTableModel
from app.views.main_window import MainWindow

log = logging.getLogger("imageshelf")


def install_exception_hook() -> None:
    """Show unexpected errors in a dialog instead of the app silently closing."""
    def hook(exc_type, exc, tb):
        log.error("Unhandled error", exc_info=(exc_type, exc, tb))
        details = "".join(traceback.format_exception(exc_type, exc, tb))
        if QApplication.instance() is not None:
            box = QMessageBox(QMessageBox.Icon.Critical, "Unexpected error",
                              f"Something went wrong:\n{exc}")
            box.setDetailedText(details)
            box.exec()
    sys.excepthook = hook


def main() -> int:
    multiprocessing.freeze_support()  # needed if a frozen (PyInstaller) build uses processes
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    app = QApplication(sys.argv)
    app.setApplicationName("ImageShelf")
    install_exception_hook()

    model = ImageTableModel()
    controller = MainController(model, AppSettings())
    window = MainWindow(controller, model)
    window.show()

    if len(sys.argv) > 1:  # optional: python main.py <folder> starts scanning straight away
        controller.start_scan(sys.argv[1])

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
