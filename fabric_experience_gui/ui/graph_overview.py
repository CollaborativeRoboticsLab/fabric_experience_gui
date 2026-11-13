from __future__ import annotations

from collections import defaultdict
import json
import math
from typing import Any, Dict, List

from python_qt_binding import QtCore, QtWidgets
from python_qt_binding.QtGui import QBrush, QColor, QPainter, QPen

from fabric_experience_gui.storage.database import TableSnapshot, format_cell


def coerce_sequence(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in ('', None):
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text[0] in '[{' and text[-1] in ']}':
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return [item.strip() for item in text.split(',') if item.strip()]
    return [str(value)]


def graph_node_sort_key(node: Dict[str, Any]) -> tuple[str, str]:
    return (str(node.get('name') or node.get('id') or '').lower(), str(node.get('id') or '').lower())


def graph_node_label(node: Dict[str, Any]) -> str:
    name = str(node.get('name') or node.get('id') or '')
    node_id = str(node.get('id') or '')
    node_type = str(node.get('type') or '')
    provider = str(node.get('provider') or '')
    suffix = f' [{node_type}]' if node_type else ''
    provider_text = f' ({provider})' if provider else ''
    if name == node_id or not node_id:
        return f'{name}{provider_text}{suffix}'
    return f'{name} [{node_id}]{provider_text}{suffix}'


def graph_node_color(node: Dict[str, Any], node_type_brushes: Dict[str, str]) -> str:
    node_type = str(node.get('type') or 'synthetic')
    return node_type_brushes.get(node_type, '#7f7f7f')


def build_graph_overview_state(
    nodes_snapshot: TableSnapshot,
    edges_snapshot: TableSnapshot,
    communities_snapshot: TableSnapshot,
) -> Dict[str, Any]:
    graph_nodes: Dict[str, Dict[str, Any]] = {}
    graph_neighbors: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    graph_communities: Dict[str, List[str]] = defaultdict(list)

    for row in nodes_snapshot.rows:
        node_id = str(row.get('id') or '')
        if not node_id:
            continue
        graph_nodes[node_id] = dict(row)

    edge_count = 0
    for edge in edges_snapshot.rows:
        source = str(edge.get('projected_source') or edge.get('source') or '')
        target = str(edge.get('projected_target') or edge.get('target') or '')
        if not source or not target:
            continue
        for endpoint in (source, target):
            if endpoint not in graph_nodes:
                graph_nodes[endpoint] = {
                    'id': endpoint,
                    'name': endpoint,
                    'provider': '',
                    'type': 'synthetic',
                    'level': '',
                    'cluster_id': '',
                    'feature_vector': '',
                }
        neighbor_from_source = dict(edge)
        neighbor_from_source['neighbor_id'] = target
        neighbor_from_source['direction'] = 'outgoing'
        graph_neighbors[source].append(neighbor_from_source)

        neighbor_from_target = dict(edge)
        neighbor_from_target['neighbor_id'] = source
        neighbor_from_target['direction'] = 'incoming'
        graph_neighbors[target].append(neighbor_from_target)
        edge_count += 1

    for community in communities_snapshot.rows:
        community_id = str(community.get('id') or '')
        for node_id in coerce_sequence(community.get('node_ids')):
            graph_communities[node_id].append(community_id)

    degrees = sorted(
        ((node_id, len(neighbors)) for node_id, neighbors in graph_neighbors.items()),
        key=lambda item: (-item[1], item[0]),
    )
    top_lines = [f'{node_id}: degree {degree}' for node_id, degree in degrees[:5]] or ['none']
    return {
        'graph_nodes': graph_nodes,
        'graph_neighbors': graph_neighbors,
        'graph_communities': graph_communities,
        'summary_lines': [
            'Graph Overview',
            f'nodes: {len(graph_nodes)}',
            f'edges: {edge_count}',
            f'communities: {len(communities_snapshot.rows)}',
            'highest-degree nodes: ' + '; '.join(top_lines),
        ],
    }


class GraphNodeItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(
        self,
        x: float,
        y: float,
        radius: float,
        node_id: str,
        color: str,
        on_click,
    ):
        super().__init__(x - radius, y - radius, radius * 2.0, radius * 2.0)
        self.node_id = node_id
        self._on_click = on_click
        self.setBrush(QBrush(QColor(color)))
        self.setPen(QPen(QColor('#1f1f1f'), 1.0))
        self.setZValue(2.0)

    def mousePressEvent(self, event):
        self._on_click(self.node_id)
        super().mousePressEvent(event)


class GraphOverviewWidget(QtWidgets.QWidget):
    def __init__(self, on_select_node):
        super().__init__()
        self._on_select_node = on_select_node
        self.graph_nodes: Dict[str, Dict[str, Any]] = {}
        self.graph_neighbors: Dict[str, List[Dict[str, Any]]] = {}
        self.graph_communities: Dict[str, List[str]] = {}
        self.current_graph_node_id = ''
        self.graph_node_items: Dict[str, GraphNodeItem] = {}
        self.graph_node_labels: Dict[str, QtWidgets.QGraphicsSimpleTextItem] = {}
        self._build_layout()

    def _build_layout(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        self.summary_box = QtWidgets.QPlainTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMaximumHeight(110)
        layout.addWidget(self.summary_box)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel('Node Filter'))
        self.node_filter_edit = QtWidgets.QLineEdit()
        self.node_filter_edit.setPlaceholderText('Filter graph nodes by id, name, provider, or type')
        self.node_filter_edit.textChanged.connect(self.apply_filter)
        filter_row.addWidget(self.node_filter_edit, stretch=1)
        left_layout.addLayout(filter_row)

        self.node_list = QtWidgets.QListWidget()
        self.node_list.currentItemChanged.connect(self.update_preview)
        left_layout.addWidget(self.node_list, stretch=1)

        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)

        self.graph_view = QtWidgets.QGraphicsView()
        self.graph_view.setRenderHint(QPainter.Antialiasing, True)
        self.graph_view.setMinimumHeight(320)
        self.graph_scene = QtWidgets.QGraphicsScene(self.graph_view)
        self.graph_view.setScene(self.graph_scene)
        right_layout.addWidget(self.graph_view, stretch=4)

        self.node_preview = QtWidgets.QPlainTextEdit()
        self.node_preview.setReadOnly(True)
        right_layout.addWidget(self.node_preview, stretch=2)

        self.neighbor_table = QtWidgets.QTableWidget()
        self.neighbor_table.setColumnCount(5)
        self.neighbor_table.setHorizontalHeaderLabels(['neighbor', 'relationship', 'strength', 'score', 'edge_id'])
        self.neighbor_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.neighbor_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.neighbor_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.neighbor_table.setAlternatingRowColors(True)
        self.neighbor_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        right_layout.addWidget(self.neighbor_table, stretch=3)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, stretch=1)

        self.clear_overview()

    def set_graph_data(
        self,
        graph_nodes: Dict[str, Dict[str, Any]],
        graph_neighbors: Dict[str, List[Dict[str, Any]]],
        graph_communities: Dict[str, List[str]],
        *,
        label_fn,
        color_fn,
        summary_lines: List[str],
    ) -> None:
        self.graph_nodes = graph_nodes
        self.graph_neighbors = graph_neighbors
        self.graph_communities = graph_communities
        self._label_fn = label_fn
        self._color_fn = color_fn
        self.summary_box.setPlainText('\n'.join(summary_lines))
        self.populate_node_list()
        self.render_scene()

    def clear_overview(self) -> None:
        self.graph_nodes = {}
        self.graph_neighbors = {}
        self.graph_communities = {}
        self.current_graph_node_id = ''
        self.summary_box.setPlainText('Load a GraphRAG database to populate the graph overview.')
        self.node_list.clear()
        self.node_preview.setPlainText('No graph data loaded.')
        self.populate_neighbor_table([])
        self.graph_scene.clear()
        self.graph_scene.addText('Load a GraphRAG database to render the graph canvas.')

    def populate_node_list(self) -> None:
        self.node_list.clear()
        for node_id, node in sorted(self.graph_nodes.items(), key=lambda item: graph_node_sort_key(item[1])):
            item = QtWidgets.QListWidgetItem(self._label_fn(node))
            item.setData(QtCore.Qt.UserRole, node_id)
            self.node_list.addItem(item)
        self.apply_filter()
        first_visible = self.first_visible_item()
        if first_visible is not None:
            self.node_list.setCurrentItem(first_visible)
        else:
            self.node_preview.setPlainText('No graph nodes available.')

    def apply_filter(self) -> None:
        needle = self.node_filter_edit.text().strip().lower()
        for index in range(self.node_list.count()):
            item = self.node_list.item(index)
            node_id = str(item.data(QtCore.Qt.UserRole))
            node = self.graph_nodes.get(node_id, {})
            haystack = ' '.join(
                [
                    str(node.get('id') or ''),
                    str(node.get('name') or ''),
                    str(node.get('provider') or ''),
                    str(node.get('type') or ''),
                ]
            ).lower()
            item.setHidden(bool(needle) and needle not in haystack)

    def update_preview(self, current: QtWidgets.QListWidgetItem | None, previous: QtWidgets.QListWidgetItem | None = None) -> None:
        del previous
        if current is None:
            self.current_graph_node_id = ''
            self.node_preview.setPlainText('No graph node selected.')
            self.populate_neighbor_table([])
            return

        node_id = str(current.data(QtCore.Qt.UserRole))
        self.current_graph_node_id = node_id
        node = self.graph_nodes.get(node_id, {})
        neighbors = sorted(
            self.graph_neighbors.get(node_id, []),
            key=lambda edge: (str(edge.get('neighbor_id') or ''), str(edge.get('relationship') or '')),
        )
        community_ids = self.graph_communities.get(node_id, [])

        lines = [
            self._label_fn(node),
            '',
            f"id: {node.get('id', '')}",
            f"provider: {node.get('provider', '')}",
            f"type: {node.get('type', '')}",
            f"level: {node.get('level', '')}",
            f"cluster_id: {node.get('cluster_id', '')}",
            f"feature_vector: {format_cell(node.get('feature_vector', ''))}",
            f"incident_edges: {len(neighbors)}",
            f"communities: {', '.join(community_ids) if community_ids else 'none'}",
        ]
        self.node_preview.setPlainText('\n'.join(lines))
        self.populate_neighbor_table(neighbors)
        self.highlight_node(node_id)
        self.center_node(node_id)

    def select_node_by_id(self, node_id: str) -> None:
        for index in range(self.node_list.count()):
            item = self.node_list.item(index)
            if str(item.data(QtCore.Qt.UserRole)) == node_id:
                self.node_list.setCurrentItem(item)
                self.node_list.scrollToItem(item)
                return
        self.highlight_node(node_id)

    def render_scene(self) -> None:
        self.graph_scene.clear()
        self.graph_node_items = {}
        self.graph_node_labels = {}

        if not self.graph_nodes:
            self.graph_scene.addText('Load a GraphRAG database to render the graph canvas.')
            return

        node_ids = sorted(self.graph_nodes, key=lambda node_id: graph_node_sort_key(self.graph_nodes[node_id]))
        count = max(1, len(node_ids))
        center_x = 320.0
        center_y = 240.0
        radius = max(120.0, min(260.0, 40.0 * count))
        positions: Dict[str, tuple[float, float]] = {}
        for index, node_id in enumerate(node_ids):
            angle = (2.0 * math.pi * index) / count
            x = center_x + radius * 0.9 * math.cos(angle)
            y = center_y + radius * 0.6 * math.sin(angle)
            positions[node_id] = (x, y)

        drawn_edges: set[tuple[str, str, str]] = set()
        for source_id, neighbors in self.graph_neighbors.items():
            source_pos = positions.get(source_id)
            if source_pos is None:
                continue
            for edge in neighbors:
                target_id = str(edge.get('neighbor_id') or '')
                target_pos = positions.get(target_id)
                if target_pos is None:
                    continue
                edge_id = str(edge.get('id') or '')
                key = tuple(sorted((source_id, target_id)) + [edge_id])
                if key in drawn_edges:
                    continue
                drawn_edges.add(key)
                self.graph_scene.addLine(
                    source_pos[0],
                    source_pos[1],
                    target_pos[0],
                    target_pos[1],
                    QPen(QColor('#93a1a1'), 1.5),
                )

        node_radius = 11.0
        for node_id in node_ids:
            node = self.graph_nodes[node_id]
            x, y = positions[node_id]
            item = GraphNodeItem(
                x,
                y,
                node_radius,
                node_id,
                self._color_fn(node),
                self._on_select_node,
            )
            item.setToolTip(self._label_fn(node))
            self.graph_scene.addItem(item)
            label = self.graph_scene.addSimpleText(str(node.get('name') or node_id))
            label.setBrush(QBrush(QColor('#222222')))
            label.setPos(x + node_radius + 2.0, y - node_radius)
            self.graph_node_items[node_id] = item
            self.graph_node_labels[node_id] = label

        self.graph_scene.setSceneRect(0.0, 0.0, 640.0, 480.0)
        if self.current_graph_node_id:
            self.highlight_node(self.current_graph_node_id)
            self.center_node(self.current_graph_node_id)

    def center_node(self, node_id: str) -> None:
        item = self.graph_node_items.get(node_id)
        if item is not None:
            self.graph_view.centerOn(item)

    def highlight_node(self, node_id: str) -> None:
        self.current_graph_node_id = node_id
        for other_id, item in self.graph_node_items.items():
            pen_width = 3.0 if other_id == node_id else 1.0
            item.setPen(QPen(QColor('#111111'), pen_width))

    def populate_neighbor_table(self, neighbors: List[Dict[str, Any]]) -> None:
        self.neighbor_table.setRowCount(len(neighbors))
        for row_index, edge in enumerate(neighbors):
            values = [
                str(edge.get('neighbor_id') or ''),
                str(edge.get('relationship') or ''),
                str(edge.get('edge_strength_class') or ''),
                str(edge.get('structural_score') or ''),
                str(edge.get('id') or ''),
            ]
            for column_index, value in enumerate(values):
                self.neighbor_table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(value))
        self.neighbor_table.resizeColumnsToContents()

    def first_visible_item(self) -> QtWidgets.QListWidgetItem | None:
        for index in range(self.node_list.count()):
            item = self.node_list.item(index)
            if not item.isHidden():
                return item
        return None
