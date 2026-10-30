"""Qt model/view layer: exposes ImageItem objects to the shelf (grid) and the details table.

One ImageTableModel feeds BOTH views through one ImageFilterProxyModel, so searching,
filtering, sorting and selection stay in sync. The filtering rule itself lives in
image_service.matches_filter() so it can be unit-tested without Qt views.
"""
from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QBrush, QColor, QIcon, QPixmap

from app.models.image_item import ImageItem, Orientation
from app.services.image_service import format_size, format_timestamp, matches_filter

COLUMNS = ("Name", "Dimensions", "Format", "Size", "Modified", "SHA-256", "Folder")
(COL_NAME, COL_DIMENSIONS, COL_FORMAT, COL_SIZE, COL_MODIFIED, COL_HASH,
 COL_FOLDER) = range(len(COLUMNS))

ITEM_ROLE = Qt.ItemDataRole.UserRole          # returns the ImageItem itself
SORT_ROLE = Qt.ItemDataRole.UserRole + 1      # returns a value that sorts correctly

DUPLICATE_BG = QColor(255, 214, 153)
DUPLICATE_FG = QColor(40, 40, 40)


class ImageTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[ImageItem] = []
        self._duplicate_hashes: frozenset[str] = frozenset()
        self._icons: dict[str, QIcon] = {}   # thumbnail icons, created lazily in the GUI thread

    # ---- required Qt overrides -------------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        column = index.column()
        is_duplicate = item.sha256 in self._duplicate_hashes

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(item, column)
        if role == Qt.ItemDataRole.DecorationRole and column == COL_NAME:
            return self._icon_for(item)
        if role == SORT_ROLE:
            return self._sort_value(item, column)
        if role == ITEM_ROLE:
            return item
        if role == Qt.ItemDataRole.ToolTipRole:
            tip = f"{item.path}\n{item.dimensions} · {format_size(item.size_bytes)}"
            return tip + ("\nDuplicate: another image has identical content." if is_duplicate else "")
        if role == Qt.ItemDataRole.BackgroundRole and is_duplicate:
            return QBrush(DUPLICATE_BG)
        if role == Qt.ItemDataRole.ForegroundRole and is_duplicate:
            return QBrush(DUPLICATE_FG)
        if role == Qt.ItemDataRole.TextAlignmentRole and column == COL_SIZE:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    # ---- helpers -----------------------------------------------------------------------
    def _icon_for(self, item: ImageItem) -> QIcon | None:
        if item.thumbnail is None or item.thumbnail.isNull():
            return None
        icon = self._icons.get(item.path)
        if icon is None:  # QPixmap/QIcon must be created in the GUI thread - data() runs there
            icon = QIcon(QPixmap.fromImage(item.thumbnail))
            self._icons[item.path] = icon
        return icon

    @staticmethod
    def _display_value(item: ImageItem, column: int) -> str:
        return {
            COL_NAME: item.name,
            COL_DIMENSIONS: item.dimensions,
            COL_FORMAT: item.image_format,
            COL_SIZE: format_size(item.size_bytes),
            COL_MODIFIED: format_timestamp(item.modified),
            COL_HASH: item.sha256[:12] + "…",
            COL_FOLDER: item.folder,
        }[column]

    @staticmethod
    def _sort_value(item: ImageItem, column: int):
        return {
            COL_NAME: item.name.lower(),
            COL_DIMENSIONS: item.width * item.height,
            COL_FORMAT: item.image_format,
            COL_SIZE: item.size_bytes,
            COL_MODIFIED: item.modified,
            COL_HASH: item.sha256,
            COL_FOLDER: item.folder.lower(),
        }[column]

    # ---- public API used by the controller (always called in the GUI thread) ------------
    def add_item(self, item: ImageItem) -> None:
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(item)
        self.endInsertRows()

    def add_items(self, items: Iterable[ImageItem]) -> None:
        items = list(items)
        if not items:
            return
        first = len(self._items)
        self.beginInsertRows(QModelIndex(), first, first + len(items) - 1)
        self._items.extend(items)
        self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self._items.clear()
        self._icons.clear()
        self._duplicate_hashes = frozenset()
        self.endResetModel()

    def set_duplicate_hashes(self, hashes: Iterable[str]) -> None:
        self._duplicate_hashes = frozenset(hashes)
        if self._items:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._items) - 1, len(COLUMNS) - 1))

    @property
    def duplicate_hashes(self) -> frozenset[str]:
        return self._duplicate_hashes

    def item_at(self, row: int) -> ImageItem | None:
        return self._items[row] if 0 <= row < len(self._items) else None

    def items(self) -> list[ImageItem]:
        return list(self._items)


class ImageFilterProxyModel(QSortFilterProxyModel):
    """Sorts by real values (bytes, pixels, timestamps) and applies the search filters."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self._text = ""
        self._orientation: Orientation | None = None
        self._duplicates_only = False

    def set_search_text(self, text: str) -> None:
        self._text = text
        self.refresh()

    def set_orientation(self, orientation: Orientation | None) -> None:
        self._orientation = orientation
        self.refresh()

    def set_duplicates_only(self, enabled: bool) -> None:
        self._duplicates_only = enabled
        self.refresh()

    def refresh(self) -> None:
        # Qt 6.10+ replaced invalidateFilter() with begin/endFilterChange().
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source: ImageTableModel = self.sourceModel()
        item = source.item_at(source_row)
        if item is None:
            return False
        return matches_filter(item, self._text, self._orientation,
                              self._duplicates_only, source.duplicate_hashes)
