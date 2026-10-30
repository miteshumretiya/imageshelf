"""Create a folder of sample photos (and slideshow music) for demos and testing.

    python tools/make_sample_images.py sample_images              # small test set
    python tools/make_sample_images.py big_images --big 60        # + 60 large 12-megapixel JPEGs

The small set deliberately contains test cases:
  * landscape, portrait and square images (JPEG and PNG),
  * duplicates (identical files under different names/folders),
  * a nested folder (tests "Include sub-folders"),
  * notes.txt (not an image, must be ignored),
  * empty.png (0 bytes) and broken.jpg (random bytes) -> must appear in the Errors tab,
  * tiny.png (1 x 1 pixel, boundary case),
  * music/slideshow_music.wav for the slideshow.
Large images make the scan slow enough to watch the progress bar and test Cancel,
and are used by benchmarks/benchmark.py.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import struct
import sys
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no window needed

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter  # noqa: E402

RATE = 44_100


def make_picture(width: int, height: int, seed: int) -> QImage:
    """Draw an abstract 'photo': a colour gradient with soft circles."""
    rnd = random.Random(seed)
    image = QImage(width, height, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0, QColor.fromHsv(rnd.randrange(360), 170, 245))
    gradient.setColorAt(1, QColor.fromHsv(rnd.randrange(360), 200, 90))
    painter.fillRect(image.rect(), gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    small = min(width, height)
    for _ in range(35):
        painter.setBrush(QColor.fromHsv(rnd.randrange(360), rnd.randrange(60, 255),
                                        rnd.randrange(120, 256), rnd.randrange(50, 170)))
        radius = rnd.randrange(max(2, small // 25), max(3, small // 4))
        painter.drawEllipse(QPoint(rnd.randrange(width), rnd.randrange(height)), radius, radius)
    painter.end()
    return image


def save(image: QImage, path: Path, quality: int = 90) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(path), quality=quality):
        raise OSError(f"Could not write {path}")


def write_music(path: Path, seconds: float = 12.0) -> None:
    """A gentle looping arpeggio (generated, so there are no copyright issues)."""
    notes = [261.63, 329.63, 392.00, 523.25, 392.00, 329.63]
    step = int(RATE * 0.25)
    frames = bytearray()
    for i in range(int(RATE * seconds)):
        freq = notes[(i // step) % len(notes)]
        t = (i % step) / step
        env = min(1.0, t * 20) * (1 - t) ** 1.5
        sample = 0.3 * env * (math.sin(2 * math.pi * freq * i / RATE)
                              + 0.3 * math.sin(4 * math.pi * freq * i / RATE))
        frames += struct.pack("<h", int(32767 * sample))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(bytes(frames))


def make_small_set(root: Path) -> None:
    photos = root / "photos"
    for i in range(6):
        save(make_picture(1600, 1067, seed=i), photos / f"landscape_{i + 1:02d}.jpg")
    for i in range(3):
        save(make_picture(900, 1350, seed=100 + i), photos / f"portrait_{i + 1:02d}.jpg")
    for i in range(2):
        save(make_picture(1000, 1000, seed=200 + i), photos / f"square_{i + 1:02d}.png")
    save(make_picture(1200, 800, seed=300), root / "holiday" / "2024" / "beach.jpg")
    save(make_picture(800, 1200, seed=301), root / "holiday" / "2024" / "sunset.jpg")
    save(make_picture(1, 1, seed=400), root / "photos" / "tiny.png")

    # duplicates: identical content, different names/folders
    (root / "backup").mkdir(exist_ok=True)
    shutil.copy(photos / "landscape_01.jpg", root / "backup" / "landscape_01 (copy).jpg")
    shutil.copy(photos / "landscape_01.jpg", root / "holiday" / "IMG_0001.jpg")
    shutil.copy(photos / "portrait_02.jpg", root / "backup" / "portrait_02_old.jpg")

    # edge cases
    (root / "notes.txt").write_text("Not an image - ImageShelf should ignore this file.\n")
    (root / "photos" / "empty.png").write_bytes(b"")
    (root / "photos" / "broken.jpg").write_bytes(os.urandom(5000))

    write_music(root / "music" / "slideshow_music.wav")


def make_big_set(root: Path, count: int) -> None:
    folder = root / "large"
    for i in range(count):
        save(make_picture(4000, 3000, seed=1000 + i), folder / f"IMG_{i + 1:04d}.jpg", quality=92)
        print(f"  large/IMG_{i + 1:04d}.jpg", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", help="where to create the sample images")
    parser.add_argument("--big", type=int, default=0,
                        help="number of large 4000x3000 JPEGs to add")
    parser.add_argument("--only-big", action="store_true", help="skip the small test set")
    args = parser.parse_args()

    app = QGuiApplication(sys.argv[:1])  # noqa: F841 - QPainter needs an application object
    root = Path(args.folder)
    if not args.only_big:
        make_small_set(root)
    if args.big:
        print(f"Creating {args.big} large images (this takes a little while)…")
        make_big_set(root, args.big)
    print(f"Sample images created in {root.resolve()}")


if __name__ == "__main__":
    main()
