from __future__ import annotations

from collections import defaultdict
import json
from typing import Any, Dict, List

from fabric_experience_gui.storage.database import TableSnapshot


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