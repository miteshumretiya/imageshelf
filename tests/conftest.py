"""Shared pytest fixtures.

Qt needs a QApplication for image plugins and widgets. The "offscreen" platform lets
the tests run without opening windows (also on machines with no display).
"""
import os
import time
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform.startswith("linux"):
    # avoids a crash in some Linux containers that have no sound server
    os.environ.setdefault("QT_AUDIO_BACKEND", "pulseaudio")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtGui import QColor, QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.models.image_item import ImageItem  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class SignalCatcher:
    """Records every emission of a Qt signal and can wait for one.

    Note: PyQt's QSignalSpy.wait() keeps Python's GIL while it blocks, which can
    deadlock with worker threads that need the GIL to emit their signals. This
    helper pumps the event loop from Python instead, so the GIL is released.
    """

    def __init__(self, signal) -> None:
        self.calls: list[tuple] = []
        signal.connect(self._record)

    def _record(self, *args) -> None:
        self.calls.append(args)

    def wait(self, timeout_ms: int = 10_000) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        while not self.calls and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.005)
        return bool(self.calls)

    def __len__(self) -> int:
        return len(self.calls)

    def __getitem__(self, index: int) -> tuple:
        return self.calls[index]


def write_image(path: Path, width: int, height: int, colour=(200, 80, 40)) -> Path:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(*colour))
    path.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(path)), f"could not write {path}"
    return path


@pytest.fixture
def image_folder(tmp_path: Path) -> Path:
    """A small folder with known contents:

    a.png 40x20 (landscape) and b.png (identical copy -> duplicate pair)
    c.jpg 20x40 (portrait)
    sub/d.png 30x30 (square, in a sub-folder)
    notes.txt (ignored), broken.jpg (random bytes), sub/empty.png (0 bytes)
    -> 6 image files found, 4 readable, 2 errors, 1 duplicate group
    """
    write_image(tmp_path / "a.png", 40, 20)
    (tmp_path / "b.png").write_bytes((tmp_path / "a.png").read_bytes())
    write_image(tmp_path / "c.jpg", 20, 40, (10, 120, 200))
    write_image(tmp_path / "sub" / "d.png", 30, 30, (0, 200, 0))
    (tmp_path / "notes.txt").write_text("ignore me")
    (tmp_path / "broken.jpg").write_bytes(os.urandom(2000))
    (tmp_path / "sub" / "empty.png").write_bytes(b"")
    return tmp_path


def make_item(name="file.png", sha="aaa", size=100, width=400, height=300,
              fmt="PNG", folder="/photos", modified=0.0, thumbnail=None) -> ImageItem:
    return ImageItem(path=f"{folder}/{name}", image_format=fmt, width=width, height=height,
                     size_bytes=size, sha256=sha, modified=modified, thumbnail=thumbnail)
