"""Tests for the Qt table model and the filter/sort proxy."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage

from app.models.image_item import Orientation
from app.models.image_table_model import (
    COL_DIMENSIONS, COL_NAME, COL_SIZE, ITEM_ROLE, ImageFilterProxyModel, ImageTableModel,
)
from tests.conftest import make_item


def thumb():
    image = QImage(16, 12, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    return image


def build():
    model = ImageTableModel()
    model.add_items([
        make_item("beach.png", "h1", 2048, 400, 300, thumbnail=thumb()),
        make_item("tower.jpg", "h2", 500, 300, 900, fmt="JPEG"),
        make_item("beach_copy.png", "h1", 2048, 400, 300),
        make_item("logo.png", "h3", 10, 64, 64),
    ])
    proxy = ImageFilterProxyModel()
    proxy.setSourceModel(model)
    return model, proxy


def names(proxy):
    return [proxy.index(r, COL_NAME).data() for r in range(proxy.rowCount())]


def test_model_rows_and_display():
    model, _ = build()
    assert model.rowCount() == 4
    assert model.columnCount() == 7
    assert model.index(0, COL_NAME).data() == "beach.png"
    assert model.index(0, COL_DIMENSIONS).data() == "400 × 300"
    assert model.index(0, COL_SIZE).data() == "2.0 KB"
    assert model.index(1, 0).data(ITEM_ROLE).name == "tower.jpg"


def test_thumbnail_shown_as_decoration():
    model, _ = build()
    assert model.index(0, COL_NAME).data(Qt.ItemDataRole.DecorationRole) is not None
    assert model.index(1, COL_NAME).data(Qt.ItemDataRole.DecorationRole) is None  # no thumbnail


def test_model_add_and_clear():
    model, _ = build()
    model.add_item(make_item("new.png", "h9"))
    assert model.rowCount() == 5
    model.clear()
    assert model.rowCount() == 0
    assert model.duplicate_hashes == frozenset()


def test_duplicates_are_highlighted():
    model, _ = build()
    model.set_duplicate_hashes({"h1"})
    assert model.index(0, 0).data(Qt.ItemDataRole.BackgroundRole) is not None
    assert model.index(1, 0).data(Qt.ItemDataRole.BackgroundRole) is None


def test_invalid_index_returns_none():
    model, _ = build()
    assert model.index(99, 0).data() is None
    assert model.item_at(-1) is None


def test_proxy_search_orientation_and_duplicate_filters():
    model, proxy = build()
    proxy.set_search_text("BEACH")
    assert sorted(names(proxy)) == ["beach.png", "beach_copy.png"]
    proxy.set_search_text("")
    proxy.set_orientation(Orientation.PORTRAIT)
    assert names(proxy) == ["tower.jpg"]
    proxy.set_orientation(Orientation.SQUARE)
    assert names(proxy) == ["logo.png"]
    proxy.set_orientation(None)
    model.set_duplicate_hashes({"h1"})
    proxy.set_duplicates_only(True)
    assert sorted(names(proxy)) == ["beach.png", "beach_copy.png"]


def test_proxy_sorts_numerically_not_alphabetically():
    _, proxy = build()
    proxy.sort(COL_SIZE, Qt.SortOrder.AscendingOrder)
    assert names(proxy)[:2] == ["logo.png", "tower.jpg"]      # 10 B < 500 B < 2.0 KB
    proxy.sort(COL_DIMENSIONS, Qt.SortOrder.DescendingOrder)
    assert names(proxy)[0] == "tower.jpg"                      # 270,000 px is the largest
