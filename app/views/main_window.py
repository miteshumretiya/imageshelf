"""View: the ImageShelf main window. It builds widgets and reacts to controller signals.

Slots here are kept short: they read input from widgets, call the controller and
update the display. All processing happens in the controller/services/workers.
"""
from __future__ import annotations

from PyQt6.QtCore import QItemSelectionModel, QModelIndex, QSize, Qt, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QHeaderView, QLabel, QLineEdit,
    QListView, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QSplitter,
    QStackedWidget, QStyle, QTableView, QTabWidget, QVBoxLayout, QWidget,
)

from app import __version__
from app.controllers.main_controller import MainController
from app.models.image_item import Orientation, ScanSummary
from app.models.image_table_model import (
    COL_DIMENSIONS, COL_FOLDER, COL_FORMAT, COL_MODIFIED, COL_NAME, COL_SIZE,
    ImageFilterProxyModel, ImageTableModel,
)
from app.services.image_service import format_size
from app.utils import resource_path
from app.views.preview_panel import PreviewPanel
from app.views.settings_dialog import SettingsDialog

TAB_PREVIEW, TAB_SUMMARY, TAB_ERRORS = range(3)
VIEW_SHELF, VIEW_DETAILS = range(2)


class MainWindow(QMainWindow):
    def __init__(self, controller: MainController, model: ImageTableModel) -> None:
        super().__init__()
        self.controller = controller
        self.model = model
        self.proxy = ImageFilterProxyModel(self)
        self.proxy.setSourceModel(model)
        self._last_folder = ""

        self.setWindowTitle("ImageShelf")
        self.resize(1280, 780)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_central_area()
        self._create_status_bar()
        self._connect_signals()

        # Audio notification when a scan finishes (QtMultimedia).
        self._chime = QSoundEffect(self)
        self._chime.setSource(QUrl.fromLocalFile(resource_path("assets/done.wav")))
        self._chime.setVolume(0.6)

        self._on_busy_changed(False)

    # ================================================================== UI construction
    def _create_actions(self) -> None:
        icon = self.style().standardIcon
        sp = QStyle.StandardPixmap
        self.act_open = QAction(icon(sp.SP_DirOpenIcon), "&Open Folder…", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.setStatusTip("Choose a folder of images to catalogue")

        self.act_rescan = QAction(icon(sp.SP_BrowserReload), "&Rescan", self)
        self.act_rescan.setShortcut(QKeySequence("F5"))
        self.act_rescan.setStatusTip("Scan the current folder again")

        self.act_cancel = QAction(icon(sp.SP_BrowserStop), "&Cancel Scan", self)
        self.act_cancel.setShortcut(QKeySequence("Esc"))
        self.act_cancel.setStatusTip("Stop the running scan")

        self.act_export = QAction(icon(sp.SP_DialogSaveButton), "&Export CSV…", self)
        self.act_export.setShortcut(QKeySequence("Ctrl+E"))
        self.act_export.setStatusTip("Save the catalogue as a CSV file")

        self.act_settings = QAction("&Settings…", self)
        self.act_settings.setShortcut(QKeySequence("Ctrl+,"))

        self.act_exit = QAction("E&xit", self)
        self.act_exit.setShortcut(QKeySequence.StandardKey.Quit)

        self.act_shelf = QAction(icon(sp.SP_FileDialogContentsView), "&Shelf view", self)
        self.act_shelf.setShortcut(QKeySequence("Ctrl+1"))
        self.act_shelf.setStatusTip("Show images as a grid of thumbnails")
        self.act_details = QAction(icon(sp.SP_FileDialogDetailedView), "&Details view", self)
        self.act_details.setShortcut(QKeySequence("Ctrl+2"))
        self.act_details.setStatusTip("Show images in a sortable table")
        group = QActionGroup(self)
        for action in (self.act_shelf, self.act_details):
            action.setCheckable(True)
            group.addAction(action)
        self.act_shelf.setChecked(True)

        self.act_duplicates = QAction("Show &duplicates only", self)
        self.act_duplicates.setCheckable(True)
        self.act_duplicates.setShortcut(QKeySequence("Ctrl+D"))
        self.act_duplicates.setStatusTip("Hide images that have no duplicate")

        self.act_slideshow = QAction(icon(sp.SP_MediaPlay), "Start/stop s&lideshow", self)
        self.act_slideshow.setShortcut(QKeySequence("F11"))

        self.act_about = QAction("&About", self)

    def _create_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addActions([self.act_open, self.act_rescan, self.act_export])
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        scan_menu = bar.addMenu("&Scan")
        scan_menu.addActions([self.act_cancel, self.act_settings])

        view_menu = bar.addMenu("&View")
        view_menu.addActions([self.act_shelf, self.act_details])
        view_menu.addSeparator()
        view_menu.addActions([self.act_duplicates, self.act_slideshow])

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.act_about)

    def _create_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.addActions([self.act_open, self.act_rescan, self.act_cancel])
        toolbar.addSeparator()
        toolbar.addActions([self.act_shelf, self.act_details])
        toolbar.addSeparator()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(240)
        toolbar.addWidget(self.search_edit)

        self.orientation_combo = QComboBox()
        self.orientation_combo.addItem("All shapes", None)
        for orientation in Orientation:
            self.orientation_combo.addItem(orientation.value, orientation)
        toolbar.addWidget(self.orientation_combo)

        toolbar.addAction(self.act_duplicates)
        toolbar.addSeparator()
        toolbar.addAction(self.act_export)

    def _create_central_area(self) -> None:
        self.folder_label = QLabel("No folder yet. Use File → Open Folder… to build your shelf.")
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Shelf view: a grid of thumbnails (QListView in icon mode).
        self.shelf = QListView()
        self.shelf.setModel(self.proxy)
        self.shelf.setViewMode(QListView.ViewMode.IconMode)
        self.shelf.setIconSize(QSize(140, 140))
        self.shelf.setGridSize(QSize(170, 190))
        self.shelf.setResizeMode(QListView.ResizeMode.Adjust)
        self.shelf.setMovement(QListView.Movement.Static)
        self.shelf.setWordWrap(True)
        self.shelf.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Details view: a sortable table of the same data.
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(COL_NAME, Qt.SortOrder.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setIconSize(QSize(32, 32))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_FOLDER, QHeaderView.ResizeMode.Stretch)
        for column, width in ((COL_NAME, 230), (COL_DIMENSIONS, 105), (COL_FORMAT, 60),
                              (COL_SIZE, 80), (COL_MODIFIED, 130)):
            header.resizeSection(column, width)

        # Both views share ONE selection model, so selecting in one selects in the other.
        self.shelf.setSelectionModel(self.table.selectionModel())

        self.views = QStackedWidget()
        self.views.addWidget(self.shelf)
        self.views.addWidget(self.table)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.folder_label)
        left_layout.addWidget(self.views)

        self.preview = PreviewPanel()
        self.summary_labels: dict[str, QLabel] = {}
        summary_page = QWidget()
        summary_form = QFormLayout(summary_page)
        for key in ("Folder", "Status", "Images catalogued", "Total size", "Total megapixels",
                    "Formats", "Shapes", "Duplicate groups", "Duplicate images",
                    "Space wasted by copies", "Unreadable files", "Time taken"):
            label = QLabel("–")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setWordWrap(True)
            self.summary_labels[key] = label
            summary_form.addRow(f"{key}:", label)

        self.error_log = QPlainTextEdit()
        self.error_log.setReadOnly(True)
        self.error_log.setPlaceholderText("Files that could not be read will be listed here.")

        self.tabs = QTabWidget()
        self.tabs.addTab(self.preview, "Preview")
        self.tabs.addTab(summary_page, "Summary")
        self.tabs.addTab(self.error_log, "Errors")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

    def _create_status_bar(self) -> None:
        self.count_label = QLabel("0 images")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.count_label)
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage("Ready")

    def _connect_signals(self) -> None:
        # user actions -> view slots
        self.act_open.triggered.connect(self.choose_folder)
        self.act_rescan.triggered.connect(self.rescan)
        self.act_cancel.triggered.connect(self.cancel_scan)
        self.act_export.triggered.connect(self.export_csv)
        self.act_settings.triggered.connect(self.open_settings)
        self.act_exit.triggered.connect(self.close)
        self.act_about.triggered.connect(self.show_about)
        self.act_shelf.triggered.connect(lambda: self.views.setCurrentIndex(VIEW_SHELF))
        self.act_details.triggered.connect(lambda: self.views.setCurrentIndex(VIEW_DETAILS))
        self.act_duplicates.toggled.connect(self.proxy.set_duplicates_only)
        self.act_slideshow.triggered.connect(
            lambda: self.preview.slideshow_button.toggle())
        self.search_edit.textChanged.connect(self.proxy.set_search_text)
        self.orientation_combo.currentIndexChanged.connect(
            lambda _: self.proxy.set_orientation(self.orientation_combo.currentData()))
        self.table.selectionModel().currentRowChanged.connect(self._on_current_row_changed)
        self.shelf.doubleClicked.connect(lambda _: self.tabs.setCurrentIndex(TAB_PREVIEW))
        self.table.doubleClicked.connect(lambda _: self.tabs.setCurrentIndex(TAB_PREVIEW))
        for signal in (self.proxy.rowsInserted, self.proxy.rowsRemoved,
                       self.proxy.modelReset, self.proxy.layoutChanged):
            signal.connect(self._update_count)

        # slideshow (custom signals from the preview panel)
        self.preview.next_requested.connect(self.show_next_image)
        self.preview.slideshow_toggled.connect(self._on_slideshow_toggled)

        # controller signals -> view slots
        c = self.controller
        c.scan_started.connect(self._on_scan_started)
        c.files_listed.connect(self._on_files_listed)
        c.progress_changed.connect(self._on_progress)
        c.file_error.connect(self._on_file_error)
        c.scan_finished.connect(self._on_scan_finished)
        c.scan_failed.connect(self._on_scan_failed)
        c.busy_changed.connect(self._on_busy_changed)

    # ================================================================== user actions
    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose an image folder", self._last_folder)
        if folder:  # empty string means the user pressed Cancel
            self._last_folder = folder
            self.controller.start_scan(folder)

    def rescan(self) -> None:
        if self._last_folder:
            self.controller.start_scan(self._last_folder)
        else:
            self.choose_folder()

    def cancel_scan(self) -> None:
        if self.controller.cancel_scan():
            self.statusBar().showMessage("Cancelling…")

    def export_csv(self) -> None:
        if self.model.rowCount() == 0:
            QMessageBox.information(self, "Nothing to export", "Scan a folder first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export catalogue", "imageshelf.csv",
                                              "CSV files (*.csv)")
        if not path:
            return
        try:
            rows = self.controller.export_csv(path)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", f"Could not save the file:\n{exc}")
            return
        self.statusBar().showMessage(f"Exported {rows} images to {path}", 8000)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.controller.settings, self)
        if dialog.exec():
            self.controller.settings = dialog.result_settings()
            self.statusBar().showMessage("Settings saved. They apply to the next scan.", 5000)

    def show_about(self) -> None:
        QMessageBox.about(self, "About ImageShelf",
                          f"<b>ImageShelf {__version__}</b><br>"
                          "Catalogues a folder of photos, finds duplicate images and plays "
                          "slideshows with music.<br>Built with Python and PyQt6.")

    def show_next_image(self) -> None:
        """Select the next visible image (wraps around). Used by the slideshow."""
        rows = self.proxy.rowCount()
        if rows == 0:
            self.preview.stop_slideshow()
            return
        current = self.table.selectionModel().currentIndex()
        next_row = (current.row() + 1) % rows if current.isValid() else 0
        self._select_row(next_row)

    def _select_row(self, row: int) -> None:
        index = self.proxy.index(row, COL_NAME)
        self.table.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows)
        self.shelf.scrollTo(index)
        self.table.scrollTo(index)

    # ================================================================== view updates
    def _on_current_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        source = self.proxy.mapToSource(current)
        self.preview.show_item(self.model.item_at(source.row()) if source.isValid() else None)

    def _on_slideshow_toggled(self, running: bool) -> None:
        if not running:
            self.statusBar().showMessage("Slideshow stopped", 3000)
            return
        if self.proxy.rowCount() == 0:
            self.preview.stop_slideshow()
            QMessageBox.information(self, "Slideshow", "There are no images to show. "
                                    "Scan a folder or clear the filters first.")
            return
        self.tabs.setCurrentIndex(TAB_PREVIEW)
        if not self.table.selectionModel().currentIndex().isValid():
            self._select_row(0)
        self.statusBar().showMessage("Slideshow running")

    def _update_count(self, *_args) -> None:
        shown, total = self.proxy.rowCount(), self.model.rowCount()
        self.count_label.setText(f"{total} images" if shown == total
                                 else f"{shown} of {total} images")

    def _on_busy_changed(self, busy: bool) -> None:
        self.act_open.setEnabled(not busy)
        self.act_rescan.setEnabled(not busy)
        self.act_settings.setEnabled(not busy)
        self.act_export.setEnabled(not busy)
        self.act_cancel.setEnabled(busy)

    def _on_scan_started(self, folder: str) -> None:
        self._last_folder = folder
        self.preview.stop_slideshow()
        self.folder_label.setText(f"Folder: {folder}")
        self.preview.show_item(None)
        self.error_log.clear()
        self.progress.setRange(0, 0)  # "busy" animation until we know the file count
        self.progress.setVisible(True)
        self.statusBar().showMessage("Looking for images…")

    def _on_files_listed(self, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(0)
        self.statusBar().showMessage(f"Found {total} images. Making thumbnails…")

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setValue(done)
        self.statusBar().showMessage(f"Processed {done} of {total} images…")

    def _on_file_error(self, path: str, message: str) -> None:
        self.error_log.appendPlainText(f"{path}\n    {message}")

    def _on_scan_finished(self, summary: ScanSummary) -> None:
        self.progress.setVisible(False)
        self.proxy.refresh()
        self._show_summary(summary)
        self._chime.play()

        if summary.cancelled:
            text = f"Scan cancelled after {summary.total_images} images."
        elif summary.total_images == 0 and summary.error_count == 0:
            text = "No supported images were found in this folder."
        else:
            text = (f"Shelf ready: {summary.total_images} images in "
                    f"{summary.elapsed_seconds:.1f} s, {summary.duplicate_groups} duplicate groups.")
        if summary.error_count:
            text += f" {summary.error_count} files could not be read (see the Errors tab)."
        self.statusBar().showMessage(text)

        box = QMessageBox(QMessageBox.Icon.Information, "Scan finished", text,
                          QMessageBox.StandardButton.Ok, self)
        box.open()  # non-blocking notification

    def _on_scan_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.statusBar().showMessage("Scan could not run.", 5000)
        QMessageBox.warning(self, "Cannot scan", message)

    def _show_summary(self, s: ScanSummary) -> None:
        values = {
            "Folder": s.folder,
            "Status": "Cancelled" if s.cancelled else "Completed",
            "Images catalogued": str(s.total_images),
            "Total size": format_size(s.total_bytes),
            "Total megapixels": f"{s.total_megapixels:.1f} MP",
            "Formats": " · ".join(f"{k} {v}" for k, v in s.counts_by_format.items()) or "–",
            "Shapes": " · ".join(f"{k} {v}" for k, v in s.counts_by_orientation.items()),
            "Duplicate groups": str(s.duplicate_groups),
            "Duplicate images": str(s.duplicate_images),
            "Space wasted by copies": format_size(s.wasted_bytes),
            "Unreadable files": str(s.error_count),
            "Time taken": f"{s.elapsed_seconds:.2f} s",
        }
        for key, value in values.items():
            self.summary_labels[key].setText(value)

    # ================================================================== closing
    def closeEvent(self, event) -> None:
        if self.controller.is_busy:
            answer = QMessageBox.question(self, "Scan in progress",
                                          "A scan is still running. Cancel it and quit?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.preview.stop()
        self.controller.shutdown()
        event.accept()
