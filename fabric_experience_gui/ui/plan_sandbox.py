from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from python_qt_binding import QtCore, QtWidgets
from python_qt_binding.QtGui import QBrush, QColor, QPainter, QPen

from fabric_experience_gui.storage.database import format_cell
from fabric_experience_gui.ui.graph_overview import GraphNodeItem


class PlanSandboxWidget(QtWidgets.QWidget):
    def __init__(self, *, on_load_xml, on_parse, on_score, on_load_score, on_clear, on_select_node, node_brushes):
        super().__init__()
        self._on_select_node = on_select_node
        self._node_brushes = node_brushes
        self.plan_nodes: Dict[str, Dict[str, Any]] = {}
        self.plan_edges: List[Dict[str, Any]] = []
        self.current_plan_node_id = ''
        self.plan_node_items: Dict[str, GraphNodeItem] = {}
        self.plan_node_labels: Dict[str, QtWidgets.QGraphicsSimpleTextItem] = {}
        self._build_layout(on_load_xml, on_parse, on_score, on_load_score, on_clear)

    def _build_layout(self, on_load_xml, on_parse, on_score, on_load_score, on_clear) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        controls = QtWidgets.QHBoxLayout()
        self.load_xml_button = QtWidgets.QPushButton('Load XML File')
        self.load_xml_button.setToolTip('Load Fabric XML into the sandbox without dispatching it.')
        self.load_xml_button.clicked.connect(on_load_xml)
        controls.addWidget(self.load_xml_button)

        self.parse_button = QtWidgets.QPushButton('Parse XML')
        self.parse_button.setToolTip('Parse and display the current XML locally without dispatching it.')
        self.parse_button.clicked.connect(on_parse)
        controls.addWidget(self.parse_button)

        self.score_button = QtWidgets.QPushButton('Score via Service')
        self.score_button.setToolTip('Request a live score for the current XML without dispatching it.')
        self.score_button.clicked.connect(on_score)
        controls.addWidget(self.score_button)

        self.load_score_button = QtWidgets.QPushButton('Load Score JSON')
        self.load_score_button.setToolTip('Load a saved score response as an overlay.')
        self.load_score_button.clicked.connect(on_load_score)
        controls.addWidget(self.load_score_button)

        self.clear_button = QtWidgets.QPushButton('Clear Sandbox')
        self.clear_button.setToolTip('Clear the sandbox inputs and graph.')
        self.clear_button.clicked.connect(on_clear)
        controls.addWidget(self.clear_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.summary_box = QtWidgets.QPlainTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMaximumHeight(120)
        layout.addWidget(self.summary_box)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        editor_panel = QtWidgets.QWidget()
        editor_layout = QtWidgets.QVBoxLayout(editor_panel)
        request_row = QtWidgets.QFormLayout()
        self.plan_task_description_edit = QtWidgets.QLineEdit()
        self.plan_task_description_edit.setToolTip('Task description required by the live scoring service.')
        self.plan_task_description_edit.setPlaceholderText('Required for live scoring requests')
        request_row.addRow('Task Description', self.plan_task_description_edit)
        self.plan_request_id_edit = QtWidgets.QLineEdit()
        self.plan_request_id_edit.setToolTip('Optional planning request ID for live scoring.')
        request_row.addRow('Planning Request ID', self.plan_request_id_edit)
        self.plan_candidate_id_edit = QtWidgets.QLineEdit()
        self.plan_candidate_id_edit.setToolTip('Optional candidate plan ID for live scoring.')
        request_row.addRow('Candidate Plan ID', self.plan_candidate_id_edit)
        self.plan_candidate_node_id_edit = QtWidgets.QLineEdit()
        self.plan_candidate_node_id_edit.setToolTip('Optional candidate node ID for live scoring.')
        request_row.addRow('Candidate Node ID', self.plan_candidate_node_id_edit)
        editor_layout.addLayout(request_row)
        editor_layout.addWidget(QtWidgets.QLabel('Fabric XML'))
        self.plan_xml_edit = QtWidgets.QPlainTextEdit()
        self.plan_xml_edit.setToolTip('Fabric XML to inspect or score; the sandbox never dispatches it.')
        editor_layout.addWidget(self.plan_xml_edit, stretch=3)
        editor_layout.addWidget(QtWidgets.QLabel('Optional Score JSON Overlay'))
        self.plan_score_edit = QtWidgets.QPlainTextEdit()
        self.plan_score_edit.setToolTip('Optional score response or snapshot JSON to overlay on the graph.')
        self.plan_score_edit.setPlaceholderText('Paste a score response or snapshot JSON here to overlay plan metrics and node explanations.')
        editor_layout.addWidget(self.plan_score_edit, stretch=2)

        explorer_panel = QtWidgets.QWidget()
        explorer_layout = QtWidgets.QVBoxLayout(explorer_panel)
        self.node_list = QtWidgets.QListWidget()
        self.node_list.currentItemChanged.connect(self.update_preview)
        explorer_layout.addWidget(QtWidgets.QLabel('Plan Nodes'))
        explorer_layout.addWidget(self.node_list, stretch=1)

        preview_panel = QtWidgets.QWidget()
        preview_layout = QtWidgets.QVBoxLayout(preview_panel)
        self.plan_view = QtWidgets.QGraphicsView()
        self.plan_view.setRenderHint(QPainter.Antialiasing, True)
        self.plan_view.setMinimumHeight(320)
        self.plan_scene = QtWidgets.QGraphicsScene(self.plan_view)
        self.plan_view.setScene(self.plan_scene)
        preview_layout.addWidget(self.plan_view, stretch=4)
        self.preview_box = QtWidgets.QPlainTextEdit()
        self.preview_box.setReadOnly(True)
        preview_layout.addWidget(self.preview_box, stretch=2)

        splitter.addWidget(editor_panel)
        splitter.addWidget(explorer_panel)
        splitter.addWidget(preview_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 3)
        layout.addWidget(splitter, stretch=1)

        self.clear_sandbox()

    def set_sandbox_data(self, plan_nodes: Dict[str, Dict[str, Any]], plan_edges: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
        self.plan_nodes = plan_nodes
        self.plan_edges = plan_edges
        self.render_scene()
        self.populate_node_list()
        self.update_summary(summary)

    def clear_sandbox(self) -> None:
        self.plan_nodes = {}
        self.plan_edges = []
        self.current_plan_node_id = ''
        self.summary_box.setPlainText('Paste or load a Fabric XML plan, then parse it to inspect its structure.')
        self.preview_box.setPlainText('No plan node selected.')
        self.node_list.clear()
        self.plan_scene.clear()
        self.plan_scene.addText('Load and parse Fabric XML to render the plan graph.')

    def update_summary(self, summary: Dict[str, Any]) -> None:
        plan_metrics = summary.get('plan_metrics', {})
        lines = [
            'Plan Sandbox',
            f"nodes: {summary.get('node_count', 0)}",
            f"edges: {summary.get('edge_count', 0)}",
            f"runners: {summary.get('runner_count', 0)}",
            f"controls: {summary.get('control_count', 0)}",
        ]
        if plan_metrics:
            lines.append('')
            lines.append('Imported score overlay:')
            for key, value in plan_metrics.items():
                lines.append(f'{key}: {value}')
        else:
            lines.append('')
            lines.append('No score overlay loaded. Structural graph only.')
        self.summary_box.setPlainText('\n'.join(lines))

    def populate_node_list(self) -> None:
        self.node_list.clear()
        for node_id, node in sorted(self.plan_nodes.items(), key=lambda item: (item[1]['kind'], item[1]['label'])):
            item = QtWidgets.QListWidgetItem(f"{node['label']} [{node['kind']}]")
            item.setData(QtCore.Qt.UserRole, node_id)
            self.node_list.addItem(item)
        if self.node_list.count() > 0:
            self.node_list.setCurrentRow(0)

    def render_scene(self) -> None:
        self.plan_scene.clear()
        self.plan_node_items = {}
        self.plan_node_labels = {}
        if not self.plan_nodes:
            self.plan_scene.addText('Load and parse Fabric XML to render the plan graph.')
            return

        node_ids = list(self.plan_nodes.keys())
        level_map = self._plan_levels()
        levels = defaultdict(list)
        for node_id in node_ids:
            levels[level_map.get(node_id, 0)].append(node_id)

        positions: Dict[str, tuple[float, float]] = {}
        x_spacing = 170.0
        y_spacing = 95.0
        for level, ids in sorted(levels.items()):
            for index, node_id in enumerate(ids):
                positions[node_id] = (80.0 + level * x_spacing, 70.0 + index * y_spacing)

        for edge in self.plan_edges:
            source_pos = positions.get(edge['source'])
            target_pos = positions.get(edge['target'])
            if source_pos is None or target_pos is None:
                continue
            pen = QPen(QColor('#8a8f98'), 1.4)
            self.plan_scene.addLine(source_pos[0], source_pos[1], target_pos[0], target_pos[1], pen)
            if edge['label'] != 'contains':
                label = self.plan_scene.addSimpleText(edge['label'])
                label.setBrush(QBrush(QColor('#444444')))
                label.setPos((source_pos[0] + target_pos[0]) / 2.0, (source_pos[1] + target_pos[1]) / 2.0)

        radius = 12.0
        for node_id, node in self.plan_nodes.items():
            x, y = positions[node_id]
            item = GraphNodeItem(
                x,
                y,
                radius,
                node_id,
                self._node_brushes.get(node['kind'], '#7f7f7f'),
                self._on_select_node,
            )
            item.setToolTip(node['label'])
            self.plan_scene.addItem(item)
            label = self.plan_scene.addSimpleText(node['label'])
            label.setBrush(QBrush(QColor('#222222')))
            label.setPos(x + radius + 3.0, y - radius)
            self.plan_node_items[node_id] = item
            self.plan_node_labels[node_id] = label

        self.plan_scene.setSceneRect(0.0, 0.0, max(640.0, 120.0 + len(levels) * x_spacing), max(420.0, 90.0 + len(node_ids) * 45.0))

    def select_node_by_id(self, node_id: str) -> None:
        for index in range(self.node_list.count()):
            item = self.node_list.item(index)
            if str(item.data(QtCore.Qt.UserRole)) == node_id:
                self.node_list.setCurrentItem(item)
                self.node_list.scrollToItem(item)
                return
        self.highlight_node(node_id)

    def update_preview(self, current: QtWidgets.QListWidgetItem | None, previous: QtWidgets.QListWidgetItem | None = None) -> None:
        del previous
        if current is None:
            return
        node_id = str(current.data(QtCore.Qt.UserRole))
        self.current_plan_node_id = node_id
        node = self.plan_nodes.get(node_id, {})
        outgoing = [edge for edge in self.plan_edges if edge['source'] == node_id]
        incoming = [edge for edge in self.plan_edges if edge['target'] == node_id]
        lines = [
            f"{node.get('label', '')} [{node.get('kind', '')}]",
            '',
            f'id: {node_id}',
            f"tag: {node.get('tag', '')}",
            f"attributes: {format_cell(node.get('attributes', {}))}",
            f'outgoing_edges: {len(outgoing)}',
            f'incoming_edges: {len(incoming)}',
        ]
        overlay = node.get('score_overlay', {})
        if overlay:
            lines.append('')
            lines.append('Score overlay:')
            for key, value in overlay.items():
                lines.append(f'{key}: {value}')
        else:
            lines.append('')
            lines.append('No node score overlay loaded for this node.')
        self.preview_box.setPlainText('\n'.join(lines))
        self.highlight_node(node_id)

    def highlight_node(self, node_id: str) -> None:
        self.current_plan_node_id = node_id
        for other_id, item in self.plan_node_items.items():
            pen_width = 3.0 if other_id == node_id else 1.0
            item.setPen(QPen(QColor('#111111'), pen_width))
        if node_id in self.plan_node_items:
            self.plan_view.centerOn(self.plan_node_items[node_id])

    def _plan_levels(self) -> Dict[str, int]:
        children_by_source = defaultdict(list)
        indegree = defaultdict(int)
        for edge in self.plan_edges:
            if edge['kind'] == 'contains':
                children_by_source[edge['source']].append(edge['target'])
                indegree[edge['target']] += 1
                indegree.setdefault(edge['source'], 0)
        roots = [node_id for node_id in self.plan_nodes if indegree.get(node_id, 0) == 0]
        levels: Dict[str, int] = {node_id: 0 for node_id in roots}
        queue = list(roots)
        while queue:
            current = queue.pop(0)
            for child in children_by_source.get(current, []):
                level = levels[current] + 1
                if level > levels.get(child, -1):
                    levels[child] = level
                queue.append(child)
        for node_id in self.plan_nodes:
            levels.setdefault(node_id, 0)
        return levels
