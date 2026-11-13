from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable


EVENT_FIELDS = ('on_start', 'on_stop', 'on_success', 'on_failure')


@dataclass(frozen=True, order=True)
class ProviderId:
    interface: str
    provider: str


@dataclass(frozen=True, order=True)
class InstanceId:
    interface: str
    provider: str
    instance_id: int

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId(self.interface, self.provider)


@dataclass(frozen=True, order=True)
class Event:
    source: InstanceId
    target: InstanceId
    label: str
    description: str
    occurrence: int


@dataclass(frozen=True, order=True)
class Dependency:
    source: ProviderId
    target: ProviderId


@dataclass(frozen=True)
class GraphNode:
    identity: InstanceId | ProviderId
    instances: tuple[InstanceId, ...]


@dataclass(frozen=True)
class GraphEdge:
    source: InstanceId | ProviderId
    target: InstanceId | ProviderId
    event: Event


@dataclass(frozen=True)
class GraphView:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    dependencies: tuple[Dependency, ...]


@dataclass(frozen=True)
class FabricGraph:
    instances: tuple[InstanceId, ...]
    events: tuple[Event, ...]
    dependencies: tuple[Dependency, ...]
    dependencies_known: bool

    def view(self, *, aggregate: bool = False, include_dependencies: bool = False) -> GraphView:
        groups: dict[InstanceId | ProviderId, list[InstanceId]] = {}
        for instance in self.instances:
            identity = instance.provider_id if aggregate else instance
            groups.setdefault(identity, []).append(instance)
        nodes = [GraphNode(identity, tuple(instances)) for identity, instances in sorted(groups.items())]
        edges = tuple(
            GraphEdge(
                event.source.provider_id if aggregate else event.source,
                event.target.provider_id if aggregate else event.target,
                event,
            )
            for event in self.events
        )
        dependencies = self.dependencies if include_dependencies else ()
        if include_dependencies and not aggregate:
            provider_instances: dict[ProviderId, list[InstanceId]] = {}
            for instance in self.instances:
                provider_instances.setdefault(instance.provider_id, []).append(instance)
            dependency_providers = {provider for dependency in dependencies for provider in (dependency.source, dependency.target)}
            nodes.extend(
                GraphNode(provider, tuple(provider_instances.get(provider, ())))
                for provider in sorted(dependency_providers)
            )
        elif include_dependencies:
            known_providers = set(groups)
            extra_providers = {dependency.target for dependency in dependencies} - known_providers
            nodes.extend(GraphNode(provider, ()) for provider in sorted(extra_providers))
        return GraphView(tuple(nodes), edges, dependencies)


@dataclass(frozen=True)
class GraphCapture:
    source: str
    graph: FabricGraph
    has_plan: bool
    connections_complete: bool
    plan_id: str = ''
    status_code: int | None = None
    capture_stamp: tuple[int, int] | None = None


def _instance(node) -> InstanceId | None:
    if not node.interface or not node.provider:
        return None
    return InstanceId(node.interface, node.provider, node.instance_id)


def build_fabric_graph(
    connections: Iterable, instances: Iterable = (), running_capabilities: Iterable | None = None
) -> FabricGraph:
    nodes = set()
    events = []
    for node in instances:
        instance = _instance(node)
        if instance is not None:
            nodes.add(instance)
    for connection in connections:
        source = _instance(connection.source)
        if source is not None:
            nodes.add(source)
        for label in EVENT_FIELDS:
            target = _instance(getattr(connection, label))
            if target is not None:
                nodes.add(target)
                if source is not None:
                    events.append((source, target, label, connection.description))
    occurrences = Counter()
    graph_events = []
    for event in sorted(events):
        occurrence = occurrences[event]
        occurrences[event] += 1
        graph_events.append(Event(*event, occurrence))
    plan_providers = {instance.provider_id for instance in nodes}
    dependencies = set()
    for running in running_capabilities if running_capabilities is not None else ():
        capability = running.capability
        source = ProviderId(capability.capability, capability.provider)
        if source not in plan_providers:
            continue
        for dependency in running.dependent_capabilities:
            if dependency.capability and dependency.provider:
                dependencies.add(Dependency(source, ProviderId(dependency.capability, dependency.provider)))
    return FabricGraph(tuple(sorted(nodes)), tuple(graph_events), tuple(sorted(dependencies)), running_capabilities is not None)


def capture_parsed_plan(response) -> GraphCapture:
    if not response.success:
        raise ValueError(response.error or 'Fabric plan parsing failed')
    return GraphCapture('loaded', build_fabric_graph(response.connections), True, True)


def capture_live_snapshot(response, running_capabilities: Iterable | None = None) -> GraphCapture:
    stamp = response.header.stamp
    graph = build_fabric_graph(
        response.connections if response.has_plan else (),
        response.instances if response.has_plan else (),
        running_capabilities,
    )
    return GraphCapture(
        'live', graph, response.has_plan, response.connections_complete,
        response.plan_id, response.status.code, (stamp.sec, stamp.nanosec),
    )