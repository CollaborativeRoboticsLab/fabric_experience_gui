from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from python_qt_binding import QtCore, QtGui, QtWidgets

from fabric_experience_gui.fabric_graph import InstanceId
from fabric_experience_gui.ui.fabric_graph_requests import FabricGraphRequests


def _identity_text(identity):
    text = f'{identity.interface}\n{identity.provider}'
    if isinstance(identity, InstanceId):
        text += f'\ninstance {identity.instance_id}'
    return text


class _GraphView(QtWidgets.QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        if 0.1 <= self.transform().m11() * factor <= 5:
            self.scale(factor, factor)


class FabricGraphWidget(QtWidgets.QWidget):
    def __init__(self, parent=None, *, client_factory=None):
        super().__init__(parent)
        options = {} if client_factory is None else {'client_factory': client_factory}
        self.requests = FabricGraphRequests(self, **options)
        self.requests.capture_ready.connect(self._capture_ready)
        self.requests.failed.connect(self._failed)
        self.capture = None
        self.loaded_xml = ''
        self.loaded_path = ''
        self.last_success = ''
        self.error = ''
        self.refreshing = False
        self._build_layout()

    def _build_layout(self):
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel('Source'))
        self.source = QtWidgets.QComboBox()
        self.source.setToolTip('Choose a live intended snapshot or a loaded XML plan.')
        self.source.addItem('Live snapshot', 'live')
        self.source.addItem('Loaded XML', 'loaded')
        self.source.currentIndexChanged.connect(self._source_changed)
        controls.addWidget(self.source)
        self.load_button = QtWidgets.QPushButton('Load XML')
        self.load_button.setToolTip('Load XML and request its parsed Fabric connections.')
        self.load_button.clicked.connect(self._load_xml)
        controls.addWidget(self.load_button)
        self.refresh_button = QtWidgets.QPushButton('Refresh')
        self.refresh_button.setToolTip('Refresh the selected source without submitting a plan.')
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)
        controls.addWidget(QtWidgets.QLabel('Level'))
        self.level = QtWidgets.QComboBox()
        self.level.setToolTip('Choose aggregated capabilities, instances, or provider dependencies.')
        self.level.addItems(['Main capabilities', 'All instances', 'Instances and dependencies'])
        self.level.currentIndexChanged.connect(self._level_changed)
        controls.addWidget(self.level)
        self.filter = QtWidgets.QLineEdit()
        self.filter.setToolTip('Filter capabilities by interface, provider, or instance ID.')
        self.filter.setPlaceholderText('Filter capabilities')
        self.filter.textChanged.connect(self.render)
        controls.addWidget(self.filter, 1)
        self.fit_button = QtWidgets.QPushButton('Fit')
        self.fit_button.setToolTip('Fit the graph in the view.')
        self.fit_button.clicked.connect(self.fit)
        controls.addWidget(self.fit_button)
        layout.addLayout(controls)

        self.status = QtWidgets.QLabel('Live snapshot: not refreshed')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        legend = QtWidgets.QLabel('Solid arrow: intended event  |  Dashed arrow: provider dependency (instance ownership unknown)')
        legend.setWordWrap(True)
        layout.addWidget(legend)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.scene = QtWidgets.QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._selection_changed)
        self.view = _GraphView(self.scene)
        self.view.setMinimumHeight(300)
        splitter.addWidget(self.view)
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText('Select a node or edge')
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([800, 200])
        layout.addWidget(splitter, 1)

    def _load_xml(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Load Fabric XML', '', 'XML files (*.xml);;All files (*)')
        if not path:
            return
        try:
            self.loaded_xml = Path(path).read_text(encoding='utf-8')
        except (OSError, UnicodeError) as exc:
            self.status.setText(f'Could not load XML: {exc}')
            return
        self.loaded_path = path
        if self.source.currentIndex() == 1:
            self._source_changed()
        else:
            self.source.setCurrentIndex(1)
        self.refresh()

    def _source_changed(self):
        self.requests.invalidate()
        self.capture = None
        self.last_success = ''
        self.error = ''
        self.refreshing = False
        self.scene.clear()
        self.details.clear()
        self.status.setText(f'{self.source.currentText()}: not refreshed')

    def _level_changed(self):
        self.render()
        self._show_status()

    def refresh(self):
        source = self.source.currentData()
        if source == 'loaded' and not self.loaded_path:
            self.status.setText('Loaded XML: no file selected')
            return
        self.error = ''
        self.refreshing = True
        self._show_status()
        self.requests.request(source, self.loaded_xml, include_dependencies=self.level.currentIndex() == 2)

    def _capture_ready(self, capture):
        self.capture = capture
        self.error = ''
        self.refreshing = False
        self.last_success = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
        self.render()
        self._show_status()
        self.fit()

    def _failed(self, error):
        self.error = error
        self.refreshing = False
        self._show_status()

    def _show_status(self):
        if self.error:
            self.status.setText(f'{self.source.currentText()}: unavailable: {self.error}' +
                                (f' | stale capture from {self.last_success}' if self.capture else ''))
            return
        if self.refreshing:
            self.status.setText(f'{self.source.currentText()}: refreshing' +
                                (' (previous capture is stale)' if self.capture else ''))
            return
        if not self.capture:
            return
        capture = self.capture
        state = 'no active plan' if not capture.has_plan else ('connections captured' if capture.connections_complete else 'partial')
        if capture.has_plan and not capture.graph.instances:
            state += ', empty graph'
        text = f'{self.source.currentText()} | {state} | last successful refresh: {self.last_success}'
        if capture.source == 'live':
            text += f' | plan: {capture.plan_id or "none"} | status: {capture.status_code}'
            if capture.capture_stamp:
                text += f' | state capture: {capture.capture_stamp[0]}.{capture.capture_stamp[1]:09d}'
        elif self.loaded_path:
            text += f' | {self.loaded_path}'
        if self.level.currentIndex() == 2:
            text += ' | dependencies: ' + ('provider-level, separately sampled' if capture.graph.dependencies_known else 'not loaded or unavailable; refresh to request')
        self.status.setText(text)

    def render(self):
        self.scene.clear()
        self.details.clear()
        if not self.capture:
            return
        graph = self.capture.graph.view(aggregate=self.level.currentIndex() == 0,
                                        include_dependencies=self.level.currentIndex() == 2)
        needle = self.filter.text().strip().lower()
        nodes = [node for node in graph.nodes if needle in _identity_text(node.identity).lower()]
        positions = {}
        count = len(nodes)
        radius = max(180, count * 40)
        for index, node in enumerate(nodes):
            angle = 2 * math.pi * index / max(count, 1) - math.pi / 2
            positions[node.identity] = QtCore.QPointF(radius * math.cos(angle), radius * math.sin(angle))
        edges = [(edge.source, edge.target, edge.event.label, edge.event, False) for edge in graph.edges]
        edges += [(edge.source, edge.target, 'dependency', edge, True) for edge in graph.dependencies]
        pairs = defaultdict(list)
        for edge in edges:
            if edge[0] in positions and edge[1] in positions:
                pairs[(edge[0], edge[1])].append(edge)
        for pair, group in pairs.items():
            for index, edge in enumerate(group):
                reverse_offset = 90 + (len(group) - 1) * 32 if pair[0] != pair[1] and (pair[1], pair[0]) in pairs else 15
                self._draw_edge(positions[pair[0]], positions[pair[1]], edge, index - (len(group) - 1) / 2, index, reverse_offset)
        for node in nodes:
            position = positions[node.identity]
            rectangle = self.scene.addRect(-85, -30, 170, 60, QtGui.QPen(QtGui.QColor('#39656b')), QtGui.QBrush(QtGui.QColor('#e5f1ef')))
            rectangle.setPos(position)
            rectangle.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)
            rectangle.setData(0, 'Node\n' + _identity_text(node.identity) + f'\nInstances: {len(node.instances)}')
            rectangle.setToolTip(_identity_text(node.identity) + f'\nInstances: {len(node.instances)}')
            label = QtWidgets.QGraphicsSimpleTextItem(node.identity.interface, rectangle)
            font = QtGui.QFont(self.font())
            font.setPointSize(8)
            label.setFont(font)
            label.setScale(min(1.0, 160.0 / max(label.boundingRect().width(), 1.0)))
            label.setPos(-80, -label.boundingRect().height() * label.scale() / 2)
            label.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))

    def _draw_edge(self, start, end, edge, offset, index, reverse_offset):
        source, target, label, detail, dependency = edge
        path = QtGui.QPainterPath()
        if source == target:
            begin = start + QtCore.QPointF(-35, -30)
            finish = start + QtCore.QPointF(35, -30)
            height = 85 + index * 30
            path.moveTo(begin)
            path.cubicTo(start + QtCore.QPointF(-100, -height), start + QtCore.QPointF(100, -height), finish)
        else:
            delta = end - start
            length = math.hypot(delta.x(), delta.y())
            unit = delta / length
            normal = QtCore.QPointF(-unit.y(), unit.x())
            boundary = min(85 / abs(unit.x()) if unit.x() else float('inf'),
                           30 / abs(unit.y()) if unit.y() else float('inf')) + 4
            begin = start + unit * boundary
            finish = end - unit * boundary
            path.moveTo(begin)
            path.quadTo((start + end) / 2 + normal * (offset * 64 + reverse_offset), finish)
        color = QtGui.QColor('#a35c24' if dependency else '#345b8b')
        pen = QtGui.QPen(color, 2, QtCore.Qt.DashLine if dependency else QtCore.Qt.SolidLine)
        item = self.scene.addPath(path, pen)
        item.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)
        item.setData(0, f'{"Provider dependency" if dependency else "Intended event"}\n{_identity_text(source)}\n->\n{_identity_text(target)}\n{label}\n{detail}')
        point = path.pointAtPercent(1)
        previous = path.pointAtPercent(0.97)
        angle = math.atan2(point.y() - previous.y(), point.x() - previous.x())
        arrow = QtGui.QPolygonF([point, point - QtCore.QPointF(10 * math.cos(angle - 0.5), 10 * math.sin(angle - 0.5)),
                                 point - QtCore.QPointF(10 * math.cos(angle + 0.5), 10 * math.sin(angle + 0.5))])
        marker = self.scene.addPolygon(arrow, QtGui.QPen(color), QtGui.QBrush(color))
        marker.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        text = self.scene.addSimpleText(label)
        text.setBrush(QtGui.QBrush(color))
        midpoint = path.pointAtPercent(0.5)
        text.setPos(midpoint.x() - text.boundingRect().width() / 2,
                    midpoint.y() - text.boundingRect().height() - 4)
        text.setAcceptedMouseButtons(QtCore.Qt.NoButton)

    def _selection_changed(self):
        selected = self.scene.selectedItems()
        self.details.setPlainText(selected[0].data(0) if selected else '')

    def fit(self):
        if not self.scene.itemsBoundingRect().isEmpty():
            self.view.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def close_requests(self):
        self.requests.close()