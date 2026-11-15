from __future__ import annotations

from typing import Any, Dict, List

from python_qt_binding import QtCore, QtWidgets

from fabric_experience_gui.storage.database import format_cell


class DecisionSupportWidget(QtWidgets.QWidget):
    def __init__(self, on_open_request=None):
        super().__init__()
        self.request_rows: List[Dict[str, Any]] = []
        self.on_open_request = on_open_request
        self._build_layout()
        self.clear_report()

    def _build_layout(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel('Request Filter'))
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText('Filter by request id, recommendation, or selected mode')
        self.filter_edit.textChanged.connect(self.apply_filter)
        filter_row.addWidget(self.filter_edit, stretch=1)
        layout.addLayout(filter_row)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        self.summary_box = QtWidgets.QPlainTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMaximumHeight(110)
        left_layout.addWidget(self.summary_box)

        self.request_table = QtWidgets.QTableWidget()
        self.request_table.setColumnCount(7)
        self.request_table.setHorizontalHeaderLabels(
            [
                'planning_request_id',
                'recommendation',
                'final_mode',
                'mean_reduction',
                'community_signal',
                'predicted_probability',
                'observed_success',
            ]
        )
        self.request_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.request_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.request_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.request_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.request_table.itemSelectionChanged.connect(self.update_request_details)
        self.request_table.itemDoubleClicked.connect(self.open_selected_request)
        left_layout.addWidget(self.request_table, stretch=1)

        open_button = QtWidgets.QPushButton('Open In Request Review')
        open_button.setToolTip('Open the selected request in Request Review to inspect its audit and plan details.')
        open_button.clicked.connect(self.open_selected_request)
        left_layout.addWidget(open_button)

        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        self.detail_box = QtWidgets.QPlainTextEdit()
        self.detail_box.setReadOnly(True)
        right_layout.addWidget(self.detail_box, stretch=1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    def clear_report(self) -> None:
        self.request_rows = []
        self.filter_edit.clear()
        self.summary_box.setPlainText('Load prompt audits and generated plan feedback artifacts to review request-level decision support.')
        self.request_table.setRowCount(0)
        self.detail_box.setPlainText('No decision-support request selected.')

    def set_report(self, report: Dict[str, Any]) -> None:
        self.request_rows = list(report.get('request_prompt_decision_support', []))
        summary = report.get('summary', {})
        self.summary_box.setPlainText(
            '\n'.join(
                [
                    'Decision Support',
                    f"request_count: {summary.get('request_count', 0)}",
                    f"favor_community: {summary.get('favor_community_count', 0)}",
                    f"favor_detailed: {summary.get('favor_detailed_count', 0)}",
                    f"needs_review: {summary.get('needs_review_count', 0)}",
                    f"with_selected_plan: {summary.get('requests_with_selected_plan', 0)}",
                ]
            )
        )
        self.request_table.setRowCount(len(self.request_rows))
        for row_index, row in enumerate(self.request_rows):
            values = [
                str(row.get('planning_request_id') or ''),
                str(row.get('recommendation') or ''),
                str(row.get('final_selected_mode') or ''),
                str(row.get('mean_prompt_reduction_ratio') or ''),
                str(row.get('community_signal_ratio') or ''),
                str(row.get('selected_predicted_success_probability') or ''),
                str(row.get('selected_observed_success') if row.get('selected_observed_success') is not None else ''),
            ]
            for column_index, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(QtCore.Qt.UserRole, row)
                self.request_table.setItem(row_index, column_index, item)
        self.request_table.resizeColumnsToContents()
        self.apply_filter()
        self.update_request_details()

    def apply_filter(self) -> None:
        needle = self.filter_edit.text().strip().lower()
        first_visible = -1
        for row_index in range(self.request_table.rowCount()):
            item = self.request_table.item(row_index, 0)
            row = item.data(QtCore.Qt.UserRole) if item is not None else {}
            haystack = ' '.join(
                [
                    str(row.get('planning_request_id') or ''),
                    str(row.get('request_uuid') or ''),
                    str(row.get('recommendation') or ''),
                    str(row.get('final_selected_mode') or ''),
                ]
            ).lower()
            hidden = bool(needle) and needle not in haystack
            self.request_table.setRowHidden(row_index, hidden)
            if not hidden and first_visible == -1:
                first_visible = row_index
        if not self.request_table.selectedItems():
            if first_visible >= 0:
                self.request_table.selectRow(first_visible)
            else:
                self.request_table.clearSelection()
                self.request_table.setCurrentCell(-1, -1)
                self.update_request_details()

    def update_request_details(self) -> None:
        selected_items = self.request_table.selectedItems()
        if not selected_items:
            self.detail_box.setPlainText('No decision-support request selected.')
            return
        row = selected_items[0].row()
        item = self.request_table.item(row, 0)
        payload = item.data(QtCore.Qt.UserRole) if item is not None else {}
        if not isinstance(payload, dict):
            self.detail_box.setPlainText('No decision-support request selected.')
            return
        lines = ['Decision Support Request']
        ordered_keys = [
            'planning_request_id',
            'request_uuid',
            'task_description',
            'recommendation',
            'final_selected_mode',
            'iteration_count',
            'community_signal_iteration_count',
            'community_selected_iteration_count',
            'community_signal_ratio',
            'mean_prompt_reduction_ratio',
            'max_prompt_reduction_ratio',
            'selected_candidate_plan_id',
            'selected_graph_hash',
            'selected_predicted_success_probability',
            'selected_predicted_terminal_success_label',
            'selected_terminal_success_estimate',
            'selected_final_rapfs',
            'selected_predicted_success',
            'selected_observed_success',
            'selected_terminal_outcome',
            'selected_human_judgement',
            'selected_candidate_skill_name_list',
            'selected_reasoning',
            'selected_calibration_version',
            'selected_normalizer_version',
            'selected_estimator_version',
            'selected_weight_version',
        ]
        for key in ordered_keys:
            lines.append(f'\n{key}:\n{format_cell(payload.get(key))}')
        self.detail_box.setPlainText('\n'.join(lines))

    def open_selected_request(self) -> None:
        if self.on_open_request is None:
            return
        selected_items = self.request_table.selectedItems()
        if not selected_items:
            return
        row = selected_items[0].row()
        item = self.request_table.item(row, 0)
        payload = item.data(QtCore.Qt.UserRole) if item is not None else {}
        if not isinstance(payload, dict):
            return
        self.on_open_request(
            str(payload.get('planning_request_id') or ''),
            candidate_plan_id=str(payload.get('selected_candidate_plan_id') or ''),
        )


__all__ = ['DecisionSupportWidget']