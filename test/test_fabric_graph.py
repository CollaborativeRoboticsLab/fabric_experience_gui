from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from fabric_experience_gui.fabric_graph import (
    Dependency, InstanceId, ProviderId, build_fabric_graph, capture_live_snapshot, capture_parsed_plan,
)


def node(interface='', provider='', instance_id=0):
    return SimpleNamespace(interface=interface, provider=provider, instance_id=instance_id)


def connection(source, *, on_start=None, on_stop=None, on_success=None, on_failure=None, description=''):
    return SimpleNamespace(
        source=source,
        on_start=on_start or node(),
        on_stop=on_stop or node(),
        on_success=on_success or node(),
        on_failure=on_failure or node(),
        description=description,
    )


def test_instances_and_aggregation_preserve_directed_parallel_events_and_self_loops():
    first = node('demo/Move', 'demo/Provider', 1)
    second = node('demo/Move', 'demo/Provider', 2)
    third = node('demo/Move', 'demo/OtherProvider', 3)
    connections = [
        connection(first, on_stop=second, on_success=second, description='parallel'),
        connection(second, on_failure=first),
        connection(third, on_start=first),
    ]
    graph = build_fabric_graph(connections)
    first_id = InstanceId('demo/Move', 'demo/Provider', 1)
    second_id = InstanceId('demo/Move', 'demo/Provider', 2)
    provider = ProviderId('demo/Move', 'demo/Provider')
    other_provider = ProviderId('demo/Move', 'demo/OtherProvider')

    instances = graph.view()
    assert len(instances.nodes) == 3
    assert {(edge.source, edge.target, edge.event.label) for edge in instances.edges} == {
        (first_id, second_id, 'on_stop'),
        (first_id, second_id, 'on_success'),
        (second_id, first_id, 'on_failure'),
        (InstanceId('demo/Move', 'demo/OtherProvider', 3), first_id, 'on_start'),
    }
    aggregate = graph.view(aggregate=True)
    assert len(aggregate.nodes) == 2
    assert next(item.instances for item in aggregate.nodes if item.identity == provider) == (first_id, second_id)
    assert [(edge.source, edge.target, edge.event.label) for edge in aggregate.edges].count(
        (provider, provider, 'on_success')
    ) == 1
    assert sum(edge.source == provider and edge.target == provider for edge in aggregate.edges) == 3
    assert any(edge.source == other_provider and edge.target == provider for edge in aggregate.edges)


def test_graph_ignores_invalid_endpoints_and_keeps_duplicate_edges_stable():
    source = node('demo/Source', 'demo/Provider', 1)
    target = node('demo/Target', 'demo/Provider', 2)
    duplicate = connection(source, on_success=target, description='same')
    invalid = connection(node('demo/Invalid', '', 3), on_start=target, on_stop=node('', 'demo/Provider', 4))
    graph = build_fabric_graph([duplicate, invalid, duplicate], instances=[source, node('demo/Orphan', 'demo/Provider', 5)])
    assert len(graph.instances) == 3
    assert len(graph.events) == 2
    assert [event.occurrence for event in graph.events] == [0, 1]
    assert graph == build_fabric_graph([duplicate, duplicate, invalid], instances=[source, node('demo/Orphan', 'demo/Provider', 5)])


def test_dependencies_remain_provider_level_with_unknown_instance_ownership():
    first = node('demo/Move', 'demo/MoveProvider', 1)
    second = node('demo/Move', 'demo/MoveProvider', 2)
    navigation = SimpleNamespace(capability='demo/Nav', provider='demo/NavProvider', instance_id='1')
    running = SimpleNamespace(
        capability=SimpleNamespace(capability='demo/Move', provider='demo/MoveProvider', instance_id='1'),
        dependent_capabilities=[navigation, navigation, SimpleNamespace(capability='demo/Unknown', provider='')],
    )
    unrelated = SimpleNamespace(
        capability=SimpleNamespace(capability='demo/Other', provider='demo/OtherProvider'),
        dependent_capabilities=[navigation],
    )
    graph = build_fabric_graph([connection(first, on_success=second)], running_capabilities=[running, unrelated])
    move = ProviderId('demo/Move', 'demo/MoveProvider')
    nav = ProviderId('demo/Nav', 'demo/NavProvider')
    assert graph.dependencies == (Dependency(move, nav),)
    assert not graph.view().dependencies
    view = graph.view(include_dependencies=True)
    assert view.dependencies == (Dependency(move, nav),)
    assert len(view.edges) == 1
    assert isinstance(view.edges[0].source, InstanceId)
    assert next(item.instances for item in view.nodes if item.identity == move) == (
        InstanceId('demo/Move', 'demo/MoveProvider', 1),
        InstanceId('demo/Move', 'demo/MoveProvider', 2),
    )
    assert next(item.instances for item in view.nodes if item.identity == nav) == ()
    assert all(isinstance(edge.source, ProviderId) and isinstance(edge.target, ProviderId) for edge in view.dependencies)
    assert graph.dependencies_known
    assert not build_fabric_graph([]).dependencies_known
    assert build_fabric_graph([], running_capabilities=[]).dependencies_known


def test_loaded_plan_and_live_snapshot_preserve_source_and_partial_state():
    source = node('demo/Move', 'demo/Provider', 1)
    target = node('demo/Move', 'demo/Provider', 2)
    loaded = capture_parsed_plan(SimpleNamespace(success=True, error='', connections=[connection(source, on_stop=target)]))
    assert loaded.source == 'loaded'
    assert loaded.has_plan and loaded.connections_complete
    assert loaded.plan_id == '' and loaded.capture_stamp is None
    assert loaded.graph.events[0].label == 'on_stop'
    with pytest.raises(ValueError, match='invalid plan'):
        capture_parsed_plan(SimpleNamespace(success=False, error='invalid plan', connections=[]))

    response = SimpleNamespace(
        has_plan=True, connections_complete=False, plan_id='plan-1',
        status=SimpleNamespace(code=2), header=SimpleNamespace(stamp=SimpleNamespace(sec=123, nanosec=456)),
        instances=[source], connections=[],
    )
    live = capture_live_snapshot(response, running_capabilities=[])
    assert live.source == 'live'
    assert live.has_plan and not live.connections_complete
    assert live.plan_id == 'plan-1' and live.status_code == 2 and live.capture_stamp == (123, 456)
    assert live.graph.instances == (InstanceId('demo/Move', 'demo/Provider', 1),)
    assert live.graph.dependencies_known
    response.has_plan = False
    response.plan_id = ''
    empty = capture_live_snapshot(response)
    assert not empty.has_plan and not empty.graph.instances and not empty.graph.events
    assert not empty.graph.dependencies_known


def test_generated_fabric_messages_are_accepted():
    messages = pytest.importorskip('fabric_msgs.msg')
    services = pytest.importorskip('fabric_msgs.srv')
    source = messages.FabricNode(interface='demo/Move', provider='demo/Provider', instance_id=1)
    target = messages.FabricNode(interface='demo/Move', provider='demo/Provider', instance_id=2)
    edge = messages.FabricConnection(source=source, on_success=target, description='move')
    parsed = services.ParsePlan.Response(success=True, connections=[edge])
    snapshot = services.GetFabricPlanSnapshot.Response(
        has_plan=True, connections_complete=True, plan_id='live-plan', instances=[source, target], connections=[edge],
    )
    loaded = capture_parsed_plan(parsed)
    live = capture_live_snapshot(snapshot)
    assert loaded.graph == live.graph
    assert live.plan_id == 'live-plan'
    assert live.graph.events[0].label == 'on_success'


def test_graph_client_timeout_and_recovery():
    from fabric_experience_gui.services.fabric_graph_client import FabricGraphClient

    class Future:
        def __init__(self, complete, response=None):
            self.complete = complete
            self.response = response
            self.cancelled = False

        def done(self):
            return self.complete

        def result(self):
            return self.response

        def cancel(self):
            self.cancelled = True

    class Client:
        available = False
        future = Future(False)
        removed = None

        def wait_for_service(self, timeout_sec):
            assert timeout_sec == 0.1
            return self.available

        def call_async(self, request):
            return self.future

        def remove_pending_request(self, future):
            self.removed = future

    class Executor:
        def spin_until_future_complete(self, future, timeout_sec):
            assert timeout_sec == 0.1

    graph_client = FabricGraphClient.__new__(FabricGraphClient)
    graph_client._timeout_sec = 0.1
    graph_client._executor = Executor()
    client = Client()
    with pytest.raises(RuntimeError, match='not available'):
        graph_client._request(client, object(), '/test')
    client.available = True
    with pytest.raises(TimeoutError, match='timed out'):
        graph_client._request(client, object(), '/test')
    assert client.removed is client.future and client.future.cancelled
    response = object()
    client.future = Future(True, response)
    assert graph_client._request(client, object(), '/test') is response


@pytest.mark.parametrize('timeout_sec', [0, -1, float('inf'), float('nan')])
def test_graph_client_requires_positive_timeout(timeout_sec):
    from fabric_experience_gui.services.fabric_graph_client import FabricGraphClient

    with pytest.raises(ValueError, match='positive'):
        FabricGraphClient(timeout_sec=timeout_sec)


def test_graph_client_captures_sources_and_optional_dependencies():
    from fabric_experience_gui.services.fabric_graph_client import FabricGraphClient

    class Request:
        pass

    graph_client = FabricGraphClient.__new__(FabricGraphClient)
    graph_client._parse_type = graph_client._snapshot_type = graph_client._running_type = SimpleNamespace(Request=Request)
    graph_client._parse = object()
    graph_client._snapshot = object()
    graph_client._running = object()
    source = node('demo/Move', 'demo/Provider', 1)
    target = node('demo/Move', 'demo/Provider', 2)
    edge = connection(source, on_success=target)
    snapshot = SimpleNamespace(
        has_plan=True, connections_complete=True, plan_id='live', status=SimpleNamespace(code=12),
        header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=2)), instances=[source, target],
        connections=[edge],
    )
    running = SimpleNamespace(
        capability=SimpleNamespace(capability='demo/Move', provider='demo/Provider'),
        dependent_capabilities=[SimpleNamespace(capability='demo/Nav', provider='demo/NavProvider')],
    )
    responses = {
        graph_client._parse: SimpleNamespace(success=True, error='', connections=[edge]),
        graph_client._snapshot: snapshot,
        graph_client._running: SimpleNamespace(running_capabilities=[running]),
    }
    requests = []

    def request(client, message, name):
        requests.append((client, message, name))
        result = responses[client]
        if isinstance(result, Exception):
            raise result
        return result

    graph_client._request = request
    loaded = graph_client.parse('<Plan />')
    assert loaded.source == 'loaded' and requests[-1][1].plan == '<Plan />'
    assert not loaded.graph.dependencies_known
    live = graph_client.snapshot(include_dependencies=True)
    assert live.source == 'live' and live.plan_id == 'live'
    assert live.graph.dependencies == (
        Dependency(ProviderId('demo/Move', 'demo/Provider'), ProviderId('demo/Nav', 'demo/NavProvider')),
    )
    responses[graph_client._running] = TimeoutError('timed out')
    assert not graph_client.snapshot(include_dependencies=True).graph.dependencies_known
    requests.clear()
    assert not graph_client.snapshot().graph.dependencies_known
    assert [name for _, _, name in requests] == ['/fabric/plan/get_snapshot']
    responses[graph_client._parse] = SimpleNamespace(success=False, error='invalid XML', connections=[])
    with pytest.raises(ValueError, match='invalid XML'):
        graph_client.parse('<Plan>')