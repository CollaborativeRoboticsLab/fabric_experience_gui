from __future__ import annotations

from typing import Any, Dict, List

from python_qt_binding import QtCore, QtWidgets

from fabric_experience_gui.storage.database import format_cell


class CalibrationReviewWidget(QtWidgets.QWidget):
    def __init__(self, on_open_request=None):
        super().__init__()
        self.threshold_rows: List[Dict[str, Any]] = []
        self.sample_rows: List[Dict[str, Any]] = []
        self.proposal: Dict[str, Any] = {}
        self.on_open_request = on_open_request
        self._build_layout()
        self.clear_report()

    def _build_layout(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        self.summary_box = QtWidgets.QPlainTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMaximumHeight(120)
        layout.addWidget(self.summary_box)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.addWidget(QtWidgets.QLabel('Threshold Candidates'))
        self.threshold_table = QtWidgets.QTableWidget()
        self.threshold_table.setColumnCount(5)
        self.threshold_table.setHorizontalHeaderLabels(['threshold', 'balanced_accuracy', 'accuracy', 'f1', 'false_positive'])
        self.threshold_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.threshold_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.threshold_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.threshold_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.threshold_table.itemSelectionChanged.connect(self.update_threshold_details)
        left_layout.addWidget(self.threshold_table, stretch=1)

        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        proposal_panel = QtWidgets.QWidget()
        proposal_layout = QtWidgets.QVBoxLayout(proposal_panel)
        proposal_layout.addWidget(QtWidgets.QLabel('Proposal / Threshold Details'))
        self.detail_box = QtWidgets.QPlainTextEdit()
        self.detail_box.setReadOnly(True)
        proposal_layout.addWidget(self.detail_box, stretch=1)

        sample_panel = QtWidgets.QWidget()
        sample_layout = QtWidgets.QVBoxLayout(sample_panel)
        sample_layout.addWidget(QtWidgets.QLabel('Observed Samples'))
        self.sample_table = QtWidgets.QTableWidget()
        self.sample_table.setColumnCount(7)
        self.sample_table.setHorizontalHeaderLabels([
            'planning_request_id',
            'candidate_plan_id',
            'final_rapfs',
            'predicted_probability',
            'calibrated_label',
            'observed_success',
            'terminal_outcome',
        ])
        self.sample_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.sample_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.sample_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.sample_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.sample_table.itemDoubleClicked.connect(self.open_selected_sample_request)
        sample_layout.addWidget(self.sample_table, stretch=1)

        open_button = QtWidgets.QPushButton('Open Sample In Request Review')
        open_button.clicked.connect(self.open_selected_sample_request)
        sample_layout.addWidget(open_button)

        right_splitter.addWidget(proposal_panel)
        right_splitter.addWidget(sample_panel)
        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 2)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_splitter)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        layout.addWidget(splitter)

    def clear_report(self) -> None:
        self.threshold_rows = []
        self.sample_rows = []
        self.proposal = {}
        self.calibration_metadata = {}
        self.runtime_policy_update = {}
        self.summary_box.setPlainText('Load a GraphRAG database and generated plan feedback artifacts to review offline terminal-success threshold analysis.')
        self.threshold_table.setRowCount(0)
        self.sample_table.setRowCount(0)
        self.detail_box.setPlainText('No calibration analysis loaded.')

    def set_report(self, report: Dict[str, Any]) -> None:
        summary = report.get('summary', {})
        self.proposal = dict(report.get('proposal', {}))
        self.calibration_metadata = dict(report.get('calibration_metadata', {}))
        self.runtime_policy_update = dict(report.get('runtime_policy_update', {}))
        self.threshold_rows = list(report.get('threshold_candidates', []))
        self.sample_rows = list(report.get('samples', []))
        self.summary_box.setPlainText(
            '\n'.join(
                [
                    'Calibration Review',
                    f"sample_count: {summary.get('sample_count', 0)}",
                    f"observed_success_count: {summary.get('observed_success_count', 0)}",
                    f"observed_failure_count: {summary.get('observed_failure_count', 0)}",
                    f"candidate_threshold_count: {summary.get('candidate_threshold_count', 0)}",
                    f"recommended_success_threshold: {summary.get('recommended_success_threshold')}",
                    f"recommended_failure_threshold: {summary.get('recommended_failure_threshold')}",
                    f"best_single_threshold: {summary.get('best_single_threshold')}",
                    f"calibration_label_version: {summary.get('calibration_label_version', '')}",
                    f"calibration_band_mode: {summary.get('calibration_band_mode', '')}",
                ]
            )
        )

        self.threshold_table.setRowCount(len(self.threshold_rows))
        for row_index, row in enumerate(self.threshold_rows):
            values = [
                str(row.get('threshold') or ''),
                str(row.get('balanced_accuracy') or ''),
                str(row.get('accuracy') or ''),
                str(row.get('f1') or ''),
                str(row.get('false_positive') or ''),
            ]
            for column_index, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(QtCore.Qt.UserRole, row)
                self.threshold_table.setItem(row_index, column_index, item)
        self.threshold_table.resizeColumnsToContents()

        self.sample_table.setRowCount(len(self.sample_rows))
        for row_index, row in enumerate(self.sample_rows):
            values = [
                str(row.get('planning_request_id') or ''),
                str(row.get('candidate_plan_id') or ''),
                str(row.get('final_rapfs') or ''),
                str(row.get('predicted_success_probability') or ''),
                str(row.get('calibrated_terminal_success_label') or ''),
                str(row.get('observed_success') or ''),
                str(row.get('terminal_outcome') or ''),
            ]
            for column_index, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(QtCore.Qt.UserRole, row)
                self.sample_table.setItem(row_index, column_index, item)
        self.sample_table.resizeColumnsToContents()

        if self.threshold_rows:
            self.threshold_table.selectRow(0)
            self.update_threshold_details()
        else:
            self.detail_box.setPlainText('No threshold candidates available.')

    def update_threshold_details(self) -> None:
        selected_items = self.threshold_table.selectedItems()
        if not selected_items:
            self.detail_box.setPlainText('No threshold candidate selected.')
            return
        row_index = selected_items[0].row()
        item = self.threshold_table.item(row_index, 0)
        payload = item.data(QtCore.Qt.UserRole) if item is not None else {}
        if not isinstance(payload, dict):
            self.detail_box.setPlainText('No threshold candidate selected.')
            return
        lines = ['Calibration Threshold Candidate', '', 'Calibration Metadata']
        for key, value in self.calibration_metadata.items():
            lines.append(f'\n{key}:\n{format_cell(value)}')
        lines.append('\nRuntime Policy Update')
        for key, value in self.runtime_policy_update.items():
            lines.append(f'\n{key}:\n{format_cell(value)}')
        lines.append('\nProposal')
        for key, value in self.proposal.items():
            lines.append(f'\n{key}:\n{format_cell(value)}')
        lines.append('\nCandidate')
        for key, value in payload.items():
            lines.append(f'\n{key}:\n{format_cell(value)}')
        self.detail_box.setPlainText('\n'.join(lines))

    def open_selected_sample_request(self) -> None:
        if self.on_open_request is None:
            return
        selected_items = self.sample_table.selectedItems()
        if not selected_items:
            return
        row_index = selected_items[0].row()
        item = self.sample_table.item(row_index, 0)
        payload = item.data(QtCore.Qt.UserRole) if item is not None else {}
        if not isinstance(payload, dict):
            return
        self.on_open_request(
            str(payload.get('planning_request_id') or ''),
            candidate_plan_id=str(payload.get('candidate_plan_id') or ''),
        )


__all__ = ['CalibrationReviewWidget']