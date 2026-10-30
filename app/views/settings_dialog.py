"""Settings dialog with input validation (Task 3)."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox,
    QSpinBox, QVBoxLayout,
)

from app.models.image_item import MAX_WORKERS, MIN_WORKERS, AppSettings
from app.services.image_service import validate_max_size_mb, validate_worker_count


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scan settings")
        self._result = settings

        self.workers = QSpinBox()
        self.workers.setRange(MIN_WORKERS, MAX_WORKERS)
        self.workers.setValue(settings.worker_count)
        self.workers.setToolTip("How many images are processed at the same time.")

        self.recursive = QCheckBox("Include sub-folders")
        self.recursive.setChecked(settings.recursive)

        self.max_size = QLineEdit("" if settings.max_size_mb is None else str(settings.max_size_mb))
        self.max_size.setPlaceholderText("No limit")
        self.max_size.setToolTip("Files larger than this (in MB) are skipped. Leave blank for no limit.")

        form = QFormLayout()
        form.addRow("Worker threads:", self.workers)
        form.addRow("", self.recursive)
        form.addRow("Skip files larger than (MB):", self.max_size)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("<small>Changes apply to the next scan.</small>"))
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        try:
            max_mb = validate_max_size_mb(self.max_size.text())
            workers = validate_worker_count(self.workers.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid setting", str(exc))
            self.max_size.setFocus()
            self.max_size.selectAll()
            return  # keep the dialog open so the user can fix the value
        self._result = AppSettings(worker_count=workers, recursive=self.recursive.isChecked(),
                                   max_size_mb=max_mb)
        self.accept()

    def result_settings(self) -> AppSettings:
        return self._result
