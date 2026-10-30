"""Model layer: plain data classes describing images, scan results and settings.

No widgets here. Each ImageItem carries a small thumbnail (a QImage, which is safe
to create in worker threads); everything else is plain Python data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Orientation(str, Enum):
    LANDSCAPE = "Landscape"
    PORTRAIT = "Portrait"
    SQUARE = "Square"


# Supported file extensions and the format name shown to the user.
IMAGE_FORMATS: dict[str, str] = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".gif": "GIF",
    ".bmp": "BMP", ".webp": "WEBP", ".tif": "TIFF", ".tiff": "TIFF",
}

# Audio formats accepted as slideshow music.
MUSIC_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}


def image_format(path: str | Path) -> str | None:
    """Return the image format for a file name, or None if it is not a supported image."""
    return IMAGE_FORMATS.get(Path(path).suffix.lower())


def orientation_of(width: int, height: int) -> Orientation:
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive.")
    if width == height:
        return Orientation.SQUARE
    return Orientation.LANDSCAPE if width > height else Orientation.PORTRAIT


@dataclass(frozen=True)
class ImageItem:
    """One analysed image file."""
    path: str
    image_format: str
    width: int
    height: int
    size_bytes: int
    sha256: str
    modified: float  # seconds since the epoch
    thumbnail: Any = field(default=None, compare=False, repr=False)  # QImage

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def folder(self) -> str:
        return str(Path(self.path).parent)

    @property
    def orientation(self) -> Orientation:
        return orientation_of(self.width, self.height)

    @property
    def megapixels(self) -> float:
        return self.width * self.height / 1_000_000

    @property
    def dimensions(self) -> str:
        return f"{self.width} × {self.height}"


@dataclass(frozen=True)
class ScanSummary:
    """Totals shown to the user when a scan ends."""
    folder: str
    total_images: int
    total_bytes: int
    counts_by_format: dict[str, int] = field(default_factory=dict)
    counts_by_orientation: dict[str, int] = field(default_factory=dict)
    total_megapixels: float = 0.0
    duplicate_groups: int = 0
    duplicate_images: int = 0
    wasted_bytes: int = 0
    error_count: int = 0
    elapsed_seconds: float = 0.0
    cancelled: bool = False


MIN_WORKERS = 1
MAX_WORKERS = 32


@dataclass
class AppSettings:
    """User-configurable options (edited through the Settings dialog)."""
    worker_count: int = 4
    recursive: bool = True
    max_size_mb: int | None = None  # None means "no limit"

    @property
    def max_size_bytes(self) -> int | None:
        return None if self.max_size_mb is None else self.max_size_mb * 1024 * 1024
