"""Unit tests for the processing logic in app/services/image_service.py.

Each group covers normal, boundary, invalid and exceptional conditions.
The test IDs in comments (AT-xx) match docs/test_plan.md.
"""
import csv
import hashlib
import threading

import pytest

from app.models.image_item import Orientation, image_format, orientation_of
from app.services import image_service as svc
from tests.conftest import make_item, write_image


# --------------------------------------------------------------- AT-01 image_format()
@pytest.mark.parametrize("name, expected", [
    ("photo.jpg", "JPEG"), ("PHOTO.JPEG", "JPEG"),   # case-insensitive
    ("logo.png", "PNG"), ("scan.tiff", "TIFF"),
    ("notes.txt", None), ("song.mp3", None), ("no_extension", None), ("photo.jpg.bak", None),
])
def test_image_format(name, expected):
    assert image_format(name) == expected


# --------------------------------------------------------------- AT-02 orientation_of()
@pytest.mark.parametrize("w, h, expected", [
    (4000, 3000, Orientation.LANDSCAPE), (3000, 4000, Orientation.PORTRAIT),
    (500, 500, Orientation.SQUARE), (1, 1, Orientation.SQUARE),          # boundary
    (2, 1, Orientation.LANDSCAPE), (1, 2, Orientation.PORTRAIT),         # boundary
])
def test_orientation(w, h, expected):
    assert orientation_of(w, h) == expected


@pytest.mark.parametrize("w, h", [(0, 10), (10, 0), (-1, 5)])
def test_orientation_invalid_dimensions(w, h):
    with pytest.raises(ValueError):
        orientation_of(w, h)


# --------------------------------------------------------------- AT-03 validate_folder()
def test_validate_folder_accepts_existing_folder(tmp_path):
    assert svc.validate_folder(str(tmp_path)) == tmp_path


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_validate_folder_rejects_empty_input(bad):
    with pytest.raises(ValueError, match="choose a folder"):
        svc.validate_folder(bad)


def test_validate_folder_rejects_missing_folder(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        svc.validate_folder(tmp_path / "missing")


def test_validate_folder_rejects_a_file(tmp_path):
    file_path = tmp_path / "file.png"
    file_path.write_bytes(b"x")
    with pytest.raises(ValueError, match="not a folder"):
        svc.validate_folder(file_path)


# --------------------------------------------------------------- AT-04 scan_folder()
def test_scan_folder_recursive_finds_only_images(image_folder):
    names = [p.name for p in svc.scan_folder(image_folder, recursive=True)]
    assert names == ["a.png", "b.png", "broken.jpg", "c.jpg", "d.png", "empty.png"]


def test_scan_folder_non_recursive_skips_subfolders(image_folder):
    names = [p.name for p in svc.scan_folder(image_folder, recursive=False)]
    assert names == ["a.png", "b.png", "broken.jpg", "c.jpg"]


def test_scan_folder_empty_folder_returns_empty_list(tmp_path):
    assert svc.scan_folder(tmp_path) == []


def test_scan_folder_respects_max_size(image_folder):
    names = [p.name for p in svc.scan_folder(image_folder, max_size_bytes=1000)]
    assert "broken.jpg" not in names       # 2000 bytes > limit
    assert "empty.png" in names            # 0 bytes <= limit


# --------------------------------------------------------------- AT-05 compute_sha256()
def test_sha256_matches_hashlib(tmp_path):
    f = tmp_path / "x.png"
    f.write_bytes(b"hello")
    assert svc.compute_sha256(f) == hashlib.sha256(b"hello").hexdigest()


@pytest.mark.parametrize("size", [0, 9, 10, 11, 25])  # around the chunk boundary
def test_sha256_correct_across_chunk_boundaries(tmp_path, size):
    data = bytes(range(size))
    f = tmp_path / "data.png"
    f.write_bytes(data)
    assert svc.compute_sha256(f, chunk_size=10) == hashlib.sha256(data).hexdigest()


def test_sha256_invalid_chunk_size(tmp_path):
    f = tmp_path / "x.png"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        svc.compute_sha256(f, chunk_size=0)


def test_sha256_stops_when_cancelled(tmp_path):
    f = tmp_path / "big.png"
    f.write_bytes(b"x" * 100)
    event = threading.Event()
    event.set()
    with pytest.raises(svc.ScanCancelled):
        svc.compute_sha256(f, chunk_size=10, cancel_event=event)


# --------------------------------------------------------------- AT-06 analyse_file()
def test_analyse_file_reads_size_and_makes_thumbnail(tmp_path):
    path = write_image(tmp_path / "wide.png", 800, 400)
    item = svc.analyse_file(path)
    assert (item.width, item.height) == (800, 400)
    assert item.image_format == "PNG"
    assert item.orientation == Orientation.LANDSCAPE
    assert len(item.sha256) == 64
    assert (item.thumbnail.width(), item.thumbnail.height()) == (160, 80)


def test_analyse_file_empty_file(image_folder):
    with pytest.raises(ValueError, match="empty"):
        svc.analyse_file(image_folder / "sub" / "empty.png")


def test_analyse_file_damaged_image(image_folder):
    with pytest.raises(ValueError, match="readable"):
        svc.analyse_file(image_folder / "broken.jpg")


def test_analyse_file_missing_file(tmp_path):
    with pytest.raises(OSError):
        svc.analyse_file(tmp_path / "gone.png")


def test_analyse_file_unsupported_type(image_folder):
    with pytest.raises(ValueError, match="Unsupported"):
        svc.analyse_file(image_folder / "notes.txt")


# --------------------------------------------------------------- AT-07 duplicates / summary
def test_find_duplicates_groups_identical_hashes():
    items = [make_item("a.png", "h1"), make_item("b.png", "h1"), make_item("c.png", "h2")]
    groups = svc.find_duplicates(items)
    assert list(groups) == ["h1"]
    assert [i.name for i in groups["h1"]] == ["a.png", "b.png"]


def test_find_duplicates_none_when_unique_or_empty():
    assert svc.find_duplicates([make_item("a", "1"), make_item("b", "2")]) == {}
    assert svc.find_duplicates([]) == {}


def test_build_summary_counts_and_wasted_space():
    items = [make_item("a.png", "h1", 100), make_item("b.png", "h1", 100),
             make_item("c.png", "h1", 100),
             make_item("d.jpg", "h2", 50, width=300, height=400, fmt="JPEG")]
    s = svc.build_summary("/photos", items, error_count=2, elapsed_seconds=1.5, cancelled=False)
    assert s.total_images == 4
    assert s.total_bytes == 350
    assert s.counts_by_format == {"JPEG": 1, "PNG": 3}
    assert s.counts_by_orientation == {"Landscape": 3, "Portrait": 1, "Square": 0}
    assert (s.duplicate_groups, s.duplicate_images) == (1, 3)
    assert s.wasted_bytes == 200          # two extra copies of a 100-byte file
    assert s.error_count == 2
    assert s.total_megapixels == pytest.approx(3 * 0.12 + 0.12)


# --------------------------------------------------------------- AT-08 matches_filter()
def test_matches_filter_text_orientation_and_duplicates():
    item = make_item("Holiday.PNG", "h1", width=400, height=300)
    assert svc.matches_filter(item)
    assert svc.matches_filter(item, text="holi")                  # case-insensitive
    assert not svc.matches_filter(item, text="beach")
    assert svc.matches_filter(item, orientation=Orientation.LANDSCAPE)
    assert not svc.matches_filter(item, orientation=Orientation.PORTRAIT)
    assert svc.matches_filter(item, duplicates_only=True, duplicate_hashes={"h1"})
    assert not svc.matches_filter(item, duplicates_only=True, duplicate_hashes={"h2"})


# --------------------------------------------------------------- AT-09 format_size()
@pytest.mark.parametrize("num, expected", [
    (0, "0 B"), (1023, "1023 B"), (1024, "1.0 KB"), (1536, "1.5 KB"),
    (1024 ** 2 - 1, "1.0 MB"), (1024 ** 2, "1.0 MB"), (5 * 1024 ** 3, "5.0 GB"),
])
def test_format_size_boundaries(num, expected):
    assert svc.format_size(num) == expected


def test_format_size_negative_rejected():
    with pytest.raises(ValueError):
        svc.format_size(-1)


# --------------------------------------------------------------- AT-10 settings validation
@pytest.mark.parametrize("text, expected", [("", None), ("  ", None), ("1", 1), (" 250 ", 250),
                                            ("100000", 100000)])
def test_validate_max_size_valid(text, expected):
    assert svc.validate_max_size_mb(text) == expected


@pytest.mark.parametrize("text", ["abc", "1.5", "0", "-5", "100001"])
def test_validate_max_size_invalid(text):
    with pytest.raises(ValueError):
        svc.validate_max_size_mb(text)


@pytest.mark.parametrize("value, ok", [(1, True), (32, True), (0, False), (33, False),
                                       (True, False), ("4", False)])
def test_validate_worker_count(value, ok):
    if ok:
        assert svc.validate_worker_count(value) == value
    else:
        with pytest.raises(ValueError):
            svc.validate_worker_count(value)


# --------------------------------------------------------------- AT-11 validate_music_file()
def test_validate_music_file_accepts_wav(tmp_path):
    music = tmp_path / "song.wav"
    music.write_bytes(b"RIFF")
    assert svc.validate_music_file(str(music)) == music


def test_validate_music_file_rejects_wrong_type(tmp_path):
    picture = tmp_path / "photo.jpg"
    picture.write_bytes(b"x")
    with pytest.raises(ValueError, match="not a supported audio file"):
        svc.validate_music_file(str(picture))


@pytest.mark.parametrize("bad", ["", None])
def test_validate_music_file_rejects_empty(bad):
    with pytest.raises(ValueError):
        svc.validate_music_file(bad)


def test_validate_music_file_rejects_missing(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        svc.validate_music_file(str(tmp_path / "missing.mp3"))


# --------------------------------------------------------------- AT-12 export_csv()
def test_export_csv_writes_header_and_rows(tmp_path):
    items = [make_item("a.png", "h1"), make_item("b.png", "h1"), make_item("c.png", "h2")]
    out = tmp_path / "report.csv"
    assert svc.export_csv(items, out, duplicate_hashes={"h1"}) == 3
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows[0] == svc.CSV_HEADER
    assert [r[0] for r in rows[1:]] == ["a.png", "b.png", "c.png"]
    assert [r[7] for r in rows[1:]] == ["yes", "yes", "no"]


def test_export_csv_to_missing_folder_raises(tmp_path):
    with pytest.raises(OSError):
        svc.export_csv([make_item()], tmp_path / "no_such_folder" / "out.csv")
