"""Preview panel with a slideshow that plays background music (Task 5 - QtMultimedia).

* The selected image is shown full size (scaled to fit) with its details.
* "Start slideshow" moves through the visible images every N seconds. The panel only
  emits `next_requested`; the main window decides which image comes next.
* "Choose music…" picks an audio file that QMediaPlayer + QAudioOutput play (looped)
  while the slideshow runs - pausing and resuming with it.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy,
    QSlider, QSpinBox, QStackedWidget, QStyle, QVBoxLayout, QWidget,
)

from app.models.image_item import ImageItem
from app.services.image_service import format_size, validate_music_file
from app.services.thumbnailer import load_full_image

PAGE_MESSAGE, PAGE_IMAGE = range(2)


class PreviewPanel(QWidget):
    next_requested = pyqtSignal()          # slideshow timer fired: show the next image
    slideshow_toggled = pyqtSignal(bool)   # slideshow started (True) or stopped (False)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._music_path: Path | None = None

        # --- image display ---
        self._stack = QStackedWidget()
        self._message = QLabel()
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._image.setMinimumSize(220, 160)
        self._stack.addWidget(self._message)
        self._stack.addWidget(self._image)

        self._info = QLabel()
        self._info.setWordWrap(True)
        self._info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # --- slideshow controls ---
        style = self.style()
        self.slideshow_button = QPushButton(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Start slideshow")
        self.slideshow_button.setCheckable(True)
        self.interval = QSpinBox()
        self.interval.setRange(1, 60)
        self.interval.setValue(3)
        self.interval.setSuffix(" s")
        self.interval.setToolTip("Seconds per image")

        self.music_button = QPushButton(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaVolume), "Choose music…")
        self.music_label = QLabel("No music chosen")
        self.music_label.setWordWrap(True)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(60)
        self.volume.setToolTip("Music volume")

        row1 = QHBoxLayout()
        row1.addWidget(self.slideshow_button)
        row1.addWidget(QLabel("Every"))
        row1.addWidget(self.interval)
        row1.addStretch(1)
        row2 = QHBoxLayout()
        row2.addWidget(self.music_button)
        row2.addWidget(QLabel("Volume"))
        row2.addWidget(self.volume, 1)
        box_layout = QVBoxLayout()
        box_layout.addLayout(row1)
        box_layout.addLayout(row2)
        box_layout.addWidget(self.music_label)
        slideshow_box = QGroupBox("Slideshow")
        slideshow_box.setLayout(box_layout)

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack, 1)
        layout.addWidget(self._info)
        layout.addWidget(slideshow_box)

        # --- timer and QtMultimedia player ---
        self._timer = QTimer(self)
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.6)
        self._player.setAudioOutput(self._audio_output)
        self._player.setLoops(QMediaPlayer.Loops.Infinite)

        # --- signals and slots ---
        self.slideshow_button.toggled.connect(self._on_slideshow_toggled)
        self.interval.valueChanged.connect(lambda s: self._timer.setInterval(s * 1000))
        self._timer.timeout.connect(self.next_requested)
        self.music_button.clicked.connect(self.choose_music)
        self.volume.valueChanged.connect(lambda v: self._audio_output.setVolume(v / 100))
        self._player.errorOccurred.connect(self._on_player_error)

        self.show_item(None)

    # ---- image preview -------------------------------------------------------------------
    def show_item(self, item: ImageItem | None) -> None:
        self._pixmap = None
        if item is None:
            self._show_message("Select an image to preview it.")
            self._info.clear()
            return
        self._info.setText(f"<b>{item.name}</b><br>{item.dimensions} px · {item.image_format} · "
                           f"{format_size(item.size_bytes)} · {item.orientation.value}"
                           f"<br><small>{item.path}</small>")
        try:
            image = load_full_image(item.path)
        except ValueError as exc:
            self._show_message(str(exc))
            return
        self._pixmap = QPixmap.fromImage(image)
        self._stack.setCurrentIndex(PAGE_IMAGE)
        self._update_image()

    def _show_message(self, text: str) -> None:
        self._message.setText(text)
        self._stack.setCurrentIndex(PAGE_MESSAGE)

    def _update_image(self) -> None:
        if self._pixmap is not None:
            self._image.setPixmap(self._pixmap.scaled(
                self._image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_image()

    # ---- slideshow + music ----------------------------------------------------------------
    @property
    def is_slideshow_running(self) -> bool:
        return self._timer.isActive()

    def choose_music(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose slideshow music", "",
            "Audio files (*.mp3 *.wav *.ogg *.flac *.m4a *.aac);;All files (*)")
        if path:
            try:
                self.set_music(path)
            except ValueError as exc:
                QMessageBox.warning(self, "Cannot use this file", str(exc))

    def set_music(self, path: str) -> None:
        music = validate_music_file(path)  # raises ValueError for bad input
        self._music_path = music
        self._player.setSource(QUrl.fromLocalFile(str(music)))
        self.music_label.setText(f"♫ {music.name}")
        if self.is_slideshow_running:
            self._player.play()

    def start_slideshow(self) -> None:
        self.slideshow_button.setChecked(True)

    def stop_slideshow(self) -> None:
        self.slideshow_button.setChecked(False)

    def _on_slideshow_toggled(self, running: bool) -> None:
        icon = QStyle.StandardPixmap.SP_MediaStop if running else QStyle.StandardPixmap.SP_MediaPlay
        self.slideshow_button.setIcon(self.style().standardIcon(icon))
        self.slideshow_button.setText("Stop slideshow" if running else "Start slideshow")
        if running:
            self._timer.start(self.interval.value() * 1000)
            if self._music_path is not None:
                self._player.play()
        else:
            self._timer.stop()
            self._player.pause()
        self.slideshow_toggled.emit(running)

    def _on_player_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.music_label.setText(f"Music cannot be played: {message or error.name}. "
                                     "The slideshow will continue without sound.")
            self._music_path = None

    def stop(self) -> None:
        self.stop_slideshow()
        self._player.stop()
