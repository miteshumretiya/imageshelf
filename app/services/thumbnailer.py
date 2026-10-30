"""Reading image sizes and making thumbnails with QImageReader.

QImage and QImageReader are data classes (not widgets) and are safe to use in
worker threads, which is why thumbnails are created here and not in the GUI.
QPixmap, by contrast, may only be used in the GUI thread.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage, QImageReader

THUMBNAIL_SIZE = 160  # longest side of a thumbnail, in pixels


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    thumbnail: QImage


def fit_within(width: int, height: int, max_side: int) -> tuple[int, int]:
    """Scale (width, height) so the longest side is at most max_side. Never enlarges."""
    if width <= 0 or height <= 0 or max_side <= 0:
        raise ValueError("Width, height and max_side must be positive.")
    scale = min(1.0, max_side / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def read_image_info(path: str | Path, max_side: int = THUMBNAIL_SIZE) -> ImageInfo:
    """Return the image's real size and a small thumbnail. Raises ValueError if unreadable."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)  # respect camera rotation (EXIF)
    size = reader.size()
    if not size.isValid():
        raise ValueError(f"Not a readable image ({reader.errorString()}).")
    width, height = size.width(), size.height()

    thumb_w, thumb_h = fit_within(width, height, max_side)
    reader.setScaledSize(QSize(thumb_w, thumb_h))  # JPEGs are decoded at reduced size: fast
    thumbnail = reader.read()
    if thumbnail.isNull():
        raise ValueError(f"The image data is damaged ({reader.errorString()}).")

    # If the camera rotated the picture, swap the reported dimensions to match.
    if width != height and (thumbnail.width() > thumbnail.height()) != (width > height):
        width, height = height, width
    return ImageInfo(width, height, thumbnail)


def load_full_image(path: str | Path) -> QImage:
    """Load the full-size image for the preview. Raises ValueError if it cannot be read."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError(f"This image cannot be displayed ({reader.errorString()}).")
    return image
