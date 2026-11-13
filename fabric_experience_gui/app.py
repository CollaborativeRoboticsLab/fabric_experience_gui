from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List

from python_qt_binding import QtCore, QtWidgets

from fabric_experience_gui.audits import export_planner_prompt_audit_summary, export_retrieval_prompt_audit
from fabric_experience_gui.automation import run_focused_checks, run_offline_functional_workflow
from fabric_server.prompt_decision_support import build_prompt_decision_support_report
from fabric_server.terminal_success_analysis import build_report as build_terminal_success_analysis_report
from fabric_server.terminal_success_analysis import export_terminal_success_analysis
from fabric_experience_gui.storage import InspectorDatabase, TableSnapshot, format_cell, load_generated_plan_index, load_prompt_audit_snapshot
from fabric_experience_gui.graph_plot_3d import save_graph_plot
from fabric_experience_gui.plan_sandbox import build_plan_sandbox_graph, build_tuning_proposal, parse_optional_json
from fabric_experience_gui.services import score_plan_live
from fabric_experience_gui.ui.fabric_graph_view import FabricGraphWidget
from fabric_experience_gui.ui.draft_editor import DraftEditorWidget
from fabric_experience_gui.ui import (
    AnalysisJobsPanel as DockAnalysisJobsPanel,
    CalibrationReviewWidget,
    DecisionSupportWidget,
    GraphOverviewWidget,
    PlanSandboxWidget,
    RequestReviewWidget,
    build_graph_overview_state,
    graph_node_color,
    graph_node_label,
)


TABLE_SECTION_NAMES = [
    'Nodes',
    'Edges',
    'Communities',
    'Plan Feedback',
    'Node Explanations',
    'Scoring Epochs',
    'Prompt Audits',
]

GRAPH_OVERVIEW_NAME = 'Graph Overview'
PLAN_SANDBOX_NAME = 'Plan Sandbox'
REQUEST_REVIEW_NAME = 'Request Review'
DECISION_SUPPORT_NAME = 'Decision Support'
CALIBRATION_REVIEW_NAME = 'Calibration Review'
NODE_TYPE_BRUSHES = {
    'capability': '#1b9e77',
    'task_entity': '#d95f02',
    'context_entity': '#7570b3',
    'plan_pattern': '#e7298a',
    'fault_concept': '#66a61e',
    'synthetic': '#7f7f7f',
    '0': '#1b9e77',
    '1': '#d95f02',
    '2': '#7570b3',
    '3': '#e7298a',
    '4': '#66a61e',
}
PLAN_NODE_BRUSHES = {
    'plan': '#2f80ed',
    'control': '#f2994a',
    'runner': '#27ae60',
}


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
            row,
            columns,
            self.secondary_column,
            self.secondary_text,
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


class InspectorWidget(QtWidgets.QWidget):
    def __init__(self, initial_db_path: str = '', initial_audit_root: str = ''):
        super().__init__()
        self.db_path_edit = QtWidgets.QLineEdit(initial_db_path)
        self.audit_root_edit = QtWidgets.QLineEdit(initial_audit_root)
        self.generated_root_edit = QtWidgets.QLineEdit('')
        self.status_label = QtWidgets.QLabel('Open a core_graphrag.sqlite3 file to inspect GraphRAG state.')

        self.snapshots: Dict[str, TableSnapshot] = {}
        self.tables: Dict[str, QtWidgets.QTableView] = {}
        self.preview_boxes: Dict[str, QtWidgets.QPlainTextEdit] = {}
        self.filter_edits: Dict[str, QtWidgets.QLineEdit] = {}
        self.match_labels: Dict[str, QtWidgets.QLabel] = {}
        self.filter_columns: Dict[str, QtWidgets.QComboBox] = {}
        self.secondary_filter_edits: Dict[str, QtWidgets.QLineEdit] = {}
        self.secondary_filter_columns: Dict[str, QtWidgets.QComboBox] = {}
        self.models: Dict[str, SnapshotTableModel] = {}
        self.proxies: Dict[str, SnapshotFilterProxyModel] = {}

        self.graph_nodes: Dict[str, Dict[str, Any]] = {}
        self.graph_neighbors: Dict[str, List[Dict[str, Any]]] = {}
        self.graph_communities: Dict[str, List[str]] = {}
        self.generated_plan_index: Dict[str, List[Dict[str, Any]]] = {}
        self.graph_overview_widget: GraphOverviewWidget | None = None

        self.plan_nodes: Dict[str, Dict[str, Any]] = {}
        self.plan_edges: List[Dict[str, Any]] = []
        self.plan_sandbox_widget: PlanSandboxWidget | None = None
        self.request_review_widget: RequestReviewWidget | None = None
        self.decision_support_widget: DecisionSupportWidget | None = None
        self.calibration_review_widget: CalibrationReviewWidget | None = None
        self._score_plan_live = score_plan_live

        self.jobs_panel: DockAnalysisJobsPanel | None = None
        self.notebook: QtWidgets.QTabWidget | None = None

        self._build_layout()
        for edit in self.findChildren(QtWidgets.QLineEdit):
            if not edit.toolTip() and edit.placeholderText():
                edit.setToolTip(edit.placeholderText())
        for button in self.findChildren(QtWidgets.QPushButton):
            if not button.toolTip():
                if button.text() == 'Clear':
                    button.setToolTip('Clear both filters for this table.')
                else:
                    button.setToolTip(button.text() + '.')

        if initial_db_path:
            self.load_database(initial_db_path)
        if initial_audit_root:
            self.load_prompt_audits()

    def _build_layout(self) -> None:
        outer_layout = QtWidgets.QVBoxLayout(self)
        notebook = QtWidgets.QTabWidget()
        self.notebook = notebook
        fabric_tabs = QtWidgets.QTabWidget()
        fabric_tabs.addTab(self._build_generative_graph(), 'Generative Graph')
        self.fabric_graph_widget = FabricGraphWidget()
        fabric_tabs.addTab(self.fabric_graph_widget, 'Live Graph Execution')
        self.draft_editor = DraftEditorWidget()
        fabric_tabs.addTab(self.draft_editor, 'Graph Editor')
        notebook.addTab(fabric_tabs, 'Fabric')

        experience = QtWidgets.QWidget()
        experience_layout = QtWidgets.QVBoxLayout(experience)
        experience_layout.addLayout(self._build_toolbar())
        self.experience_tabs = QtWidgets.QTabWidget()
        self.experience_tabs.addTab(self._build_plan_sandbox(), PLAN_SANDBOX_NAME)
        graph_tabs = QtWidgets.QTabWidget()
        graph_tabs.addTab(self._build_graph_overview(), 'Overview')
        for section in ('Nodes', 'Edges', 'Communities'):
            graph_tabs.addTab(self._build_section(section), section)
        self.experience_tabs.addTab(graph_tabs, 'Inspect GraphRAG')
        self.decision_tabs = QtWidgets.QTabWidget()
        self.decision_tabs.addTab(self._build_request_review(), REQUEST_REVIEW_NAME)
        self.decision_tabs.addTab(self._build_calibration_review(), CALIBRATION_REVIEW_NAME)
        self.decision_tabs.addTab(self._build_decision_support(), DECISION_SUPPORT_NAME)
        self.experience_tabs.addTab(self.decision_tabs, 'Decision Support')
        feedback_tabs = QtWidgets.QTabWidget()
        for section in ('Plan Feedback', 'Scoring Epochs', 'Node Explanations', 'Prompt Audits'):
            feedback_tabs.addTab(self._build_section(section), section)
        self.experience_tabs.addTab(feedback_tabs, 'Feedback Ingestion')
        experience_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        experience_splitter.addWidget(self.experience_tabs)
        self.jobs_scroll = QtWidgets.QScrollArea()
        self.jobs_scroll.setWidgetResizable(True)
        self.jobs_scroll.setWidget(DockAnalysisJobsPanel(self))
        self.set_jobs_panel(self.jobs_scroll.widget())
        experience_splitter.addWidget(self.jobs_scroll)
        experience_splitter.setStretchFactor(0, 4)
        experience_splitter.setStretchFactor(1, 1)
        self.jobs_scroll.hide()
        experience_layout.addWidget(experience_splitter, stretch=1)
        experience_layout.addWidget(self.status_label)
        notebook.addTab(experience, 'Experience')
        outer_layout.addWidget(notebook, stretch=1)

    def _build_generative_graph(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel('Task prompt'))
        self.generation_prompt = QtWidgets.QPlainTextEdit()
        self.generation_prompt.setPlaceholderText('Describe the task for the generated plan.')
        self.generation_prompt.setToolTip('Task description to use when plan generation becomes available.')
        self.generation_prompt.setMaximumHeight(160)
        layout.addWidget(self.generation_prompt)
        self.generate_button = QtWidgets.QPushButton('Generate plan')
        self.generate_button.setEnabled(False)
        self.generate_button.setToolTip('Unavailable until non-dispatching generation is verified.')
        layout.addWidget(self.generate_button, alignment=QtCore.Qt.AlignLeft)
        status = QtWidgets.QLabel('Plan generation and dispatch are unavailable pending safe preview and validation.')
        status.setWordWrap(True)
        layout.addWidget(status)
        layout.addWidget(QtWidgets.QLabel('Generated plan'))
        self.generated_plan_preview = QtWidgets.QPlainTextEdit()
        self.generated_plan_preview.setReadOnly(True)
        self.generated_plan_preview.setPlaceholderText('No generated plan available.')
        self.generated_plan_preview.setToolTip('Generated plan XML will appear here when safe preview is available.')
        layout.addWidget(self.generated_plan_preview, stretch=1)
        return page

    def closeEvent(self, event):
        if not self.draft_editor.confirm_discard():
            event.ignore()
            return
        self.draft_editor.close_requests()
        self.fabric_graph_widget.close_requests()
        super().closeEvent(event)

    def _build_toolbar(self) -> QtWidgets.QVBoxLayout:
        toolbar = QtWidgets.QVBoxLayout()
        paths = QtWidgets.QGridLayout()
        self.db_path_edit.setToolTip('Path to the GraphRAG SQLite database to inspect.')
        self.audit_root_edit.setToolTip('Directory containing planner prompt-audit artifacts.')
        self.generated_root_edit.setToolTip('Directory containing generated-plan artifacts.')
        rows = [
            ('DB Path', self.db_path_edit, self.browse_database, 'Load', self.load_from_entry,
             'Select a GraphRAG database.', 'Load the selected GraphRAG database.'),
            ('Prompt Audit Dir', self.audit_root_edit, self.browse_audit_root, 'Load Audits', self.load_prompt_audits,
             'Select the prompt-audit directory.', 'Load prompt-audit artifacts from the selected directory.'),
            ('Generated Plans Dir', self.generated_root_edit, self.browse_generated_root, 'Load Plans', self.load_generated_plan_artifacts,
             'Select the generated-plan directory.', 'Load generated-plan artifacts from the selected directory.'),
        ]
        for row, (label, edit, browse, action, callback, browse_tip, action_tip) in enumerate(rows):
            paths.addWidget(QtWidgets.QLabel(label), row, 0)
            paths.addWidget(edit, row, 1)
            browse_button = QtWidgets.QPushButton('Browse')
            browse_button.setToolTip(browse_tip)
            browse_button.clicked.connect(browse)
            paths.addWidget(browse_button, row, 2)
            action_button = QtWidgets.QPushButton(action)
            action_button.setToolTip(action_tip)
            action_button.clicked.connect(callback)
            paths.addWidget(action_button, row, 3)
        toolbar.addLayout(paths)
        actions = QtWidgets.QHBoxLayout()
        for label, tip, callback in (
            ('Export Retrieval Audit', 'Export retrieval statistics from the loaded database.', self.export_retrieval_audit),
            ('Summarize Audits', 'Export a summary of the loaded prompt audits.', self.export_planner_summary),
            ('Save 3D Plot', 'Save a 3D plot of the loaded GraphRAG graph.', self.export_graph_plot),
            ('Write Proposal', 'Write a non-destructive tuning proposal.', self.export_tuning_proposal),
        ):
            button = QtWidgets.QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(callback)
            actions.addWidget(button)
        jobs_button = QtWidgets.QPushButton('Analysis Jobs')
        jobs_button.setCheckable(True)
        jobs_button.setToolTip('Show or hide offline exports, analysis workflows, and focused checks.')
        jobs_button.toggled.connect(lambda visible: self.jobs_scroll.setVisible(visible))
        actions.addWidget(jobs_button)
        actions.addStretch(1)
        toolbar.addLayout(actions)
        return toolbar

    def _build_section(self, name: str) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)

        model = SnapshotTableModel()
        proxy = SnapshotFilterProxyModel()
        proxy.setSourceModel(model)

        primary_row = QtWidgets.QHBoxLayout()
        primary_row.addWidget(QtWidgets.QLabel('Primary Filter'))
        primary_column = QtWidgets.QComboBox()
        primary_column.addItem('All columns')
        primary_column.currentTextChanged.connect(lambda _text, section=name: self.apply_filter(section))
        primary_row.addWidget(primary_column)
        primary_edit = QtWidgets.QLineEdit()
        primary_edit.setPlaceholderText('Primary match')
        primary_edit.textChanged.connect(lambda _text, section=name: self.apply_filter(section))
        primary_row.addWidget(primary_edit, stretch=1)
        left_layout.addLayout(primary_row)

        secondary_row = QtWidgets.QHBoxLayout()
        secondary_row.addWidget(QtWidgets.QLabel('Secondary Filter'))
        secondary_column = QtWidgets.QComboBox()
        secondary_column.addItem('All columns')
        secondary_column.currentTextChanged.connect(lambda _text, section=name: self.apply_filter(section))
        secondary_row.addWidget(secondary_column)
        secondary_edit = QtWidgets.QLineEdit()
        secondary_edit.setPlaceholderText('Optional second match')
        secondary_edit.textChanged.connect(lambda _text, section=name: self.apply_filter(section))
        secondary_row.addWidget(secondary_edit, stretch=1)
        clear_button = QtWidgets.QPushButton('Clear')
        clear_button.clicked.connect(lambda _checked=False, s=name: self.clear_filters(s))
        secondary_row.addWidget(clear_button)
        match_label = QtWidgets.QLabel('0 / 0 rows')
        secondary_row.addWidget(match_label)
        left_layout.addLayout(secondary_row)

        table = QtWidgets.QTableView()
        table.setModel(proxy)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        table.selectionModel().selectionChanged.connect(lambda _selected, _deselected, section=name: self.update_preview(section))
        left_layout.addWidget(table, stretch=1)

        preview = QtWidgets.QPlainTextEdit()
        preview.setReadOnly(True)

        splitter.addWidget(left_panel)
        splitter.addWidget(preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self.tables[name] = table
        self.preview_boxes[name] = preview
        self.filter_edits[name] = primary_edit
        self.match_labels[name] = match_label
        self.filter_columns[name] = primary_column
        self.secondary_filter_edits[name] = secondary_edit
        self.secondary_filter_columns[name] = secondary_column
        self.models[name] = model
        self.proxies[name] = proxy
        return page

    def _build_graph_overview(self) -> QtWidgets.QWidget:
        page = GraphOverviewWidget(self.select_graph_node_by_id)
        self.graph_overview_widget = page
        self._clear_graph_overview()
        return page

    def _build_plan_sandbox(self) -> QtWidgets.QWidget:
        page = PlanSandboxWidget(
            on_load_xml=self.load_plan_xml_file,
            on_parse=self.parse_plan_sandbox,
            on_score=self.score_plan_sandbox_live,
            on_load_score=self.load_plan_score_file,
            on_clear=self.clear_plan_sandbox,
            on_select_node=self.select_plan_node_by_id,
            node_brushes=PLAN_NODE_BRUSHES,
        )
        self.plan_sandbox_widget = page
        self.clear_plan_sandbox()
        return page

    def _build_request_review(self) -> QtWidgets.QWidget:
        page = RequestReviewWidget()
        self.request_review_widget = page
        self.refresh_request_review()
        return page

    def _build_decision_support(self) -> QtWidgets.QWidget:
        page = DecisionSupportWidget(on_open_request=self.open_request_review_for_request)
        self.decision_support_widget = page
        self.refresh_decision_support()
        return page

    def _build_calibration_review(self) -> QtWidgets.QWidget:
        page = CalibrationReviewWidget(on_open_request=self.open_request_review_for_request)
        self.calibration_review_widget = page
        self.refresh_calibration_review()
        return page

    def set_jobs_panel(self, jobs_panel: AnalysisJobsPanel) -> None:
        self.jobs_panel = jobs_panel
        self.jobs_panel.sync_defaults_from_widget()

    def browse_database(self) -> None:
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            'Select core_graphrag.sqlite3',
            '',
            'SQLite database (*.sqlite3);;All files (*.*)',
        )
        if selected:
            self.db_path_edit.setText(selected)
            self.load_database(selected)

    def browse_audit_root(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            'Select planner_prompt_audit directory',
        )
        if selected:
            self.audit_root_edit.setText(selected)
            self.load_prompt_audits()

    def browse_generated_root(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            'Select generated plan artifact directory',
        )
        if selected:
            self.generated_root_edit.setText(selected)
            self.load_generated_plan_artifacts()

    def load_from_entry(self) -> None:
        self.load_database(self.db_path_edit.text().strip())

    def load_database(self, db_path: str) -> None:
        if not db_path:
            QtWidgets.QMessageBox.warning(self, 'Experience Inspector', 'Provide a path to core_graphrag.sqlite3.')
            return

        database = InspectorDatabase(Path(db_path))
        if not database.exists():
            QtWidgets.QMessageBox.critical(self, 'Experience Inspector', f'Database not found: {db_path}')
            return

        try:
            snapshots = database.load_all()
        except Exception as exc:  # pragma: no cover - UI path
            QtWidgets.QMessageBox.critical(self, 'Experience Inspector', f'Failed to load database: {exc}')
            return

        self.snapshots = {snapshot.name: snapshot for snapshot in snapshots}
        for snapshot in snapshots:
            self.populate_table(snapshot)
        self.refresh_graph_overview()
        self.refresh_request_review()
        self.refresh_decision_support()
        self.refresh_calibration_review()
        if self.jobs_panel is not None:
            self.jobs_panel.sync_defaults_from_widget()
        self.status_label.setText(f'Loaded {db_path} with {len(snapshots)} inspector views.')

    def load_prompt_audits(self) -> None:
        audit_root = self.audit_root_edit.text().strip()
        if not audit_root:
            QtWidgets.QMessageBox.warning(self, 'Experience Inspector', 'Provide a planner prompt audit directory path.')
            return

        snapshot = load_prompt_audit_snapshot(Path(audit_root))
        self.snapshots[snapshot.name] = snapshot
        self.populate_table(snapshot)
        self.refresh_request_review()
        self.refresh_decision_support()
        self.refresh_calibration_review()
        if self.jobs_panel is not None:
            self.jobs_panel.sync_defaults_from_widget()
        self.status_label.setText(f'Loaded prompt audits from {audit_root} with {len(snapshot.rows)} iteration rows.')

    def load_generated_plan_artifacts(self) -> None:
        generated_root = self.current_generated_root()
        if not generated_root:
            QtWidgets.QMessageBox.warning(self, 'Experience Inspector', 'Provide a generated plan artifact directory path.')
            return
        self.generated_plan_index = load_generated_plan_index(Path(generated_root))
        self.refresh_request_review()
        self.refresh_decision_support()
        self.refresh_calibration_review()
        self.status_label.setText(
            f'Loaded generated plan artifacts from {generated_root} with {len(self.generated_plan_index)} requests.'
        )

    def populate_table(self, snapshot: TableSnapshot) -> None:
        model = self.models[snapshot.name]
        proxy = self.proxies[snapshot.name]
        table = self.tables[snapshot.name]

        model.set_snapshot(snapshot)

        previous_primary = self.filter_columns[snapshot.name].currentText()
        previous_secondary = self.secondary_filter_columns[snapshot.name].currentText()

        self._reset_filter_combo(self.filter_columns[snapshot.name], snapshot.columns, previous_primary)
        self._reset_filter_combo(self.secondary_filter_columns[snapshot.name], snapshot.columns, previous_secondary)

        table.resizeColumnsToContents()
        table.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.set_preview(snapshot.name, f"{snapshot.name}\n\nRows: {len(snapshot.rows)}\nColumns: {', '.join(snapshot.columns)}")
        self.apply_filter(snapshot.name)

    def apply_filter(self, section: str) -> None:
        model = self.models.get(section)
        proxy = self.proxies.get(section)
        primary_edit = self.filter_edits.get(section)
        primary_column = self.filter_columns.get(section)
        secondary_edit = self.secondary_filter_edits.get(section)
        secondary_column = self.secondary_filter_columns.get(section)
        match_label = self.match_labels.get(section)
        if None in (model, proxy, primary_edit, primary_column, secondary_edit, secondary_column, match_label):
            return

        proxy.set_primary_filter(primary_column.currentText(), primary_edit.text())
        proxy.set_secondary_filter(secondary_column.currentText(), secondary_edit.text())
        match_label.setText(f'{proxy.rowCount()} / {model.rowCount()} rows')

    def clear_filters(self, section: str) -> None:
        self.filter_columns[section].setCurrentText('All columns')
        self.filter_edits[section].clear()
        self.secondary_filter_columns[section].setCurrentText('All columns')
        self.secondary_filter_edits[section].clear()
        self.apply_filter(section)

    def update_preview(self, section: str) -> None:
        model = self.models.get(section)
        proxy = self.proxies.get(section)
        table = self.tables.get(section)
        if model is None or proxy is None or table is None:
            return

        selected_rows = table.selectionModel().selectedRows()
        if not selected_rows:
            return

        source_index = proxy.mapToSource(selected_rows[0])
        row = model.row_dict(source_index.row())
        lines: List[str] = [section]
        for key, value in row.items():
            lines.append(f'\n{key}:\n{format_cell(value)}')
        self.set_preview(section, '\n'.join(lines))

    def set_preview(self, section: str, text: str) -> None:
        self.preview_boxes[section].setPlainText(text)

    def current_db_path(self) -> str:
        return self.db_path_edit.text().strip()

    def current_audit_root(self) -> str:
        return self.audit_root_edit.text().strip()

    def current_generated_root(self) -> str:
        return self.generated_root_edit.text().strip()

    def set_db_path(self, db_path: str) -> None:
        self.db_path_edit.setText(db_path)
        if self.jobs_panel is not None:
            self.jobs_panel.sync_defaults_from_widget()

    def set_audit_root(self, audit_root: str) -> None:
        self.audit_root_edit.setText(audit_root)
        if self.jobs_panel is not None:
            self.jobs_panel.sync_defaults_from_widget()

    def set_generated_root(self, generated_root: str) -> None:
        self.generated_root_edit.setText(generated_root)

    def default_retrieval_output_dir(self) -> Path:
        db_path = self.current_db_path()
        if db_path:
            return Path(db_path).resolve().parent / 'retrieval_prompt_audit'
        return Path.cwd() / 'retrieval_prompt_audit'

    def default_summary_output_dir(self) -> Path:
        audit_root = self.current_audit_root()
        if audit_root:
            return Path(audit_root).resolve().parent / 'planner_prompt_audit_exports'
        return Path.cwd() / 'planner_prompt_audit_exports'

    def default_workflow_output_dir(self) -> Path:
        db_path = self.current_db_path()
        if db_path:
            return Path(db_path).resolve().parent / 'offline_functional_outputs'
        return Path.cwd() / 'offline_functional_outputs'

    def default_terminal_success_analysis_dir(self) -> Path:
        db_path = self.current_db_path()
        if db_path:
            return Path(db_path).resolve().parent / 'terminal_success_analysis'
        return Path.cwd() / 'terminal_success_analysis'

    def default_plot_output_path(self) -> Path:
        db_path = self.current_db_path()
        if db_path:
            resolved = Path(db_path).resolve()
            return resolved.with_name(f'{resolved.stem}_3d_graph.png')
        return Path.cwd() / 'core_graphrag_3d_graph.png'

    def default_proposal_output_path(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        db_path = self.current_db_path()
        if db_path:
            resolved = Path(db_path).resolve()
            return resolved.with_name(f'{resolved.stem}_proposal_{stamp}.json')
        return Path.cwd() / f'fabric_experience_gui_proposal_{stamp}.json'

    def refresh_graph_overview(self) -> None:
        nodes_snapshot = self.snapshots.get('Nodes')
        edges_snapshot = self.snapshots.get('Edges')
        communities_snapshot = self.snapshots.get('Communities')
        if nodes_snapshot is None or edges_snapshot is None or communities_snapshot is None or self.graph_overview_widget is None:
            self._clear_graph_overview()
            return

        graph_state = build_graph_overview_state(nodes_snapshot, edges_snapshot, communities_snapshot)
        self.graph_nodes = graph_state['graph_nodes']
        self.graph_neighbors = graph_state['graph_neighbors']
        self.graph_communities = graph_state['graph_communities']
        self.graph_overview_widget.set_graph_data(
            self.graph_nodes,
            self.graph_neighbors,
            self.graph_communities,
            label_fn=graph_node_label,
            color_fn=lambda node: graph_node_color(node, NODE_TYPE_BRUSHES),
            summary_lines=graph_state['summary_lines'],
        )

    def refresh_request_review(self) -> None:
        if self.request_review_widget is None:
            return

        prompt_snapshot = self.snapshots.get('Prompt Audits')
        explanation_snapshot = self.snapshots.get('Node Explanations')
        if prompt_snapshot is None and explanation_snapshot is None and not self.generated_plan_index:
            self.request_review_widget.clear_review()
            return

        records_by_key: Dict[str, Dict[str, Any]] = {}

        def ensure_record(request_key: str) -> Dict[str, Any]:
            return records_by_key.setdefault(
                request_key,
                {
                    'request_key': request_key,
                    'planning_request_id': request_key,
                    'request_uuid': '',
                    'source_file': '',
                    'prompt_iterations': [],
                    'node_explanations': [],
                    'generated_plans': [],
                    'selected_modes': [],
                },
            )

        if prompt_snapshot is not None:
            for row in prompt_snapshot.rows:
                request_key = str(row.get('planning_request_id') or row.get('request_uuid') or row.get('source_file') or '')
                if not request_key:
                    continue
                record = ensure_record(request_key)
                record['planning_request_id'] = str(row.get('planning_request_id') or record['planning_request_id'])
                record['request_uuid'] = str(row.get('request_uuid') or record['request_uuid'])
                record['source_file'] = str(row.get('source_file') or record['source_file'])
                record['prompt_iterations'].append(row)
                mode = str(row.get('selected_semantic_context_mode') or '')
                if mode and mode not in record['selected_modes']:
                    record['selected_modes'].append(mode)

        if explanation_snapshot is not None:
            for row in explanation_snapshot.rows:
                request_key = str(row.get('planning_request_id') or '')
                if not request_key:
                    continue
                record = ensure_record(request_key)
                record['node_explanations'].append(row)

        for request_key, plans in self.generated_plan_index.items():
            record = ensure_record(str(request_key))
            record['generated_plans'].extend(plans)

        records = sorted(
            records_by_key.values(),
            key=lambda record: (
                str(record.get('planning_request_id') or record.get('request_key') or '').lower(),
                str(record.get('request_uuid') or '').lower(),
            ),
        )
        self.request_review_widget.set_request_records(records)

    def refresh_decision_support(self) -> None:
        if self.decision_support_widget is None:
            return
        audit_root = self.current_audit_root()
        feedback_root = self.current_generated_root()
        if not audit_root or not feedback_root:
            self.decision_support_widget.clear_report()
            return
        db_path = self.current_db_path()
        report = build_prompt_decision_support_report(
            Path(audit_root),
            Path(feedback_root),
            Path(db_path) if db_path else None,
        )
        self.decision_support_widget.set_report(report)

    def refresh_calibration_review(self) -> None:
        if self.calibration_review_widget is None:
            return
        feedback_root = self.current_generated_root()
        db_path = self.current_db_path()
        if not feedback_root or not db_path:
            self.calibration_review_widget.clear_report()
            return
        report = build_terminal_success_analysis_report(Path(feedback_root), Path(db_path))
        self.calibration_review_widget.set_report(report)

    def open_request_review_for_request(
        self,
        request_id: str,
        candidate_plan_id: str = '',
        candidate_node_id: str = '',
    ) -> bool:
        if self.request_review_widget is None:
            return False
        selected = self.request_review_widget.select_request(
            request_id,
            candidate_plan_id=candidate_plan_id,
            candidate_node_id=candidate_node_id,
        )
        if selected and self.notebook is not None:
            self.notebook.setCurrentIndex(1)
            self.experience_tabs.setCurrentWidget(self.decision_tabs)
            self.decision_tabs.setCurrentWidget(self.request_review_widget)
        return selected

    def apply_graph_filter(self) -> None:
        if self.graph_overview_widget is None:
            return
        self.graph_overview_widget.apply_filter()

    def select_graph_node_by_id(self, node_id: str) -> None:
        if self.graph_overview_widget is None:
            return
        self.graph_overview_widget.select_node_by_id(node_id)

    def _clear_graph_overview(self) -> None:
        self.graph_nodes = {}
        self.graph_neighbors = {}
        self.graph_communities = {}
        if self.graph_overview_widget is not None:
            self.graph_overview_widget.clear_overview()

    def _first_visible_graph_item(self) -> QtWidgets.QListWidgetItem | None:
        if self.graph_node_list is None:
            return None
        for index in range(self.graph_node_list.count()):
            item = self.graph_node_list.item(index)
            if not item.isHidden():
                return item
        return None

    def run_retrieval_export(self, out_dir: Path) -> Dict[str, Any]:
        db_path = self.current_db_path()
        if not db_path:
            raise ValueError('Load a GraphRAG database first.')
        return export_retrieval_prompt_audit(Path(db_path), out_dir)

    def run_planner_summary_export(
        self,
        out_dir: Path,
        high_prompt_chars: int = 1200,
        low_signal_items: int = 2,
    ) -> Dict[str, Any]:
        audit_root = self.current_audit_root()
        if not audit_root:
            raise ValueError('Load a planner prompt audit directory first.')
        return export_planner_prompt_audit_summary(
            Path(audit_root),
            out_dir,
            high_prompt_chars=high_prompt_chars,
            low_signal_items=low_signal_items,
        )

    def run_graph_plot_export(
        self,
        output_path: Path,
        label_nodes: bool = True,
        drop_isolated: bool = False,
        component: str = 'all',
    ) -> Path:
        db_path = self.current_db_path()
        if not db_path:
            raise ValueError('Load a GraphRAG database first.')
        return save_graph_plot(
            Path(db_path),
            output_path=output_path,
            label_nodes=label_nodes,
            drop_isolated=drop_isolated,
            component=component,
        )

    def build_tuning_proposal(self, proposal_kind: str, summary: str = '', notes: str = '') -> Dict[str, Any]:
        prompt_snapshot = self.snapshots.get('Prompt Audits')
        plan_summary_text = self.plan_summary_box.toPlainText().strip() if self.plan_summary_box is not None else ''
        return build_tuning_proposal(
            proposal_kind,
            summary,
            notes,
            db_path=self.current_db_path(),
            audit_root=self.current_audit_root(),
            selected_graph_node_id=self.current_graph_node_id,
            selected_plan_node_id=self.current_plan_node_id,
            graph_nodes=self.graph_nodes,
            graph_neighbors=self.graph_neighbors,
            graph_communities=self.graph_communities,
            prompt_audit_row_count=len(prompt_snapshot.rows) if prompt_snapshot is not None else 0,
            plan_nodes=self.plan_nodes,
            plan_edges=self.plan_edges,
            plan_summary_text=plan_summary_text,
        )

    def run_tuning_proposal_export(
        self,
        output_path: Path,
        proposal_kind: str,
        summary: str = '',
        notes: str = '',
    ) -> Path:
        proposal = self.build_tuning_proposal(proposal_kind, summary=summary, notes=notes)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(proposal, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        return output_path

    def run_offline_workflow(
        self,
        feedback_root: Path,
        out_dir: Path,
        planning_request_id: str = '',
        candidate_plan_id: str = '',
        graph_hash: str = '',
        candidate_node_id: str = '',
    ) -> Dict[str, Any]:
        db_path = self.current_db_path()
        audit_root = self.current_audit_root()
        if not db_path:
            raise ValueError('Load a GraphRAG database first.')
        if not audit_root:
            raise ValueError('Load a planner prompt audit directory first.')
        return run_offline_functional_workflow(
            Path(db_path),
            Path(audit_root),
            feedback_root,
            out_dir,
            planning_request_id=planning_request_id,
            candidate_plan_id=candidate_plan_id,
            graph_hash=graph_hash,
            candidate_node_id=candidate_node_id,
        )

    def run_focused_checks(self, workspace_root: Path) -> Dict[str, Any]:
        return run_focused_checks(workspace_root)

    def run_terminal_success_analysis(self, feedback_root: Path, out_dir: Path) -> Dict[str, Any]:
        db_path = self.current_db_path()
        if not db_path:
            raise ValueError('Load a GraphRAG database first.')
        return export_terminal_success_analysis(feedback_root, Path(db_path), out_dir)

    def export_retrieval_audit(self) -> None:
        default_dir = str(self.default_retrieval_output_dir())
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select retrieval audit output directory', default_dir)
        if not out_dir:
            return
        try:
            audit = self.run_retrieval_export(Path(out_dir))
        except Exception as exc:  # pragma: no cover - UI path
            QtWidgets.QMessageBox.critical(self, 'Experience Inspector', f'Failed to export retrieval audit: {exc}')
            return
        QtWidgets.QMessageBox.information(
            self,
            'Experience Inspector',
            f"Wrote retrieval audit to {out_dir}\nplans={audit['summary']['plan_count']} nodes={audit['summary']['node_explanation_count']}",
        )

    def export_planner_summary(self) -> None:
        default_dir = str(self.default_summary_output_dir())
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select planner summary output directory', default_dir)
        if not out_dir:
            return
        try:
            report = self.run_planner_summary_export(Path(out_dir))
        except Exception as exc:  # pragma: no cover - UI path
            QtWidgets.QMessageBox.critical(self, 'Experience Inspector', f'Failed to summarize prompt audits: {exc}')
            return
        QtWidgets.QMessageBox.information(
            self,
            'Experience Inspector',
            f"Wrote planner prompt summary to {out_dir}\nrequests={report['summary']['request_count']} iterations={report['summary']['iteration_count']}",
        )

    def export_graph_plot(self) -> None:
        default_path = str(self.default_plot_output_path())
        output_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            'Save 3D graph plot',
            default_path,
            'PNG image (*.png);;All files (*.*)',
        )
        if not output_path:
            return
        try:
            written_path = self.run_graph_plot_export(Path(output_path), label_nodes=True)
        except Exception as exc:  # pragma: no cover - UI path
            QtWidgets.QMessageBox.critical(self, 'Experience Inspector', f'Failed to save 3D plot: {exc}')
            return
        QtWidgets.QMessageBox.information(self, 'Experience Inspector', f'Wrote 3D graph plot to {written_path}')

    def export_tuning_proposal(self) -> None:
        default_path = str(self.default_proposal_output_path())
        output_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            'Write non-destructive tuning proposal',
            default_path,
            'JSON file (*.json);;All files (*.*)',
        )
        if not output_path:
            return
        summary, ok = QtWidgets.QInputDialog.getText(self, 'Experience Inspector', 'Proposal summary:')
        if not ok:
            return
        try:
            written_path = self.run_tuning_proposal_export(
                Path(output_path),
                proposal_kind='general_review',
                summary=summary.strip(),
                notes='',
            )
        except Exception as exc:  # pragma: no cover - UI path
            QtWidgets.QMessageBox.critical(self, 'Experience Inspector', f'Failed to write tuning proposal: {exc}')
            return
        QtWidgets.QMessageBox.information(self, 'Experience Inspector', f'Wrote non-destructive tuning proposal to {written_path}')

    def load_plan_xml_file(self) -> None:
        if self.plan_xml_edit is None:
            return
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            'Select Fabric XML plan',
            '',
            'XML files (*.xml);;All files (*.*)',
        )
        if not selected:
            return
        self.plan_xml_edit.setPlainText(Path(selected).read_text(encoding='utf-8'))
        self.status_label.setText(f'Loaded Fabric XML from {selected}.')

    def load_plan_score_file(self) -> None:
        if self.plan_score_edit is None:
            return
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            'Select score JSON overlay',
            '',
            'JSON files (*.json *.jsonl);;All files (*.*)',
        )
        if not selected:
            return
        text = Path(selected).read_text(encoding='utf-8')
        if selected.endswith('.jsonl'):
            first_line = next((line for line in text.splitlines() if line.strip()), '')
            text = first_line
        self.plan_score_edit.setPlainText(text)
        self.status_label.setText(f'Loaded score overlay from {selected}.')

    def score_plan_sandbox_live(self) -> None:
        if self.plan_xml_edit is None or self.plan_score_edit is None or self.plan_task_description_edit is None:
            return
        task_description = self.plan_task_description_edit.text().strip()
        if not task_description:
            QtWidgets.QMessageBox.warning(self, 'Experience Inspector', 'Provide a task description before live scoring.')
            return
        plan_xml = self.plan_xml_edit.toPlainText()
        if not plan_xml.strip():
            QtWidgets.QMessageBox.warning(self, 'Experience Inspector', 'Provide Fabric XML before live scoring.')
            return
        try:
            payload = self._score_plan_live(
                task_description,
                plan_xml,
                planning_request_id=self.plan_request_id_edit.text().strip() if self.plan_request_id_edit else '',
                candidate_plan_id=self.plan_candidate_id_edit.text().strip() if self.plan_candidate_id_edit else '',
                candidate_node_id=self.plan_candidate_node_id_edit.text().strip() if self.plan_candidate_node_id_edit else '',
            )
        except Exception as exc:  # pragma: no cover - UI path
            QtWidgets.QMessageBox.critical(
                self,
                'Experience Inspector',
                f'Live scoring failed: {exc}\n\n'
                'Make sure the workspace is sourced and the /fabric/experience/score service is running.',
            )
            return
        self.plan_score_edit.setPlainText(json.dumps(payload, indent=2, sort_keys=True))
        self.parse_plan_sandbox()
        self.status_label.setText('Loaded live score response into the Plan Sandbox overlay.')

    def parse_plan_sandbox(self) -> None:
        if self.plan_xml_edit is None or self.plan_score_edit is None:
            return
        xml_text = self.plan_xml_edit.toPlainText()
        try:
            score_payload = parse_optional_json(self.plan_score_edit.toPlainText())
        except json.JSONDecodeError as exc:
            QtWidgets.QMessageBox.critical(self, 'Experience Inspector', f'Failed to parse score JSON: {exc}')
            return
        try:
            sandbox = build_plan_sandbox_graph(xml_text, score_payload)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, 'Experience Inspector', str(exc))
            return

        self.plan_nodes = sandbox['nodes']
        self.plan_edges = sandbox['edges']
        if self.plan_sandbox_widget is not None:
            self.plan_sandbox_widget.set_sandbox_data(self.plan_nodes, self.plan_edges, sandbox['summary'])
        self.status_label.setText(
            f"Parsed Fabric XML plan with {sandbox['summary']['node_count']} nodes and {sandbox['summary']['edge_count']} edges."
        )

    def clear_plan_sandbox(self) -> None:
        self.plan_nodes = {}
        self.plan_edges = []
        if self.plan_sandbox_widget is not None:
            self.plan_sandbox_widget.clear_sandbox()

    def select_plan_node_by_id(self, node_id: str) -> None:
        if self.plan_sandbox_widget is None:
            return
        self.plan_sandbox_widget.select_node_by_id(node_id)

    @property
    def graph_summary_box(self) -> QtWidgets.QPlainTextEdit | None:
        return self.graph_overview_widget.summary_box if self.graph_overview_widget is not None else None

    @property
    def graph_node_filter_edit(self) -> QtWidgets.QLineEdit | None:
        return self.graph_overview_widget.node_filter_edit if self.graph_overview_widget is not None else None

    @property
    def graph_node_list(self) -> QtWidgets.QListWidget | None:
        return self.graph_overview_widget.node_list if self.graph_overview_widget is not None else None

    @property
    def graph_node_preview(self) -> QtWidgets.QPlainTextEdit | None:
        return self.graph_overview_widget.node_preview if self.graph_overview_widget is not None else None

    @property
    def graph_neighbor_table(self) -> QtWidgets.QTableWidget | None:
        return self.graph_overview_widget.neighbor_table if self.graph_overview_widget is not None else None

    @property
    def graph_scene(self) -> QtWidgets.QGraphicsScene | None:
        return self.graph_overview_widget.graph_scene if self.graph_overview_widget is not None else None

    @property
    def graph_view(self) -> QtWidgets.QGraphicsView | None:
        return self.graph_overview_widget.graph_view if self.graph_overview_widget is not None else None

    @property
    def graph_node_items(self) -> Dict[str, Any]:
        return self.graph_overview_widget.graph_node_items if self.graph_overview_widget is not None else {}

    @property
    def graph_node_labels(self) -> Dict[str, Any]:
        return self.graph_overview_widget.graph_node_labels if self.graph_overview_widget is not None else {}

    @property
    def current_graph_node_id(self) -> str:
        return self.graph_overview_widget.current_graph_node_id if self.graph_overview_widget is not None else ''

    @property
    def plan_xml_edit(self) -> QtWidgets.QPlainTextEdit | None:
        return self.plan_sandbox_widget.plan_xml_edit if self.plan_sandbox_widget is not None else None

    @property
    def plan_score_edit(self) -> QtWidgets.QPlainTextEdit | None:
        return self.plan_sandbox_widget.plan_score_edit if self.plan_sandbox_widget is not None else None

    @property
    def plan_summary_box(self) -> QtWidgets.QPlainTextEdit | None:
        return self.plan_sandbox_widget.summary_box if self.plan_sandbox_widget is not None else None

    @property
    def plan_preview_box(self) -> QtWidgets.QPlainTextEdit | None:
        return self.plan_sandbox_widget.preview_box if self.plan_sandbox_widget is not None else None

    @property
    def plan_task_description_edit(self) -> QtWidgets.QLineEdit | None:
        return self.plan_sandbox_widget.plan_task_description_edit if self.plan_sandbox_widget is not None else None

    @property
    def plan_request_id_edit(self) -> QtWidgets.QLineEdit | None:
        return self.plan_sandbox_widget.plan_request_id_edit if self.plan_sandbox_widget is not None else None

    @property
    def plan_candidate_id_edit(self) -> QtWidgets.QLineEdit | None:
        return self.plan_sandbox_widget.plan_candidate_id_edit if self.plan_sandbox_widget is not None else None

    @property
    def plan_candidate_node_id_edit(self) -> QtWidgets.QLineEdit | None:
        return self.plan_sandbox_widget.plan_candidate_node_id_edit if self.plan_sandbox_widget is not None else None

    @property
    def plan_scene(self) -> QtWidgets.QGraphicsScene | None:
        return self.plan_sandbox_widget.plan_scene if self.plan_sandbox_widget is not None else None

    @property
    def plan_view(self) -> QtWidgets.QGraphicsView | None:
        return self.plan_sandbox_widget.plan_view if self.plan_sandbox_widget is not None else None

    @property
    def plan_node_list(self) -> QtWidgets.QListWidget | None:
        return self.plan_sandbox_widget.node_list if self.plan_sandbox_widget is not None else None

    @property
    def plan_node_items(self) -> Dict[str, Any]:
        return self.plan_sandbox_widget.plan_node_items if self.plan_sandbox_widget is not None else {}

    @property
    def plan_node_labels(self) -> Dict[str, Any]:
        return self.plan_sandbox_widget.plan_node_labels if self.plan_sandbox_widget is not None else {}

    @property
    def current_plan_node_id(self) -> str:
        return self.plan_sandbox_widget.current_plan_node_id if self.plan_sandbox_widget is not None else ''

    @staticmethod
    def _reset_filter_combo(combo: QtWidgets.QComboBox, columns: List[str], previous: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem('All columns')
        combo.addItems(columns)
        if previous and previous in ['All columns', *columns]:
            combo.setCurrentText(previous)
        combo.blockSignals(False)


class InspectorMainWindow(QtWidgets.QMainWindow):
    def closeEvent(self, event):
        if not self.widget.draft_editor.confirm_discard():
            event.ignore()
            return
        self.widget.draft_editor.close_requests()
        self.widget.fabric_graph_widget.close_requests()
        super().closeEvent(event)

    def __init__(self, initial_db_path: str = '', initial_audit_root: str = '', initial_feedback_root: str = ''):
        super().__init__()
        self.setWindowTitle('Fabric Experience GUI')
        self.resize(1520, 900)
        self.widget = InspectorWidget(initial_db_path=initial_db_path, initial_audit_root=initial_audit_root)
        if initial_feedback_root:
            self.widget.set_generated_root(initial_feedback_root)
            self.widget.load_generated_plan_artifacts()
        self.setCentralWidget(self.widget)

        self.jobs_panel = self.widget.jobs_panel


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Offline inspector for Experience GraphRAG databases.')
    parser.add_argument('--db-path', default='', help='Optional path to core_graphrag.sqlite3 opened on startup.')
    parser.add_argument('--audit-root', default='', help='Optional path to planner_prompt_audit opened on startup.')
    parser.add_argument('--feedback-root', default='', help='Optional path to generated plan artifacts loaded on startup.')
    return parser.parse_args(argv)


def ensure_application(argv: List[str] | None = None) -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        return QtWidgets.QApplication(argv or sys.argv)
    return app


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    app = ensure_application(argv)
    window = InspectorMainWindow(
        initial_db_path=args.db_path,
        initial_audit_root=args.audit_root,
        initial_feedback_root=args.feedback_root,
    )
    previous_sigint = signal.signal(signal.SIGINT, lambda _signal, _frame: window.close())
    signal_timer = QtCore.QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(100)
    try:
        window.show()
        return app.exec_()
    finally:
        signal_timer.stop()
        signal.signal(signal.SIGINT, previous_sigint)