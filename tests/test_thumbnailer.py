"""Tests for thumbnail sizing and image reading (app/services/thumbnailer.py)."""
import pytest

from app.services.thumbnailer import fit_within, load_full_image, read_image_info
from tests.conftest import write_image


@pytest.mark.parametrize("w, h, max_side, expected", [
    (4000, 3000, 160, (160, 120)),     # landscape
    (3000, 4000, 160, (120, 160)),     # portrait
    (500, 500, 160, (160, 160)),       # square
    (100, 50, 160, (100, 50)),         # already small: never enlarged
    (160, 160, 160, (160, 160)),       # exactly at the limit
    (1, 1, 160, (1, 1)),               # smallest possible image
    (10000, 10, 160, (160, 1)),        # very thin: height never below 1
])
def test_fit_within(w, h, max_side, expected):
    assert fit_within(w, h, max_side) == expected


@pytest.mark.parametrize("args", [(0, 10, 160), (10, 0, 160), (10, 10, 0)])
def test_fit_within_rejects_invalid(args):
    with pytest.raises(ValueError):
        fit_within(*args)


def test_read_image_info_real_size_and_thumbnail(tmp_path):
    path = write_image(tmp_path / "tall.jpg", 300, 900)
    info = read_image_info(path, max_side=90)
    assert (info.width, info.height) == (300, 900)
    assert (info.thumbnail.width(), info.thumbnail.height()) == (30, 90)


def test_read_image_info_rejects_non_image(tmp_path):
    path = tmp_path / "fake.png"
    path.write_bytes(b"this is not a png")
    with pytest.raises(ValueError):
        read_image_info(path)


def test_load_full_image(tmp_path):
    path = write_image(tmp_path / "x.png", 64, 32)
    image = load_full_image(path)
    assert (image.width(), image.height()) == (64, 32)


def test_load_full_image_missing_file(tmp_path):
    with pytest.raises(ValueError):
        load_full_image(tmp_path / "missing.png")
