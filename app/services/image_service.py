"""Business logic: validating input, scanning folders, hashing, duplicates, summaries, export.

Keeping this logic out of the GUI event handlers means it can be unit-tested on its
own and called safely from worker threads or worker processes. The only Qt it uses
is QImageReader (via thumbnailer), which is thread-safe and contains no widgets.
"""
from __future__ import annotations

import csv
import hashlib
import os
import threading
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.models.image_item import (
    IMAGE_FORMATS, MAX_WORKERS, MIN_WORKERS, MUSIC_EXTENSIONS, ImageItem, Orientation,
    ScanSummary, image_format,
)
from app.services.thumbnailer import THUMBNAIL_SIZE, read_image_info

CHUNK_SIZE = 1024 * 1024        # read files 1 MB at a time
MAX_SIZE_LIMIT_MB = 100_000     # upper bound accepted by the settings dialog


class ScanCancelled(Exception):
    """Raised inside a worker when the user cancels a running scan."""


# --------------------------------------------------------------------------- validation
def validate_folder(path: str | os.PathLike | None) -> Path:
    """Return the folder as a Path, or raise ValueError with a user-friendly message."""
    if path is None or not str(path).strip():
        raise ValueError("Please choose a folder to scan.")
    folder = Path(str(path).strip()).expanduser()
    if not folder.exists():
        raise ValueError(f"The folder does not exist:\n{folder}")
    if not folder.is_dir():
        raise ValueError(f"This is a file, not a folder:\n{folder}")
    if not os.access(folder, os.R_OK | os.X_OK):
        raise ValueError(f"You do not have permission to read this folder:\n{folder}")
    return folder


def validate_max_size_mb(text: str | None) -> int | None:
    """Parse the 'skip files larger than' setting. Blank means no limit."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        raise ValueError("Maximum file size must be a whole number of megabytes "
                         "(or leave it blank for no limit).") from None
    if not 1 <= value <= MAX_SIZE_LIMIT_MB:
        raise ValueError(f"Maximum file size must be between 1 and {MAX_SIZE_LIMIT_MB} MB.")
    return value


def validate_worker_count(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("Worker count must be a whole number.")
    if not MIN_WORKERS <= value <= MAX_WORKERS:
        raise ValueError(f"Worker count must be between {MIN_WORKERS} and {MAX_WORKERS}.")
    return value


def validate_music_file(path: str | os.PathLike | None) -> Path:
    """Check a file chosen as slideshow music."""
    if path is None or not str(path).strip():
        raise ValueError("Please choose a music file.")
    music = Path(str(path))
    if music.suffix.lower() not in MUSIC_EXTENSIONS:
        allowed = ", ".join(sorted(MUSIC_EXTENSIONS))
        raise ValueError(f"'{music.name}' is not a supported audio file ({allowed}).")
    if not music.is_file():
        raise ValueError(f"The music file does not exist:\n{music}")
    return music


# --------------------------------------------------------------------------- scanning
def scan_folder(folder: str | os.PathLike, recursive: bool = True,
                max_size_bytes: int | None = None) -> list[Path]:
    """List supported image files in a folder (sorted). Other files are ignored."""
    root = validate_folder(folder)
    found: list[Path] = []

    if recursive:
        walker = os.walk(root)  # sub-folders we cannot read are skipped
    else:
        with os.scandir(root) as entries:
            names = [e.name for e in entries if e.is_file()]
        walker = [(str(root), [], names)]

    for dirpath, _dirs, filenames in walker:
        for name in filenames:
            path = Path(dirpath) / name
            if image_format(path) is None or not path.is_file():
                continue
            if max_size_bytes is not None:
                try:
                    if path.stat().st_size > max_size_bytes:
                        continue
                except OSError:
                    pass  # analyse_file() will report the problem properly
            found.append(path)
    return sorted(found)


def compute_sha256(path: str | os.PathLike, chunk_size: int = CHUNK_SIZE,
                   cancel_event: threading.Event | None = None) -> str:
    """SHA-256 of a file, read in chunks. Raises ScanCancelled if the event is set."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            if cancel_event is not None and cancel_event.is_set():
                raise ScanCancelled()
            digest.update(chunk)
    return digest.hexdigest()


def analyse_file(path: str | os.PathLike, cancel_event: threading.Event | None = None,
                 max_side: int = THUMBNAIL_SIZE) -> ImageItem:
    """Hash one image, read its size and make a thumbnail.

    Raises OSError (cannot open/read), ValueError (unsupported, empty or damaged)
    or ScanCancelled.
    """
    file_path = Path(path)
    fmt = image_format(file_path)
    if fmt is None:
        raise ValueError(f"Unsupported file type: {file_path.suffix or '(no extension)'}")
    stat = file_path.stat()
    if stat.st_size == 0:
        raise ValueError("The file is empty (0 bytes).")
    digest = compute_sha256(file_path, cancel_event=cancel_event)
    if cancel_event is not None and cancel_event.is_set():
        raise ScanCancelled()
    info = read_image_info(file_path, max_side)
    return ImageItem(path=str(file_path), image_format=fmt, width=info.width,
                     height=info.height, size_bytes=stat.st_size, sha256=digest,
                     modified=stat.st_mtime, thumbnail=info.thumbnail)


# --------------------------------------------------------------------------- analysis
def find_duplicates(items: Iterable[ImageItem]) -> dict[str, list[ImageItem]]:
    """Group images with identical content. Only groups of 2+ files are returned."""
    groups: dict[str, list[ImageItem]] = defaultdict(list)
    for item in items:
        groups[item.sha256].append(item)
    return {digest: group for digest, group in groups.items() if len(group) > 1}


def wasted_bytes(groups: dict[str, list[ImageItem]]) -> int:
    """Space that could be freed by keeping only one copy of each duplicate."""
    return sum(group[0].size_bytes * (len(group) - 1) for group in groups.values())


def build_summary(folder: str, items: list[ImageItem], error_count: int,
                  elapsed_seconds: float, cancelled: bool) -> ScanSummary:
    groups = find_duplicates(items)
    formats = Counter(item.image_format for item in items)
    orientations = Counter(item.orientation.value for item in items)
    return ScanSummary(
        folder=folder,
        total_images=len(items),
        total_bytes=sum(item.size_bytes for item in items),
        counts_by_format=dict(sorted(formats.items())),
        counts_by_orientation={o.value: orientations.get(o.value, 0) for o in Orientation},
        total_megapixels=sum(item.megapixels for item in items),
        duplicate_groups=len(groups),
        duplicate_images=sum(len(g) for g in groups.values()),
        wasted_bytes=wasted_bytes(groups),
        error_count=error_count,
        elapsed_seconds=elapsed_seconds,
        cancelled=cancelled,
    )


def matches_filter(item: ImageItem, text: str = "", orientation: Orientation | None = None,
                   duplicates_only: bool = False,
                   duplicate_hashes: frozenset[str] | set[str] = frozenset()) -> bool:
    """Decide whether an image is visible (used by the filter proxy model)."""
    if text and text.strip().lower() not in item.name.lower():
        return False
    if orientation is not None and item.orientation != orientation:
        return False
    if duplicates_only and item.sha256 not in duplicate_hashes:
        return False
    return True


# --------------------------------------------------------------------------- formatting / export
def format_size(num_bytes: int) -> str:
    if num_bytes < 0:
        raise ValueError("Size cannot be negative")
    if num_bytes < 1024:
        return f"{num_bytes} B"
    size = float(num_bytes)
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024
        if round(size, 1) < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
    raise AssertionError("unreachable")


def format_timestamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds).strftime("%Y-%m-%d %H:%M")


CSV_HEADER = ["name", "format", "width", "height", "size_bytes", "modified",
              "sha256", "duplicate", "path"]


def export_csv(items: Iterable[ImageItem], path: str | os.PathLike,
               duplicate_hashes: frozenset[str] | set[str] = frozenset()) -> int:
    """Write the catalogue to a CSV file and return the number of rows written."""
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        for item in items:
            writer.writerow([item.name, item.image_format, item.width, item.height,
                             item.size_bytes, format_timestamp(item.modified), item.sha256,
                             "yes" if item.sha256 in duplicate_hashes else "no", item.path])
            rows += 1
    return rows


SUPPORTED_EXTENSIONS_TEXT = ", ".join(sorted(IMAGE_FORMATS))
