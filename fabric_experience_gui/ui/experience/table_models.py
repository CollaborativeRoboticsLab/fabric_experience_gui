from __future__ import annotations

import json
from typing import Any, Dict, List

from python_qt_binding import QtCore

from fabric_experience_gui.storage import TableSnapshot, format_cell


class SnapshotTableModel(QtCore.QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self.snapshot = TableSnapshot(name='', columns=[], rows=[])

    def set_snapshot(self, snapshot: TableSnapshot) -> None:
        self.beginResetModel()
        self.snapshot = snapshot
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        del parent
        return len(self.snapshot.rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        del parent
        return len(self.snapshot.columns)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self.snapshot.rows[index.row()]
        column_name = self.snapshot.columns[index.column()]
        value = row.get(column_name, '')
        if role == QtCore.Qt.DisplayRole:
            return self._compact_value(value)
        if role == QtCore.Qt.ToolTipRole:
            return format_cell(value)
        if role == QtCore.Qt.UserRole:
            return index.row()
        if role == QtCore.Qt.UserRole + 1:
            return self._sortable_value(value)
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole) -> Any:
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            if 0 <= section < len(self.snapshot.columns):
                return self.snapshot.columns[section]
            return None
        return section + 1

    def row_dict(self, row_index: int) -> Dict[str, Any]:
        if 0 <= row_index < len(self.snapshot.rows):
            return self.snapshot.rows[row_index]
        return {}

    @staticmethod
    def _compact_value(value: Any) -> str:
        text = format_cell(value)
        return text if len(text) <= 80 else text[:77] + '...'

    @staticmethod
    def _sortable_value(value: Any) -> Any:
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, list):
            return json.dumps(value, sort_keys=True)
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True)
        if value is None:
            return ''
        text = str(value)
        try:
            return float(text)
        except ValueError:
            return text.lower()


class SnapshotFilterProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.primary_column = 'All columns'
        self.primary_text = ''
        self.secondary_column = 'All columns'
        self.secondary_text = ''
        self.setDynamicSortFilter(True)

    def set_primary_filter(self, column_name: str, text: str) -> None:
        self.primary_column = column_name
        self.primary_text = text.strip().lower()
        self.invalidateFilter()

    def set_secondary_filter(self, column_name: str, text: str) -> None:
        self.secondary_column = column_name
        self.secondary_text = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:
        del source_parent
        model = self.sourceModel()
        if not isinstance(model, SnapshotTableModel):
            return True
        row = model.row_dict(source_row)
        columns = model.snapshot.columns
        return self._row_matches(row, columns, self.primary_column, self.primary_text) and self._row_matches(
            row, columns, self.secondary_column, self.secondary_text,
        )

    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:
        left_value = left.data(QtCore.Qt.UserRole + 1)
        right_value = right.data(QtCore.Qt.UserRole + 1)
        try:
            return left_value < right_value
        except TypeError:
            return str(left_value) < str(right_value)

    @staticmethod
    def _row_matches(row: Dict[str, Any], columns: List[str], column_name: str, needle: str) -> bool:
        if not needle:
            return True
        if column_name == 'All columns':
            values = [SnapshotTableModel._compact_value(row.get(name, '')).lower() for name in columns]
            return any(needle in value for value in values)
        return needle in SnapshotTableModel._compact_value(row.get(column_name, '')).lower()