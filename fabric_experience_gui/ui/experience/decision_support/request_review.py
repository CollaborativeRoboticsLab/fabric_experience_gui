from __future__ import annotations

from typing import Any, Dict, List

from python_qt_binding import QtCore, QtWidgets

from fabric_experience_gui.storage.database import format_cell


class RequestReviewWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.request_records: Dict[str, Dict[str, Any]] = {}
        self.current_request_key = ''
        self._build_layout()
        self.clear_review()

    def _build_layout(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel('Request Filter'))
        self.request_filter_edit = QtWidgets.QLineEdit()
        self.request_filter_edit.setPlaceholderText('Filter by planning request id or request uuid')
        self.request_filter_edit.textChanged.connect(self.apply_filter)
        filter_row.addWidget(self.request_filter_edit, stretch=1)
        left_layout.addLayout(filter_row)

        self.request_list = QtWidgets.QListWidget()
        self.request_list.currentItemChanged.connect(self.update_request_details)
        left_layout.addWidget(self.request_list, stretch=1)

        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        top_panel = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(top_panel)
        self.summary_box = QtWidgets.QPlainTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMaximumHeight(120)
        top_layout.addWidget(self.summary_box)

        self.audit_box = QtWidgets.QPlainTextEdit()
        self.audit_box.setReadOnly(True)
        top_layout.addWidget(self.audit_box, stretch=1)

        bottom_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        explanation_panel = QtWidgets.QWidget()
        explanation_layout = QtWidgets.QVBoxLayout(explanation_panel)
        explanation_layout.addWidget(QtWidgets.QLabel('Persisted Node Explanations'))
        self.explanation_table = QtWidgets.QTableWidget()
        self.explanation_table.setColumnCount(4)
        self.explanation_table.setHorizontalHeaderLabels(['candidate_node_id', 'skill_name', 'fallback_level', 'reason'])
        self.explanation_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.explanation_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.explanation_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.explanation_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.explanation_table.itemSelectionChanged.connect(self.update_explanation_preview)
        explanation_layout.addWidget(self.explanation_table, stretch=2)
        self.explanation_preview = QtWidgets.QPlainTextEdit()
        self.explanation_preview.setReadOnly(True)
        explanation_layout.addWidget(self.explanation_preview, stretch=1)

        generated_panel = QtWidgets.QWidget()
        generated_layout = QtWidgets.QVBoxLayout(generated_panel)
        generated_layout.addWidget(QtWidgets.QLabel('Selected Generated Plan Snapshot'))
        self.generated_plan_box = QtWidgets.QPlainTextEdit()
        self.generated_plan_box.setReadOnly(True)
        generated_layout.addWidget(self.generated_plan_box, stretch=1)

        bottom_splitter.addWidget(explanation_panel)
        bottom_splitter.addWidget(generated_panel)
        bottom_splitter.setStretchFactor(0, 3)
        bottom_splitter.setStretchFactor(1, 2)

        right_splitter.addWidget(top_panel)
        right_splitter.addWidget(bottom_splitter)
        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 3)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_splitter)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)

        layout.addWidget(splitter)

    def clear_review(self) -> None:
        self.request_records = {}
        self.current_request_key = ''
        self.request_list.clear()
        self.summary_box.setPlainText('Load prompt audits and a GraphRAG database to review requests end to end.')
        self.audit_box.setPlainText('No prompt-audit request selected.')
        self.explanation_table.setRowCount(0)
        self.explanation_preview.setPlainText('No node explanation selected.')
        self.generated_plan_box.setPlainText('No generated plan artifact loaded.')

    def set_request_records(self, records: List[Dict[str, Any]]) -> None:
        self.request_records = {str(record['request_key']): record for record in records}
        self.request_list.clear()
        for record in records:
            request_key = str(record['request_key'])
            label = request_key
            request_uuid = str(record.get('request_uuid') or '')
            if request_uuid and request_uuid != request_key:
                label = f'{request_key} ({request_uuid})'
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.UserRole, request_key)
            self.request_list.addItem(item)
        self.apply_filter()
        first_visible = self.first_visible_item()
        if first_visible is not None:
            self.request_list.setCurrentItem(first_visible)
        else:
            self.clear_review()

    def select_request(self, request_id: str, candidate_plan_id: str = '', candidate_node_id: str = '') -> bool:
        needle = str(request_id or '').strip()
        if not needle:
            return False
        for index in range(self.request_list.count()):
            item = self.request_list.item(index)
            request_key = str(item.data(QtCore.Qt.UserRole))
            record = self.request_records.get(request_key, {})
            if needle in {request_key, str(record.get('planning_request_id') or ''), str(record.get('request_uuid') or '')}:
                item.setHidden(False)
                self.request_list.setCurrentItem(item)
                self.update_request_details(item)
                if candidate_plan_id:
                    self.select_generated_plan(candidate_plan_id)
                if candidate_node_id:
                    self.select_explanation(candidate_node_id)
                return True
        return False

    def apply_filter(self) -> None:
        needle = self.request_filter_edit.text().strip().lower()
        for index in range(self.request_list.count()):
            item = self.request_list.item(index)
            request_key = str(item.data(QtCore.Qt.UserRole))
            record = self.request_records.get(request_key, {})
            haystack = ' '.join(
                [
                    request_key,
                    str(record.get('planning_request_id') or ''),
                    str(record.get('request_uuid') or ''),
                ]
            ).lower()
            item.setHidden(bool(needle) and needle not in haystack)

    def update_request_details(self, current: QtWidgets.QListWidgetItem | None, previous: QtWidgets.QListWidgetItem | None = None) -> None:
        del previous
        if current is None:
            self.current_request_key = ''
            self.summary_box.setPlainText('No request selected.')
            self.audit_box.setPlainText('No prompt-audit request selected.')
            self.explanation_table.setRowCount(0)
            self.explanation_preview.setPlainText('No node explanation selected.')
            self.generated_plan_box.setPlainText('No generated plan artifact loaded.')
            return

        request_key = str(current.data(QtCore.Qt.UserRole))
        self.current_request_key = request_key
        record = self.request_records.get(request_key, {})

        self.summary_box.setPlainText('\n'.join(self._summary_lines(record)))
        self.audit_box.setPlainText(self._audit_text(record))
        self.generated_plan_box.setPlainText(self._generated_plan_text(record))
        self._populate_explanation_table(record.get('node_explanations', []))

    def select_generated_plan(self, candidate_plan_id: str) -> bool:
        needle = str(candidate_plan_id or '').strip()
        if not needle:
            return False
        record = self.request_records.get(self.current_request_key, {})
        generated_plans = record.get('generated_plans', [])
        for plan in generated_plans:
            if needle in {str(plan.get('candidate_plan_id') or ''), str(plan.get('plan_key') or '')}:
                self.generated_plan_box.setPlainText(self._generated_plan_text(record, plan))
                return True
        return False

    def select_explanation(self, candidate_node_id: str) -> bool:
        needle = str(candidate_node_id or '').strip()
        if not needle:
            return False
        for row_index in range(self.explanation_table.rowCount()):
            item = self.explanation_table.item(row_index, 0)
            payload = item.data(QtCore.Qt.UserRole) if item is not None else {}
            if isinstance(payload, dict) and needle == str(payload.get('candidate_node_id') or ''):
                self.explanation_table.selectRow(row_index)
                self.update_explanation_preview()
                return True
        return False

    def update_explanation_preview(self) -> None:
        selected_items = self.explanation_table.selectedItems()
        if not selected_items:
            self.explanation_preview.setPlainText('No node explanation selected.')
            return
        row = selected_items[0].row()
        explanation = self.explanation_table.item(row, 0).data(QtCore.Qt.UserRole)
        if not isinstance(explanation, dict):
            self.explanation_preview.setPlainText('No node explanation selected.')
            return
        lines = ['Node Explanation']
        for key, value in explanation.items():
            lines.append(f'\n{key}:\n{format_cell(value)}')
        self.explanation_preview.setPlainText('\n'.join(lines))

    def first_visible_item(self) -> QtWidgets.QListWidgetItem | None:
        for index in range(self.request_list.count()):
            item = self.request_list.item(index)
            if not item.isHidden():
                return item
        return None

    def _populate_explanation_table(self, explanations: List[Dict[str, Any]]) -> None:
        self.explanation_table.setRowCount(len(explanations))
        for row_index, explanation in enumerate(explanations):
            values = [
                str(explanation.get('candidate_node_id') or ''),
                str(explanation.get('skill_name') or ''),
                str(explanation.get('fallback_level') or ''),
                str(explanation.get('reason') or ''),
            ]
            for column_index, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(QtCore.Qt.UserRole, explanation)
                self.explanation_table.setItem(row_index, column_index, item)
        self.explanation_table.resizeColumnsToContents()
        if explanations:
            self.explanation_table.selectRow(0)
            self.update_explanation_preview()
        else:
            self.explanation_preview.setPlainText('No persisted node explanations for this request.')

    @staticmethod
    def _summary_lines(record: Dict[str, Any]) -> List[str]:
        return [
            'Request Review',
            f"planning_request_id: {record.get('planning_request_id') or record.get('request_key') or ''}",
            f"request_uuid: {record.get('request_uuid') or ''}",
            f"prompt_iterations: {len(record.get('prompt_iterations', []))}",
            f"node_explanations: {len(record.get('node_explanations', []))}",
            f"generated_plan_snapshots: {len(record.get('generated_plans', []))}",
            f"selected_semantic_modes: {', '.join(record.get('selected_modes', [])) or 'none'}",
        ]

    @staticmethod
    def _audit_text(record: Dict[str, Any]) -> str:
        lines = ['Prompt Audit Iterations']
        source_file = str(record.get('source_file') or '')
        if source_file:
            lines.append(f'source_file: {source_file}')
        for iteration in record.get('prompt_iterations', []):
            lines.extend(
                [
                    '',
                    str(iteration.get('iteration_key') or ''),
                    f"phase: {iteration.get('phase') or ''}",
                    f"mode: {iteration.get('selected_semantic_context_mode') or ''}",
                    f"detailed_chars: {iteration.get('detailed_chars')}",
                    f"community_chars: {iteration.get('community_chars')}",
                    f"reduction_ratio: {iteration.get('reduction_ratio')}",
                    f"community_summaries: {iteration.get('community_summaries')}",
                    f"relevant_capabilities: {iteration.get('relevant_capabilities')}",
                ]
            )
        if len(lines) == 1:
            lines.append('No prompt-audit iterations for this request.')
        return '\n'.join(lines)

    @staticmethod
    def _generated_plan_text(record: Dict[str, Any], selected_plan: Dict[str, Any] | None = None) -> str:
        generated_plans = record.get('generated_plans', [])
        if not generated_plans:
            return 'No generated plan snapshot loaded for this request.'
        selected = selected_plan or next((item for item in generated_plans if item.get('selected')), generated_plans[0])
        lines = [
            'Generated Plan Snapshot',
            f"candidate_plan_id: {selected.get('candidate_plan_id') or ''}",
            f"graph_hash: {selected.get('graph_hash') or ''}",
            f"iteration: {selected.get('iteration_key') or ''}",
            f"plan_key: {selected.get('plan_key') or ''}",
            f"selected: {selected.get('selected')}",
            f"feasible: {selected.get('feasible')}",
            f"final_rapfs: {selected.get('final_rapfs')}",
            f"terminal_success_estimate: {selected.get('terminal_success_estimate')}",
            f"source_file: {selected.get('source_file') or ''}",
            '',
            'Reasoning:',
            str(selected.get('reasoning') or ''),
            '',
            'Plan XML:',
            str(selected.get('plan_xml') or ''),
        ]
        return '\n'.join(lines)


__all__ = ['RequestReviewWidget']