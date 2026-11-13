import os
import select
import signal
import sqlite3
import subprocess
import sys
import json
import threading
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from python_qt_binding import QtCore, QtWidgets

from fabric_experience_gui.app import InspectorMainWindow, InspectorWidget, ensure_application
from fabric_experience_gui.audits.planner_prompt_audit_summary import export_planner_prompt_audit_summary
from fabric_experience_gui.audits.retrieval_prompt_audit import export_retrieval_prompt_audit
from fabric_experience_gui.fabric_graph import Dependency, Event, FabricGraph, GraphCapture, InstanceId, ProviderId
from fabric_experience_gui.ui.fabric_graph_requests import FabricGraphRequests, _active_requests
from fabric_experience_gui.ui.fabric_graph_view import FabricGraphWidget
from test_sqlite_reader import create_minimal_db


def test_navigation_and_experience_controls():
    app = ensure_application([])
    widget = InspectorWidget()
    widget.resize(1200, 800)
    widget.show()
    app.processEvents()
    tabs = widget.notebook
    assert [tabs.tabText(index) for index in range(tabs.count())] == ['Fabric', 'Experience']
    fabric = tabs.widget(0)
    assert [fabric.tabText(index) for index in range(fabric.count())] == [
        'Generative Graph', 'Live Graph Execution', 'Graph Editor']
    widget.generation_prompt.setPlainText('Inspect the room')
    assert widget.generation_prompt.toPlainText() == 'Inspect the room'
    assert not widget.generate_button.isEnabled()
    assert widget.generated_plan_preview.isReadOnly()
    experience = widget.experience_tabs
    assert [experience.tabText(index) for index in range(experience.count())] == [
        'Plan Sandbox', 'Inspect GraphRAG', 'Decision Support', 'Feedback Ingestion']
    for index, expected in (
        (1, ['Overview', 'Nodes', 'Edges', 'Communities']),
        (2, ['Request Review', 'Calibration Review', 'Decision Support']),
        (3, ['Plan Feedback', 'Scoring Epochs', 'Node Explanations', 'Prompt Audits']),
    ):
        group = experience.widget(index)
        assert [group.tabText(child) for child in range(group.count())] == expected
    assert not widget.db_path_edit.isVisible()
    tabs.setCurrentIndex(1)
    app.processEvents()
    assert widget.db_path_edit.isVisible() and widget.db_path_edit.toolTip()
    assert not widget.jobs_scroll.isVisible()
    jobs = next(button for button in widget.findChildren(QtWidgets.QPushButton)
                if button.text() == 'Analysis Jobs')
    jobs.click()
    app.processEvents()
    assert widget.jobs_scroll.isVisible()
    defaults = next(button for button in widget.jobs_panel.findChildren(QtWidgets.QPushButton)
                    if button.text() == 'Use Current Defaults')
    assert 'Replace the analysis paths' in defaults.toolTip()
    assert 'threshold' in widget.jobs_panel.high_prompt_spin.toolTip()
    for button in widget.findChildren(QtWidgets.QPushButton):
        assert button.toolTip(), button.text()
    for edit in widget.findChildren(QtWidgets.QLineEdit):
        if not isinstance(edit.parent(), QtWidgets.QAbstractSpinBox):
            assert edit.toolTip(), edit.placeholderText()
    tabs.setCurrentIndex(0)
    app.processEvents()
    assert not widget.jobs_scroll.isVisible() and not widget.db_path_edit.isVisible()
    widget.close()


def test_xml_draft_load_save_and_syntax(tmp_path, monkeypatch):
    app = ensure_application([])
    widget = InspectorWidget()
    draft = widget.draft_editor
    original = '<?xml version="1.0"?>\n<Plan><Unknown keep="value" /></Plan>\n'
    source = tmp_path / 'source.xml'
    destination = tmp_path / 'draft.xml'
    source.write_text(original, encoding='utf-8')
    monkeypatch.setattr(widget.fabric_graph_widget.requests, 'request',
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('unexpected ROS request')))
    monkeypatch.setattr(QtWidgets.QFileDialog, 'getOpenFileName', lambda *args: (str(source), ''))
    monkeypatch.setattr(QtWidgets.QFileDialog, 'getSaveFileName', lambda *args: (str(destination), ''))
    draft.load_draft()
    assert draft.editor.toPlainText() == original
    draft.check_xml()
    assert 'have not been validated' in draft.status.text()
    draft.editor.insertPlainText(' ')
    assert 'syntax has not been checked' in draft.status.text()
    draft.editor.setPlainText(original)
    draft.save_draft()
    assert destination.read_text(encoding='utf-8') == original
    draft.editor.setPlainText('<Plan>')
    draft.check_xml()
    assert 'syntax error' in draft.status.text()
    draft.editor.setPlainText('<Other/>')
    draft.check_xml()
    assert 'Plan root' in draft.status.text()
    draft.editor.document().setModified(True)
    monkeypatch.setattr(QtWidgets.QFileDialog, 'getSaveFileName',
                        lambda *args: (str(tmp_path / 'missing' / 'draft.xml'), ''))
    draft.save_draft()
    assert draft.editor.document().isModified()
    assert 'Could not save' in draft.status.text()
    draft.editor.document().setModified(False)
    widget.close()
    app.processEvents()


def test_xml_draft_unsaved_changes_protect_load_and_close(tmp_path, monkeypatch):
    app = ensure_application([])
    window = InspectorMainWindow()
    window.show()
    app.processEvents()
    draft = window.widget.draft_editor
    draft.editor.insertPlainText('<Plan/>')
    assert draft.editor.document().isModified()
    monkeypatch.setattr(QtWidgets.QMessageBox, 'question', lambda *args: QtWidgets.QMessageBox.Cancel)
    monkeypatch.setattr(QtWidgets.QFileDialog, 'getOpenFileName',
                        lambda *args: (_ for _ in ()).throw(AssertionError('load should be cancelled')))
    draft.load_draft()
    draft.new_draft()
    assert draft.editor.toPlainText() == '<Plan/>'
    assert not window.close()
    assert window.isVisible()
    monkeypatch.setattr(QtWidgets.QMessageBox, 'question', lambda *args: QtWidgets.QMessageBox.Discard)
    assert window.close()
    app.processEvents()


def test_rqt_shutdown_requires_resolving_unsaved_draft(tmp_path, monkeypatch):
    from fabric_experience_gui.plugin import ExperienceInspectorPlugin

    app = ensure_application([])

    class Context(QtCore.QObject):
        def argv(self):
            return []

        def serial_number(self):
            return 1

        def add_widget(self, widget):
            self.widget = widget

    context = Context()
    plugin = ExperienceInspectorPlugin(context)
    draft = context.widget.draft_editor
    draft.editor.insertPlainText('<Plan/>')
    destination = tmp_path / 'draft.xml'
    paths = iter(['', str(tmp_path / 'missing' / 'draft.xml'), str(destination)])
    messages = []
    monkeypatch.setattr(QtWidgets.QFileDialog, 'getSaveFileName', lambda *args: (next(paths), ''))

    def choose_save(_parent, _title, message, *_args):
        messages.append(message)
        assert len(messages) <= 3
        return QtWidgets.QMessageBox.Save

    monkeypatch.setattr(QtWidgets.QMessageBox, 'warning', choose_save)
    plugin.shutdown_plugin()
    assert len(messages) == 3
    assert 'cannot cancel' in messages[0]
    assert 'not saved' in messages[1] and 'not saved' in messages[2]
    assert destination.read_text(encoding='utf-8') == '<Plan/>'
    assert not draft.editor.document().isModified()
    app.processEvents()


def test_rqt_shutdown_explicitly_discards_draft(monkeypatch):
    from fabric_experience_gui.plugin import ExperienceInspectorPlugin

    app = ensure_application([])

    class Context(QtCore.QObject):
        def argv(self):
            return []

        def serial_number(self):
            return 1

        def add_widget(self, widget):
            self.widget = widget

    context = Context()
    plugin = ExperienceInspectorPlugin(context)
    context.widget.draft_editor.editor.insertPlainText('<Plan/>')
    monkeypatch.setattr(QtWidgets.QMessageBox, 'warning', lambda *args: QtWidgets.QMessageBox.Discard)
    monkeypatch.setattr(QtWidgets.QFileDialog, 'getSaveFileName',
                        lambda *args: (_ for _ in ()).throw(AssertionError('unexpected save')))
    plugin.shutdown_plugin()
    assert not context.widget.draft_editor.editor.document().isModified()
    app.processEvents()


def test_fabric_graph_requests_switch_failure_and_close():
    app = ensure_application([])
    started = threading.Event()
    release = threading.Event()
    closed = []

    class Client:
        def snapshot(self, include_dependencies=False):
            started.set()
            assert release.wait(5)
            return 'obsolete'

        def parse(self, plan_xml):
            if plan_xml == 'bad':
                raise TimeoutError('parse timed out')
            return plan_xml

        def close(self):
            closed.append(True)

    def wait_for(predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            threading.Event().wait(0.005)
        assert predicate()

    requests = FabricGraphRequests(client_factory=Client)
    captures = []
    failures = []
    busy = []
    requests.capture_ready.connect(captures.append)
    requests.failed.connect(failures.append)
    requests.busy_changed.connect(busy.append)
    requests.request('live')
    assert started.wait(5)
    requests.request('loaded', 'current')
    release.set()
    wait_for(lambda: captures == ['current'] and busy[-1:] == [False])
    assert failures == []
    assert len(closed) == 2

    requests.request('loaded', 'bad')
    wait_for(lambda: failures == ['parse timed out'] and busy[-1:] == [False])
    assert len(closed) == 3

    started.clear()
    release.clear()
    requests.request('live')
    assert started.wait(5)
    requests.close()
    release.set()
    wait_for(lambda: len(closed) == 4 and busy[-1:] == [False])
    assert captures == ['current']
    assert failures == ['parse timed out']


def test_fabric_graph_widget_levels_selection_and_status():
    app = ensure_application([])
    widget = FabricGraphWidget()
    widget.resize(1000, 700)
    widget.show()
    app.processEvents()
    assert widget.view.width() > widget.details.width()
    first = InstanceId('interface/' + 'long_name_' * 15, 'provider/first', 1)
    second = InstanceId(first.interface, first.provider, 2)
    other = InstanceId('interface/other', 'provider/other', 3)
    events = (Event(first, second, 'on_success', 'first', 0),
              Event(first, second, 'on_failure', 'second', 0),
              Event(second, other, 'on_start', 'third', 0))
    dependency = Dependency(first.provider_id, ProviderId('interface/dependency', 'provider/dependency'))
    graph = FabricGraph((first, second, other), events, (dependency,), True)
    widget._capture_ready(GraphCapture('live', graph, True, True, 'plan-id', 12, (1, 2)))

    def items(kind):
        return [item for item in widget.scene.items() if isinstance(item, kind)]

    nodes = items(QtWidgets.QGraphicsRectItem)
    paths = items(QtWidgets.QGraphicsPathItem)
    assert len(nodes) == 2 and len(paths) == 3
    loops = [path for path in paths if 'on_success' in path.data(0) or 'on_failure' in path.data(0)]
    assert len(loops) == 2 and loops[0].path().boundingRect() != loops[1].path().boundingRect()
    for loop in loops:
        event_label = 'on_success' if 'on_success' in loop.data(0) else 'on_failure'
        label = next(item for item in widget.scene.items()
                     if isinstance(item, QtWidgets.QGraphicsSimpleTextItem) and item.text() == event_label)
        assert label.sceneBoundingRect().bottom() < loop.path().pointAtPercent(0.5).y()
    for node in nodes:
        label = node.childItems()[0]
        assert label.boundingRect().width() * label.scale() <= node.rect().width()
    long_node = next(node for node in nodes if first.interface in node.toolTip())
    assert long_node.childItems()[0].text() == first.interface
    assert first.provider in long_node.toolTip()
    long_node.setSelected(True)
    app.processEvents()
    assert first.interface in widget.details.toPlainText()
    assert 'Instances: 2' in widget.details.toPlainText()

    widget.level.setCurrentIndex(1)
    assert len(items(QtWidgets.QGraphicsRectItem)) == 3
    assert len(items(QtWidgets.QGraphicsPathItem)) == 3
    widget.level.setCurrentIndex(2)
    assert len(items(QtWidgets.QGraphicsRectItem)) == 5
    assert len(items(QtWidgets.QGraphicsPathItem)) == 4
    assert 'separately sampled' in widget.status.text()
    dependency_path = next(item for item in items(QtWidgets.QGraphicsPathItem) if 'Provider dependency' in item.data(0))
    dependency_path.setSelected(True)
    assert 'interface/dependency' in widget.details.toPlainText()
    widget.filter.setText('other')
    assert len(items(QtWidgets.QGraphicsRectItem)) == 1
    assert not items(QtWidgets.QGraphicsPathItem)
    widget._failed('timeout')
    widget.level.setCurrentIndex(0)
    assert 'stale' in widget.status.text() and 'timeout' in widget.status.text()
    widget.close_requests()


def test_fabric_graph_opposite_event_labels_do_not_overlap():
    app = ensure_application([])
    widget = FabricGraphWidget()
    first = InstanceId('demo/First', 'demo/First', 1)
    second = InstanceId('demo/Second', 'demo/Second', 2)
    graph = FabricGraph((first, second), (
        Event(first, second, 'on_success', '', 0),
        Event(second, first, 'on_failure', '', 0),
    ), (), False)
    widget._capture_ready(GraphCapture('live', graph, True, True))
    labels = [item for item in widget.scene.items()
              if isinstance(item, QtWidgets.QGraphicsSimpleTextItem)
              and item.text() in ('on_success', 'on_failure')]
    assert len(labels) == 2
    assert not labels[0].sceneBoundingRect().intersects(labels[1].sceneBoundingRect())
    widget.close_requests()
    app.processEvents()


def test_fabric_graph_widget_new_empty_file_invalidates_capture(tmp_path, monkeypatch):
    app = ensure_application([])
    widget = FabricGraphWidget()
    widget.source.setCurrentIndex(1)
    widget.loaded_path = 'old.xml'
    widget.loaded_xml = '<old/>'
    widget._capture_ready(GraphCapture('loaded', FabricGraph((), (), (), False), True, True))
    new_file = tmp_path / 'empty.xml'
    new_file.write_text('', encoding='utf-8')
    monkeypatch.setattr(QtWidgets.QFileDialog, 'getOpenFileName', lambda *args: (str(new_file), ''))
    requests = []
    monkeypatch.setattr(widget.requests, 'request', lambda *args, **kwargs: requests.append((args, kwargs)))
    widget._load_xml()
    assert widget.capture is None
    assert requests[0][0] == ('loaded', '')
    widget._failed('invalid XML')
    assert 'invalid XML' in widget.status.text() and 'stale' not in widget.status.text()
    widget.close_requests()
    app.processEvents()


def test_fabric_graph_requests_survive_parent_destruction():
    app = ensure_application([])
    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()

    class Client:
        def snapshot(self, include_dependencies=False):
            started.set()
            assert release.wait(5)
            return 'late'

        def close(self):
            closed.set()

    parent = QtWidgets.QWidget()
    requests = FabricGraphRequests(parent, client_factory=Client)
    requests.request('live')
    assert started.wait(5)
    requests.close()
    parent.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    release.set()
    deadline = time.monotonic() + 5
    while (not closed.is_set() or _active_requests) and time.monotonic() < deadline:
        app.processEvents()
        threading.Event().wait(0.005)
    assert closed.is_set() and not _active_requests


def test_standalone_exits_on_sigint():
    script = '''
import fabric_experience_gui.app as app
original_show = app.InspectorMainWindow.show
def show(window):
    original_show(window)
    print('ready', flush=True)
app.InspectorMainWindow.show = show
raise SystemExit(app.main([]))
'''
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(PACKAGE_ROOT) + os.pathsep + environment.get('PYTHONPATH', '')
    process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, env=environment)
    try:
        assert select.select([process.stdout], [], [], 10)[0], 'GUI did not start'
        assert process.stdout.readline().strip() == 'ready'
        process.send_signal(signal.SIGINT)
        _, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_standalone_sigint_waits_for_active_graph_request():
    script = '''
import threading
import fabric_experience_gui.app as app
started = threading.Event()
class Client:
    def snapshot(self, include_dependencies=False):
        started.set()
        threading.Event().wait(0.5)
    def close(self):
        print('client closed', flush=True)
original_show = app.InspectorMainWindow.show
def show(window):
    window.widget.fabric_graph_widget.requests._client_factory = Client
    window.widget.fabric_graph_widget.refresh()
    assert started.wait(5)
    original_show(window)
    print('ready', flush=True)
app.InspectorMainWindow.show = show
raise SystemExit(app.main([]))
'''
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(PACKAGE_ROOT) + os.pathsep + environment.get('PYTHONPATH', '')
    process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, env=environment)
    try:
        assert select.select([process.stdout], [], [], 10)[0], 'GUI did not start'
        assert process.stdout.readline().strip() == 'ready'
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stderr
        assert 'client closed' in stdout
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_fabric_graph_requests_finish_on_process_exit():
    script = '''
import threading
from fabric_experience_gui.app import ensure_application
from fabric_experience_gui.ui.fabric_graph_requests import FabricGraphRequests
started = threading.Event()
class Client:
    def snapshot(self, include_dependencies=False):
        started.set()
        threading.Event().wait(0.1)
        return None
    def close(self):
        print('client closed', flush=True)
app = ensure_application([])
requests = FabricGraphRequests(client_factory=Client)
requests.request('live')
assert started.wait(5)
requests.close()
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'client closed' in result.stdout


def test_fabric_graph_widget_real_services_recover_without_mutation(monkeypatch):
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from capabilities2_msgs.srv import ConnectCapability, TriggerCapability
    from fabric_msgs.msg import FabricConnection, FabricNode, FabricStatus
    from fabric_msgs.srv import CancelFabricPlan, GetFabricPlanSnapshot, ParsePlan, SubmitFabricPlan
    from fabric_experience_gui.services.fabric_graph_client import FabricGraphClient

    monkeypatch.setenv('ROS_DOMAIN_ID', str(100 + os.getpid() % 100))
    monkeypatch.setenv('ROS_LOCALHOST_ONLY', '1')
    context = Context()
    rclpy.init(context=context)
    node = Node('inspector_read_only_test', context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    app = ensure_application([])
    widget = FabricGraphWidget(client_factory=lambda: FabricGraphClient(timeout_sec=1.0))
    requests = []
    mutations = []
    source = FabricNode(interface='demo/Source', provider='demo/Source', instance_id=1)
    target = FabricNode(interface='demo/Target', provider='demo/Target', instance_id=2)
    edge = FabricConnection(source=source, on_success=target)

    def snapshot_callback(request, response):
        requests.append('snapshot')
        response.has_plan = True
        response.plan_id = 'controlled-plan'
        response.status.code = FabricStatus.RUNNING
        response.connections_complete = True
        response.instances = [source, target]
        response.connections = [edge]
        return response

    def parse_callback(request, response):
        requests.append(('parse', request.plan))
        response.success = True
        response.connections = [edge]
        return response

    def mutation_callback(request, response):
        mutations.append(True)
        return response

    def wait_for(predicate):
        deadline = time.monotonic() + 8
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            threading.Event().wait(0.01)
        assert predicate(), widget.status.text()

    try:
        snapshot_service = node.create_service(GetFabricPlanSnapshot, '/fabric/plan/get_snapshot', snapshot_callback)
        node.create_service(ParsePlan, '/fabric/plan/parse', parse_callback)
        node.create_service(SubmitFabricPlan, '/fabric/plan/submit', mutation_callback)
        node.create_service(CancelFabricPlan, '/fabric/plan/cancel', mutation_callback)
        node.create_service(ConnectCapability, '/capabilities/connect_capability', mutation_callback)
        node.create_service(TriggerCapability, '/capabilities/trigger_capability', mutation_callback)

        widget.refresh()
        wait_for(lambda: widget.capture is not None and not widget.refreshing)
        assert widget.capture.plan_id == 'controlled-plan'
        assert widget.capture.graph.events[0].label == 'on_success'
        widget.level.setCurrentIndex(1)
        widget.filter.setText('demo')
        widget.fit()
        assert requests == ['snapshot']

        node.destroy_service(snapshot_service)
        widget.refresh()
        wait_for(lambda: bool(widget.error) and not widget.refreshing)
        assert 'stale' in widget.status.text()
        snapshot_service = node.create_service(GetFabricPlanSnapshot, '/fabric/plan/get_snapshot', snapshot_callback)
        widget.refresh()
        wait_for(lambda: not widget.error and not widget.refreshing)
        assert widget.capture.plan_id == 'controlled-plan'

        widget.source.setCurrentIndex(1)
        widget.loaded_path = 'controlled.xml'
        widget.loaded_xml = '<Plan />'
        widget.refresh()
        wait_for(lambda: widget.capture is not None and not widget.refreshing)
        assert widget.capture.source == 'loaded'
        assert requests == ['snapshot', 'snapshot', ('parse', '<Plan />')]
        assert not mutations
    finally:
        widget.close_requests()
        wait_for(lambda: not _active_requests)
        executor.shutdown()
        thread.join(timeout=5)
        node.destroy_node()
        rclpy.shutdown(context=context)


def test_qt_widget_smoke(tmp_path):
    app = ensure_application([])
    widget = InspectorWidget()

    db_path = tmp_path / 'core_graphrag.sqlite3'
    audit_root = tmp_path / 'planner_prompt_audit'
    audit_root.mkdir()

    widget.set_db_path(str(db_path))
    widget.set_audit_root(str(audit_root))

    assert widget.current_db_path() == str(db_path)
    assert widget.current_audit_root() == str(audit_root)

    widget.close()
    app.processEvents()


def test_qt_widget_filters_and_graph_view(tmp_path):
    app = ensure_application([])
    db_path = tmp_path / 'core_graphrag.sqlite3'
    create_minimal_db(db_path)

    widget = InspectorWidget(initial_db_path=str(db_path))

    assert 'nodes: 2' in widget.graph_summary_box.toPlainText().lower()
    assert 'edges: 1' in widget.graph_summary_box.toPlainText().lower()

    widget.filter_edits['Nodes'].setText('DetectObject')
    widget.apply_filter('Nodes')
    nodes_table = widget.tables['Nodes']
    assert nodes_table.isRowHidden(0) is False

    widget.filter_columns['Nodes'].setCurrentText('provider')
    widget.filter_edits['Nodes'].setText('demo')
    widget.apply_filter('Nodes')
    assert nodes_table.isRowHidden(0) is False

    widget.secondary_filter_columns['Nodes'].setCurrentText('name')
    widget.secondary_filter_edits['Nodes'].setText('DetectObject')
    widget.apply_filter('Nodes')
    assert widget.proxies['Nodes'].rowCount() == 1

    widget.graph_node_filter_edit.setText('DetectObject')
    widget.apply_graph_filter()
    assert widget.graph_node_list.count() >= 1
    assert len(widget.graph_node_items) >= 2

    first_visible = widget._first_visible_graph_item()
    assert first_visible is not None
    widget.graph_node_list.setCurrentItem(first_visible)
    app.processEvents()

    assert 'incident_edges: 1' in widget.graph_node_preview.toPlainText()
    assert widget.graph_neighbor_table.rowCount() == 1
    selected_node_id = first_visible.data(0x0100)
    widget.select_graph_node_by_id(selected_node_id)
    app.processEvents()
    assert widget.current_graph_node_id == selected_node_id
    assert widget.graph_node_items[selected_node_id].pen().widthF() >= 3.0

    widget.close()
    app.processEvents()


def test_qt_widget_export_helpers(tmp_path):
    app = ensure_application([])
    db_path = tmp_path / 'core_graphrag.sqlite3'
    create_minimal_db(db_path)

    audit_root = tmp_path / 'planner_prompt_audit'
    audit_root.mkdir()
    (audit_root / 'req_1_10_20.json').write_text(
        '{\n'
        '  "planning_request_id": "req_1",\n'
        '  "request_uuid": "uuid_1",\n'
        '  "iterations": {\n'
        '    "iteration_1": {\n'
        '      "phase": "generation",\n'
        '      "selected_semantic_context_mode": "detailed",\n'
        '      "prompt_comparison": {\n'
        '        "detailed_chars": 1500,\n'
        '        "community_chars": 900,\n'
        '        "reduction_chars": 600,\n'
        '        "reduction_ratio": 0.4\n'
        '      },\n'
        '      "semantic_counts": {\n'
        '        "community_summaries": 1,\n'
        '        "relevant_capabilities": 2\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )

    widget = InspectorWidget(initial_db_path=str(db_path), initial_audit_root=str(audit_root))

    retrieval_out = tmp_path / 'retrieval_prompt_audit'
    summary_out = tmp_path / 'planner_prompt_audit_exports'

    retrieval_report = export_retrieval_prompt_audit(db_path, retrieval_out)
    summary_report = export_planner_prompt_audit_summary(audit_root, summary_out)

    assert retrieval_report['summary']['plan_count'] == 1
    assert summary_report['summary']['request_count'] == 1
    assert (retrieval_out / 'retrieval_prompt_audit.json').exists()
    assert (summary_out / 'planner_prompt_audit_summary.json').exists()

    widget.close()
    app.processEvents()


def test_analysis_jobs_panel_defaults(tmp_path):
    app = ensure_application([])
    db_path = tmp_path / 'core_graphrag.sqlite3'
    create_minimal_db(db_path)
    audit_root = tmp_path / 'planner_prompt_audit'
    audit_root.mkdir()

    window = InspectorMainWindow(initial_db_path=str(db_path), initial_audit_root=str(audit_root))

    assert window.jobs_panel.retrieval_out_edit.text().endswith('retrieval_prompt_audit')
    assert window.jobs_panel.summary_out_edit.text().endswith('planner_prompt_audit_exports')
    assert window.jobs_panel.calibration_out_edit.text().endswith('terminal_success_analysis')
    assert window.jobs_panel.plot_path_edit.text().endswith('_3d_graph.png')
    assert '_proposal_' in window.jobs_panel.proposal_path_edit.text()

    window.close()
    app.processEvents()


def test_plan_sandbox_parse_and_overlay(tmp_path):
    app = ensure_application([])
    widget = InspectorWidget()

    widget.plan_xml_edit.setPlainText(
        '<Plan>'
        '<Control type="sequential">'
        '<Runner name="detect" />'
        '<Runner name="pick" />'
        '</Control>'
        '</Plan>'
    )
    widget.plan_score_edit.setPlainText(
        '{'
        '"final_rapfs": 0.72,'
        '"expected_runtime_seconds": 5.5,'
        '"score_components": "runtime=5.5;success=0.8",'
        '"node_explanations": ['
        '  {'
        '    "candidate_node_id": "runner_1",'
        '    "skill_name": "detect",'
        '    "reason": "matched evidence"'
        '  }'
        ']'
        '}'
    )

    widget.parse_plan_sandbox()
    app.processEvents()

    assert len(widget.plan_nodes) >= 4
    assert len(widget.plan_edges) >= 3
    assert 'expected_runtime_seconds: 5.5' in widget.plan_summary_box.toPlainText()
    assert len(widget.plan_node_items) >= 4

    widget.select_plan_node_by_id('runner_1')
    app.processEvents()

    assert widget.current_plan_node_id == 'runner_1'
    assert 'matched evidence' in widget.plan_preview_box.toPlainText()
    assert widget.plan_node_items['runner_1'].pen().widthF() >= 3.0

    widget.close()
    app.processEvents()


def test_tuning_proposal_export(tmp_path):
    app = ensure_application([])
    db_path = tmp_path / 'core_graphrag.sqlite3'
    create_minimal_db(db_path)

    widget = InspectorWidget(initial_db_path=str(db_path))
    proposal_path = tmp_path / 'exports' / 'review_proposal.json'

    written_path = widget.run_tuning_proposal_export(
        proposal_path,
        proposal_kind='threshold_recalibration',
        summary='Review scoring threshold drift',
        notes='Observed mismatch between offline review and runtime decisions.',
    )

    assert written_path == proposal_path
    proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
    assert proposal['proposal_kind'] == 'threshold_recalibration'
    assert proposal['read_only_policy']['mutates_database'] is False
    assert proposal['graph_snapshot']['node_count'] == 2

    widget.close()
    app.processEvents()


def test_request_review_joins_prompt_audit_explanations_and_generated_plan(tmp_path):
    app = ensure_application([])
    db_path = tmp_path / 'core_graphrag.sqlite3'
    create_minimal_db(db_path)

    audit_root = tmp_path / 'planner_prompt_audit'
    audit_root.mkdir()
    (audit_root / 'req_1_10_20.json').write_text(
        '{\n'
        '  "planning_request_id": "req_1",\n'
        '  "request_uuid": "uuid_1",\n'
        '  "iterations": {\n'
        '    "iteration_1": {\n'
        '      "phase": "generation",\n'
        '      "selected_semantic_context_mode": "detailed",\n'
        '      "prompt_comparison": {\n'
        '        "detailed_chars": 1500,\n'
        '        "community_chars": 900,\n'
        '        "reduction_chars": 600,\n'
        '        "reduction_ratio": 0.4\n'
        '      },\n'
        '      "semantic_counts": {\n'
        '        "community_summaries": 1,\n'
        '        "relevant_capabilities": 2\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )

    generated_root = tmp_path / 'generated'
    execution_root = generated_root / 'execution_1'
    execution_root.mkdir(parents=True)
    (execution_root / 'generated_plans.json').write_text(
        '{\n'
        '  "iteration_1": {\n'
        '    "selected_candidate_plan_id": "plan_1",\n'
        '    "plan_1": {\n'
        '      "planning_request_id": "req_1",\n'
        '      "candidate_plan_id": "plan_1",\n'
        '      "graph_hash": "graph_1",\n'
        '      "selected": true,\n'
        '      "feasible": true,\n'
        '      "terminal_success_estimate": 0.9,\n'
        '      "final_rapfs": 0.72,\n'
        '      "reasoning": "selected because evidence matched",\n'
        '      "plan": "<Plan><Runner name=\'detect\' /></Plan>"\n'
        '    }\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )

    widget = InspectorWidget(initial_db_path=str(db_path), initial_audit_root=str(audit_root))
    widget.set_generated_root(str(generated_root))
    widget.load_generated_plan_artifacts()
    app.processEvents()

    review = widget.request_review_widget
    assert review is not None
    assert review.request_list.count() == 1
    assert 'prompt_iterations: 1' in review.summary_box.toPlainText()
    assert 'iteration_1' in review.audit_box.toPlainText()
    assert 'selected because evidence matched' in review.generated_plan_box.toPlainText()
    assert review.explanation_table.rowCount() == 1
    assert 'semantic_community_summaries' in review.explanation_preview.toPlainText()

    widget.close()
    app.processEvents()


def test_decision_support_tab_summarizes_request_level_recommendations(tmp_path):
    app = ensure_application([])
    db_path = tmp_path / 'core_graphrag.sqlite3'
    create_minimal_db(db_path)

    audit_root = tmp_path / 'planner_prompt_audit'
    audit_root.mkdir()
    (audit_root / 'req_1_10_20.json').write_text(
        '{\n'
        '  "planning_request_id": "req_1",\n'
        '  "request_uuid": "uuid_1",\n'
        '  "task_description": "pick the apple",\n'
        '  "iterations": {\n'
        '    "iteration_1": {\n'
        '      "phase": "generation",\n'
        '      "selected_semantic_context_mode": "community",\n'
        '      "prompt_comparison": {\n'
        '        "detailed_chars": 1500,\n'
        '        "community_chars": 900,\n'
        '        "reduction_ratio": 0.4\n'
        '      },\n'
        '      "semantic_counts": {\n'
        '        "community_summaries": 1,\n'
        '        "relevant_capabilities": 2\n'
        '      }\n'
        '    },\n'
        '    "iteration_2": {\n'
        '      "phase": "refinement",\n'
        '      "selected_semantic_context_mode": "community",\n'
        '      "prompt_comparison": {\n'
        '        "detailed_chars": 1600,\n'
        '        "community_chars": 950,\n'
        '        "reduction_ratio": 0.40625\n'
        '      },\n'
        '      "semantic_counts": {\n'
        '        "community_summaries": 2,\n'
        '        "relevant_capabilities": 2\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )

    generated_root = tmp_path / 'feedback'
    execution_root = generated_root / 'execution_1'
    execution_root.mkdir(parents=True)
    (execution_root / 'generated_plans.json').write_text(
        '{\n'
        '  "iteration_2": {\n'
        '    "selected_candidate_plan_id": "plan_1",\n'
        '    "plan_1": {\n'
        '      "planning_request_id": "req_1",\n'
        '      "candidate_plan_id": "plan_1",\n'
        '      "graph_hash": "graph_1",\n'
        '      "selected": true,\n'
        '      "feasible": true,\n'
        '      "terminal_success": true,\n'
        '      "terminal_success_estimate": 0.83,\n'
        '      "final_rapfs": 0.77,\n'
        '      "reasoning": "community context was sufficient",\n'
        '      "candidate_skill_name_list": ["detect", "pick"]\n'
        '    }\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )
    (execution_root / 'user_feedback.json').write_text(
        '{\n'
        '  "1": {\n'
        '    "planning_request_id": "req_1",\n'
        '    "candidate_plan_id": "plan_1",\n'
        '    "graph_hash": "graph_1",\n'
        '    "outcome": "success",\n'
        '    "feedback_success": true,\n'
        '    "feedback": "operator confirmed"\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )

    widget = InspectorWidget(initial_db_path=str(db_path), initial_audit_root=str(audit_root))
    widget.set_generated_root(str(generated_root))
    widget.load_generated_plan_artifacts()
    app.processEvents()

    panel = widget.decision_support_widget
    assert panel is not None
    assert panel.request_table.rowCount() == 1
    assert 'favor_community: 1' in panel.summary_box.toPlainText()
    assert 'selected_predicted_success_probability' in panel.detail_box.toPlainText()
    assert 'selected_predicted_terminal_success_label' in panel.detail_box.toPlainText()
    assert 'community context was sufficient' in panel.detail_box.toPlainText()

    widget.close()
    app.processEvents()


def test_calibration_review_tab_summarizes_threshold_candidates(tmp_path):
    app = ensure_application([])
    db_path = tmp_path / 'core_graphrag.sqlite3'
    create_minimal_db(db_path)

    generated_root = tmp_path / 'feedback'
    for index, (request_id, score, success) in enumerate([
        ('req_1', 0.82, True),
        ('req_2', 0.68, True),
        ('req_3', 0.41, False),
        ('req_4', 0.22, False),
    ], start=1):
        execution_root = generated_root / f'execution_{index}'
        execution_root.mkdir(parents=True)
        (execution_root / 'generated_plans.json').write_text(
            '{\n'
            '  "iteration_1": {\n'
            f'    "selected_candidate_plan_id": "plan_{index}",\n'
            f'    "plan_{index}": {{\n'
            f'      "planning_request_id": "{request_id}",\n'
            f'      "candidate_plan_id": "plan_{index}",\n'
            f'      "graph_hash": "graph_{index}",\n'
            '      "selected": true,\n'
            '      "feasible": true,\n'
            f'      "terminal_success": {str(success).lower()},\n'
            f'      "terminal_success_estimate": {score},\n'
            f'      "final_rapfs": {score},\n'
            '      "reasoning": "test",\n'
            '      "candidate_skill_name_list": ["demo"]\n'
            '    }\n'
            '  }\n'
            '}\n',
            encoding='utf-8',
        )
        outcome = 'success' if success else 'failure'
        (execution_root / 'user_feedback.json').write_text(
            '{\n'
            '  "1": {\n'
            f'    "planning_request_id": "{request_id}",\n'
            f'    "candidate_plan_id": "plan_{index}",\n'
            f'    "graph_hash": "graph_{index}",\n'
            f'    "outcome": "{outcome}",\n'
            f'    "feedback_success": {str(success).lower()},\n'
            '    "feedback": "operator review"\n'
            '  }\n'
            '}\n',
            encoding='utf-8',
        )

    widget = InspectorWidget(initial_db_path=str(db_path))
    widget.set_generated_root(str(generated_root))
    widget.load_generated_plan_artifacts()
    app.processEvents()

    panel = widget.calibration_review_widget
    assert panel is not None
    assert panel.threshold_table.rowCount() >= 1
    assert panel.sample_table.rowCount() == 4
    assert 'best_single_threshold' in panel.summary_box.toPlainText()
    assert 'calibration_label_version' in panel.summary_box.toPlainText()
    assert 'recommended_success_threshold' in panel.detail_box.toPlainText()
    assert 'Runtime Policy Update' in panel.detail_box.toPlainText()

    widget.close()
    app.processEvents()


def test_review_tabs_can_jump_into_request_review(tmp_path):
    app = ensure_application([])
    db_path = tmp_path / 'core_graphrag.sqlite3'
    create_minimal_db(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO plan_node_score_explanation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            'req_1', 'plan_2', 'graph_2', 'runner_2', 'demo/PickObject', 'pick', 'task:pick', 'task:pick', 'pick',
            'task:pick', 'empirical', 'context_key', 'requested_skill', 'picked after detection', 0.8, 'pick,grasp',
            'apple,gripper', 'gripper_ready', 'detect_then_pick', 'slip', 'manipulation summary', 'success_probability',
            '0.95', '1', 'posterior', 11, 21, 'test'
        ),
    )
    connection.commit()
    connection.close()

    audit_root = tmp_path / 'planner_prompt_audit'
    audit_root.mkdir()
    (audit_root / 'req_1_10_20.json').write_text(
        '{\n'
        '  "planning_request_id": "req_1",\n'
        '  "request_uuid": "uuid_1",\n'
        '  "task_description": "pick the apple",\n'
        '  "iterations": {\n'
        '    "iteration_1": {\n'
        '      "phase": "generation",\n'
        '      "selected_semantic_context_mode": "community",\n'
        '      "prompt_comparison": {\n'
        '        "detailed_chars": 1500,\n'
        '        "community_chars": 900,\n'
        '        "reduction_ratio": 0.4\n'
        '      },\n'
        '      "semantic_counts": {\n'
        '        "community_summaries": 1,\n'
        '        "relevant_capabilities": 2\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )

    generated_root = tmp_path / 'feedback'
    execution_root = generated_root / 'execution_1'
    execution_root.mkdir(parents=True)
    (execution_root / 'generated_plans.json').write_text(
        '{\n'
        '  "iteration_1": {\n'
        '    "selected_candidate_plan_id": "plan_2",\n'
        '    "plan_1": {\n'
        '      "planning_request_id": "req_1",\n'
        '      "candidate_plan_id": "plan_1",\n'
        '      "graph_hash": "graph_1",\n'
        '      "selected": false,\n'
        '      "feasible": true,\n'
        '      "terminal_success": false,\n'
        '      "terminal_success_estimate": 0.31,\n'
        '      "final_rapfs": 0.28,\n'
        '      "reasoning": "fallback plan",\n'
        '      "candidate_skill_name_list": ["detect"]\n'
        '    },\n'
        '    "plan_2": {\n'
        '      "planning_request_id": "req_1",\n'
        '      "candidate_plan_id": "plan_2",\n'
        '      "graph_hash": "graph_2",\n'
        '      "selected": true,\n'
        '      "feasible": true,\n'
        '      "terminal_success": true,\n'
        '      "terminal_success_estimate": 0.83,\n'
        '      "final_rapfs": 0.77,\n'
        '      "reasoning": "community context was sufficient",\n'
        '      "candidate_skill_name_list": ["detect", "pick"]\n'
        '    }\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )
    (execution_root / 'user_feedback.json').write_text(
        '{\n'
        '  "1": {\n'
        '    "planning_request_id": "req_1",\n'
        '    "candidate_plan_id": "plan_2",\n'
        '    "graph_hash": "graph_2",\n'
        '    "outcome": "success",\n'
        '    "feedback_success": true,\n'
        '    "feedback": "operator confirmed"\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )

    widget = InspectorWidget(initial_db_path=str(db_path), initial_audit_root=str(audit_root))
    widget.set_generated_root(str(generated_root))
    widget.load_generated_plan_artifacts()
    app.processEvents()

    assert widget.decision_support_widget is not None
    widget.decision_support_widget.open_selected_request()
    app.processEvents()
    assert widget.request_review_widget is not None
    assert 'planning_request_id: req_1' in widget.request_review_widget.summary_box.toPlainText()
    assert 'candidate_plan_id: plan_2' in widget.request_review_widget.generated_plan_box.toPlainText()
    assert 'community context was sufficient' in widget.request_review_widget.generated_plan_box.toPlainText()

    assert widget.calibration_review_widget is not None
    for row_index in range(widget.calibration_review_widget.sample_table.rowCount()):
        item = widget.calibration_review_widget.sample_table.item(row_index, 1)
        if item is not None and item.text() == 'plan_2':
            widget.calibration_review_widget.sample_table.selectRow(row_index)
            break
    widget.calibration_review_widget.open_selected_sample_request()
    app.processEvents()
    assert 'planning_request_id: req_1' in widget.request_review_widget.summary_box.toPlainText()
    assert 'candidate_plan_id: plan_2' in widget.request_review_widget.generated_plan_box.toPlainText()

    assert widget.open_request_review_for_request('req_1', candidate_node_id='runner_2') is True
    app.processEvents()
    assert 'picked after detection' in widget.request_review_widget.explanation_preview.toPlainText()

    widget.close()
    app.processEvents()


def test_plan_sandbox_live_scoring_success(tmp_path):
    app = ensure_application([])
    widget = InspectorWidget()

    widget.plan_task_description_edit.setText('pick object')
    widget.plan_request_id_edit.setText('req_1')
    widget.plan_candidate_id_edit.setText('plan_1')
    widget.plan_candidate_node_id_edit.setText('runner_1')
    widget.plan_xml_edit.setPlainText('<Plan><Runner name="detect" /></Plan>')

    def fake_score(task_description, plan_xml, planning_request_id='', candidate_plan_id='', candidate_node_id=''):
        assert task_description == 'pick object'
        assert planning_request_id == 'req_1'
        assert candidate_plan_id == 'plan_1'
        assert candidate_node_id == 'runner_1'
        return {
            'plan': {
                'final_rapfs': 0.72,
                'expected_runtime_seconds': 5.5,
                'planning_request_id': 'req_1',
                'candidate_plan_id': 'plan_1',
            },
            'node_explanations': [
                {
                    'candidate_node_id': 'runner_1',
                    'skill_name': 'detect',
                    'reason': 'matched evidence',
                }
            ],
        }

    widget._score_plan_live = fake_score
    widget.score_plan_sandbox_live()
    app.processEvents()

    assert '"final_rapfs": 0.72' in widget.plan_score_edit.toPlainText()
    assert 'expected_runtime_seconds: 5.5' in widget.plan_summary_box.toPlainText()
    assert widget.status_label.text() == 'Loaded live score response into the Plan Sandbox overlay.'

    widget.close()
    app.processEvents()


def test_plan_sandbox_live_scoring_failure_preserves_offline_state(monkeypatch):
    app = ensure_application([])
    widget = InspectorWidget()

    widget.plan_task_description_edit.setText('pick object')
    widget.plan_xml_edit.setPlainText('<Plan><Runner name="detect" /></Plan>')
    widget.plan_score_edit.setPlainText('{}')
    widget.parse_plan_sandbox()
    baseline_node_count = len(widget.plan_nodes)

    captured = []

    def fake_critical(_parent, _title, text):
        captured.append(text)
        return QtWidgets.QMessageBox.Ok

    def fail_score(*_args, **_kwargs):
        raise RuntimeError('live scoring unavailable: missing ROS score client dependencies (rclpy and fabric_msgs)')

    monkeypatch.setattr(QtWidgets.QMessageBox, 'critical', staticmethod(fake_critical))
    widget._score_plan_live = fail_score
    widget.score_plan_sandbox_live()
    app.processEvents()

    assert captured
    assert 'live scoring unavailable' in captured[0]
    assert widget.plan_score_edit.toPlainText() == '{}'
    assert len(widget.plan_nodes) == baseline_node_count

    widget.close()
    app.processEvents()