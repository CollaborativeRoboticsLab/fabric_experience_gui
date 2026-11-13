#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


NODE_TYPE_LABELS = {
    0: 'capability',
    1: 'task_entity',
    2: 'context_entity',
    3: 'plan_pattern',
    4: 'fault_concept',
}

NODE_TYPE_COLORS = {
    0: '#1b9e77',
    1: '#d95f02',
    2: '#7570b3',
    3: '#e7298a',
    4: '#66a61e',
    None: '#7f7f7f',
}


def require_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            'numpy is required for GraphRAG layout generation. Install it in the active Python 3 environment.'
        ) from exc
    return np


def require_matplotlib_pyplot():
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            'matplotlib is required for GraphRAG plotting. Install it in the active Python 3 environment.'
        ) from exc
    return plt


@dataclass(frozen=True)
class NodeRecord:
    node_id: str
    name: str
    provider: str
    descriptions: str
    node_type: int | None
    level: int
    cluster_id: int | None
    feature_vector: tuple[float, ...]


@dataclass(frozen=True)
class EdgeRecord:
    edge_id: str
    source: str
    target: str
    relationship: str
    edge_type: str
    edge_strength_class: str
    structural_score: float


@dataclass(frozen=True)
class RuntimeEvidence:
    skill_name: str
    runs_completed: int
    runs_succeeded: int
    runs_failed: int
    warning_count: int
    error_count: int
    runtime_sample_count: int
    runtime_sum_seconds: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Read a core_graphrag SQLite database and save a 3D plot of connected nodes and edges.'
    )
    parser.add_argument('db_path', type=Path, help='Path to core_graphrag.sqlite3')
    parser.add_argument('--output', type=Path, help='Output image path.')
    parser.add_argument('--component', choices=('all', 'largest', 'seed'), default='all')
    parser.add_argument('--seed-node', help='Node id used with --component seed.')
    parser.add_argument('--drop-isolated', action='store_true')
    parser.add_argument('--label-nodes', action='store_true')
    parser.add_argument('--show', action='store_true')
    parser.add_argument('--runtime-overlay', choices=('auto', 'off'), default='auto')
    return parser.parse_args()


def parse_feature_vector(raw_value: str | None) -> tuple[float, ...]:
    if not raw_value:
        return ()
    values = []
    for item in raw_value.split(','):
        item = item.strip()
        if item:
            values.append(float(item))
    return tuple(values)


def fetch_nodes(connection: sqlite3.Connection) -> dict[str, NodeRecord]:
    graph_node_count = connection.execute('SELECT COUNT(*) FROM graph_node;').fetchone()[0]
    if graph_node_count > 0:
        rows = connection.execute(
            '''
            SELECT gn.id, COALESCE(ni.name, gn.id), COALESCE(ni.provider, ''), COALESCE(ni.descriptions, ''),
                   ni.type, COALESCE(gn.level, 0), gn.cluster_id, COALESCE(gn.feature_vector, '')
            FROM graph_node AS gn
            LEFT JOIN node_information AS ni ON ni.id = gn.id
            ORDER BY gn.id;
            '''
        ).fetchall()
    else:
        rows = connection.execute(
            '''
            SELECT ni.id, COALESCE(ni.name, ni.id), COALESCE(ni.provider, ''), COALESCE(ni.descriptions, ''),
                   ni.type, 0, NULL, ''
            FROM node_information AS ni
            ORDER BY ni.id;
            '''
        ).fetchall()

    nodes: dict[str, NodeRecord] = {}
    for row in rows:
        node = NodeRecord(
            node_id=row[0],
            name=row[1],
            provider=row[2],
            descriptions=row[3],
            node_type=row[4],
            level=row[5],
            cluster_id=row[6],
            feature_vector=parse_feature_vector(row[7]),
        )
        nodes[node.node_id] = node
    return nodes


def fetch_edges(connection: sqlite3.Connection, nodes: dict[str, NodeRecord]) -> list[EdgeRecord]:
    graph_edge_count = connection.execute('SELECT COUNT(*) FROM graph_edge;').fetchone()[0]
    if graph_edge_count > 0:
        rows = connection.execute(
            '''
            SELECT ge.id, ge.source, ge.target, COALESCE(ei.relationship, ''), COALESCE(ei.edge_type, ''),
                   COALESCE(ei.edge_strength_class, ''), COALESCE(ei.structural_score, 0.0)
            FROM graph_edge AS ge
            LEFT JOIN edge_information AS ei ON ei.id = ge.id
            ORDER BY ge.id;
            '''
        ).fetchall()
    else:
        rows = connection.execute(
            '''
            SELECT ei.id, ei.source, ei.target, COALESCE(ei.relationship, ''), COALESCE(ei.edge_type, ''),
                   COALESCE(ei.edge_strength_class, ''), COALESCE(ei.structural_score, 0.0)
            FROM edge_information AS ei
            ORDER BY ei.id;
            '''
        ).fetchall()

    nodes_by_endpoint: dict[str, str] = {}
    for node_id, node in nodes.items():
        nodes_by_endpoint.setdefault(node_id, node_id)
        nodes_by_endpoint.setdefault(node.name, node_id)
        if node.provider:
            nodes_by_endpoint.setdefault(node.provider, node_id)

    edges: list[EdgeRecord] = []
    for row in rows:
        source = nodes_by_endpoint.get(row[1], row[1])
        target = nodes_by_endpoint.get(row[2], row[2])
        if source not in nodes or target not in nodes:
            continue
        edges.append(
            EdgeRecord(
                edge_id=row[0],
                source=source,
                target=target,
                relationship=row[3],
                edge_type=row[4],
                edge_strength_class=row[5],
                structural_score=float(row[6] or 0.0),
            )
        )
    return edges


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        'SELECT 1 FROM sqlite_master WHERE type = \'table\' AND name = ? LIMIT 1;',
        (table_name,),
    ).fetchone()
    return row is not None


def fetch_runtime_evidence(connection: sqlite3.Connection, nodes: dict[str, NodeRecord], overlay_mode: str):
    if overlay_mode == 'off' or not table_exists(connection, 'skill_run_statistics'):
        return {}

    rows = connection.execute(
        '''
        SELECT skill_name, SUM(COALESCE(runs_completed, 0)), SUM(COALESCE(runs_succeeded, 0)),
               SUM(COALESCE(runs_failed, 0)), SUM(COALESCE(warning_count, 0)), SUM(COALESCE(error_count, 0)),
               SUM(COALESCE(runtime_sample_count, 0)), SUM(COALESCE(runtime_sum_seconds, 0.0))
        FROM skill_run_statistics
        WHERE COALESCE(skill_name, '') != ''
        GROUP BY skill_name
        ORDER BY skill_name;
        '''
    ).fetchall()

    by_name = {node.name: node_id for node_id, node in nodes.items()}
    evidence_by_node = {}
    for row in rows:
        node_id = by_name.get(row[0])
        if node_id is None:
            continue
        evidence_by_node[node_id] = RuntimeEvidence(
            skill_name=row[0],
            runs_completed=int(row[1] or 0),
            runs_succeeded=int(row[2] or 0),
            runs_failed=int(row[3] or 0),
            warning_count=int(row[4] or 0),
            error_count=int(row[5] or 0),
            runtime_sample_count=int(row[6] or 0),
            runtime_sum_seconds=float(row[7] or 0.0),
        )
    return evidence_by_node


def build_adjacency(nodes: dict[str, NodeRecord], edges: list[EdgeRecord]):
    adjacency = {node_id: set() for node_id in nodes}
    for edge in edges:
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)
    return adjacency


def connected_components(adjacency):
    remaining = set(adjacency)
    components = []
    while remaining:
        start = remaining.pop()
        queue = [start]
        component = [start]
        while queue:
            current = queue.pop()
            for neighbor in adjacency[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
                    component.append(neighbor)
        components.append(sorted(component))
    components.sort(key=len, reverse=True)
    return components


def select_nodes(nodes, edges, adjacency, component_mode, seed_node, drop_isolated):
    components = connected_components(adjacency)
    if drop_isolated:
        components = [component for component in components if len(component) > 1]
    if not components:
        return {}, [], []
    if component_mode == 'largest':
        selected_ids = set(components[0])
        components = [components[0]]
    elif component_mode == 'seed':
        if not seed_node:
            raise ValueError('--seed-node is required when --component seed is used')
        if seed_node not in nodes:
            raise ValueError(f"Seed node '{seed_node}' was not found in graph_node")
        matching = next((component for component in components if seed_node in component), None)
        if matching is None:
            raise ValueError(f"Seed node '{seed_node}' is not part of any selected connected component")
        selected_ids = set(matching)
        components = [matching]
    else:
        selected_ids = {node_id for component in components for node_id in component}

    selected_nodes = {node_id: nodes[node_id] for node_id in selected_ids}
    selected_edges = [edge for edge in edges if edge.source in selected_ids and edge.target in selected_ids]
    return selected_nodes, selected_edges, components


def project_feature_vectors(nodes):
    np = require_numpy()
    max_dim = max((len(node.feature_vector) for node in nodes), default=0)
    if max_dim == 0:
        return None
    matrix = np.zeros((len(nodes), max_dim), dtype=float)
    for row_index, node in enumerate(nodes):
        if node.feature_vector:
            matrix[row_index, : len(node.feature_vector)] = node.feature_vector
    if np.allclose(matrix, matrix[0]):
        return None
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    _, singular_values, right_vectors = np.linalg.svd(centered, full_matrices=False)
    usable_dims = min(3, right_vectors.shape[0], np.count_nonzero(singular_values > 1e-9))
    if usable_dims == 0:
        return None
    coords = centered @ right_vectors[:usable_dims].T
    if usable_dims < 3:
        coords = np.pad(coords, ((0, 0), (0, 3 - usable_dims)))
    return {node.node_id: coords[index] for index, node in enumerate(nodes)}


def force_layout_3d(component_nodes, component_edges, seed):
    np = require_numpy()
    rng = np.random.default_rng(seed)
    count = len(component_nodes)
    positions = {node_id: rng.normal(0.0, 0.3, size=3) for node_id in component_nodes}
    if count == 1:
        positions[component_nodes[0]] = np.zeros(3, dtype=float)
        return positions
    edge_pairs = [(edge.source, edge.target) for edge in component_edges]
    area = max(float(count), 1.0)
    optimal_distance = math.pow(area, 1.0 / 3.0)
    initial_step = 0.12
    for iteration in range(200):
        displacements = {node_id: np.zeros(3, dtype=float) for node_id in component_nodes}
        for index, source in enumerate(component_nodes):
            for target in component_nodes[index + 1:]:
                delta = positions[source] - positions[target]
                distance = max(np.linalg.norm(delta), 1e-6)
                direction = delta / distance
                repulsive_force = (optimal_distance * optimal_distance) / distance
                displacement = direction * repulsive_force
                displacements[source] += displacement
                displacements[target] -= displacement
        for source, target in edge_pairs:
            delta = positions[source] - positions[target]
            distance = max(np.linalg.norm(delta), 1e-6)
            direction = delta / distance
            attractive_force = (distance * distance) / max(optimal_distance, 1e-6)
            displacement = direction * attractive_force
            displacements[source] -= displacement
            displacements[target] += displacement
        step = initial_step * (1.0 - (iteration / 200.0))
        for node_id in component_nodes:
            norm = np.linalg.norm(displacements[node_id])
            if norm > 0:
                positions[node_id] += (displacements[node_id] / norm) * min(norm, step)
    return positions


def component_offsets(component_count):
    np = require_numpy()
    if component_count == 1:
        return [np.zeros(3, dtype=float)]
    columns = math.ceil(math.sqrt(component_count))
    offsets = []
    spacing = 4.0
    for index in range(component_count):
        row = index // columns
        column = index % columns
        offsets.append(np.array([column * spacing, row * spacing, 0.0], dtype=float))
    return offsets


def compute_positions(nodes, edges, components):
    ordered_nodes = [nodes[node_id] for node_id in sorted(nodes)]
    projected = project_feature_vectors(ordered_nodes)
    if projected is not None:
        return projected
    edges_by_component = defaultdict(list)
    component_lookup = {node_id: frozenset(component) for component in components for node_id in component}
    for edge in edges:
        edges_by_component[component_lookup[edge.source]].append(edge)
    positions = {}
    offsets = component_offsets(len(components))
    for index, component in enumerate(components):
        component_key = frozenset(component)
        local_positions = force_layout_3d(component, edges_by_component[component_key], seed=index + 1)
        offset = offsets[index]
        for node_id, position in local_positions.items():
            positions[node_id] = position + offset
    return positions


def node_sizes(adjacency, node_ids):
    np = require_numpy()
    return np.array([70.0 + 18.0 * len(adjacency[node_id]) for node_id in node_ids], dtype=float)


def runtime_overlay_metric(runtime_evidence, node_ids):
    np = require_numpy()
    evidence_ids = [node_id for node_id in node_ids if node_id in runtime_evidence]
    if not evidence_ids:
        return None
    runtime_values = np.array([runtime_evidence[node_id].runtime_sum_seconds for node_id in evidence_ids], dtype=float)
    if np.any(runtime_values > 0.0):
        return 'runtime_sum_seconds', runtime_values
    completed_values = np.array([float(runtime_evidence[node_id].runs_completed) for node_id in evidence_ids], dtype=float)
    if np.any(completed_values > 0.0):
        return 'runs_completed', completed_values
    return None


def make_output_path(db_path: Path, output_path: Path | None) -> Path:
    if output_path is not None:
        return output_path
    return db_path.with_name(f'{db_path.stem}_3d_graph.png')


def plot_graph(nodes, edges, adjacency, positions, runtime_evidence, output_path, label_nodes, show):
    plt = require_matplotlib_pyplot()
    np = require_numpy()
    from matplotlib.lines import Line2D
    figure = plt.figure(figsize=(14, 10))
    axis = figure.add_subplot(111, projection='3d')
    node_ids = sorted(nodes)
    coordinates = np.array([positions[node_id] for node_id in node_ids], dtype=float)
    node_colors = [NODE_TYPE_COLORS.get(nodes[node_id].node_type, NODE_TYPE_COLORS[None]) for node_id in node_ids]
    axis.scatter(coordinates[:, 0], coordinates[:, 1], coordinates[:, 2], c=node_colors,
                 s=node_sizes(adjacency, node_ids), alpha=0.9, edgecolors='black', linewidths=0.4)
    overlay_metric = runtime_overlay_metric(runtime_evidence, node_ids)
    evidence_node_ids = []
    if overlay_metric is not None:
        metric_name, metric_values = overlay_metric
        evidence_node_ids = [node_id for node_id in node_ids if node_id in runtime_evidence]
        evidence_coords = np.array([positions[node_id] for node_id in evidence_node_ids], dtype=float)
        overlay_sizes = np.array([
            110.0 + 20.0 * len(adjacency[node_id]) + 35.0 * math.log1p(max(runtime_evidence[node_id].runs_completed, 0))
            for node_id in evidence_node_ids
        ], dtype=float)
        overlay = axis.scatter(evidence_coords[:, 0], evidence_coords[:, 1], evidence_coords[:, 2], c=metric_values,
                               cmap='YlOrRd', s=overlay_sizes, alpha=0.42, edgecolors='#7a1f00', linewidths=0.6)
        colorbar_label = 'Observed runtime sum (s)' if metric_name == 'runtime_sum_seconds' else 'Observed completed runs'
        figure.colorbar(overlay, ax=axis, pad=0.08, shrink=0.72, label=colorbar_label)
    for edge in edges:
        source = positions[edge.source]
        target = positions[edge.target]
        axis.plot([source[0], target[0]], [source[1], target[1]], [source[2], target[2]],
                  color='#5c677d', alpha=0.35, linewidth=0.8 + min(edge.structural_score, 1.5))
    if label_nodes:
        for node_id, xyz in zip(node_ids, coordinates, strict=True):
            node = nodes[node_id]
            label = node.name if node.name and node.name != node_id else node_id
            evidence = runtime_evidence.get(node_id)
            if evidence is not None:
                if evidence.runtime_sum_seconds > 0.0:
                    label = f'{label}\n{evidence.runtime_sum_seconds:.2f}s/{evidence.runs_completed} runs'
                else:
                    label = f'{label}\n{evidence.runs_completed} runs'
            axis.text(xyz[0], xyz[1], xyz[2], label, fontsize=8)
    axis.set_title('CoreGraphRAG 3D Graph')
    axis.set_xlabel('X')
    axis.set_ylabel('Y')
    axis.set_zlabel('Z')
    legend_handles = []
    present_types = []
    for node in nodes.values():
        if node.node_type not in present_types:
            present_types.append(node.node_type)
    for node_type in sorted(present_types, key=lambda value: (value is None, value)):
        legend_handles.append(
            Line2D([0], [0], marker='o', color='w', markerfacecolor=NODE_TYPE_COLORS.get(node_type, NODE_TYPE_COLORS[None]),
                   markeredgecolor='black', markeredgewidth=0.4, markersize=8,
                   label=NODE_TYPE_LABELS.get(node_type, 'unknown'))
        )
    if legend_handles:
        axis.legend(handles=legend_handles, loc='upper left', bbox_to_anchor=(1.02, 1.0), title='node type')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(output_path, dpi=220, bbox_inches='tight')
    if show:
        plt.show()
    plt.close(figure)


def save_graph_plot(
    db_path: Path,
    output_path: Path | None = None,
    component: str = 'all',
    seed_node: str | None = None,
    drop_isolated: bool = False,
    label_nodes: bool = False,
    show: bool = False,
    runtime_overlay: str = 'auto',
) -> Path:
    resolved_db_path = db_path.expanduser().resolve()
    if not resolved_db_path.exists():
        raise FileNotFoundError(f'Database not found: {resolved_db_path}')

    connection = sqlite3.connect(resolved_db_path)
    try:
        nodes = fetch_nodes(connection)
        if not nodes:
            raise ValueError('No graph nodes were found in graph_node or node_information.')
        edges = fetch_edges(connection, nodes)
        runtime_evidence = fetch_runtime_evidence(connection, nodes, runtime_overlay)
        adjacency = build_adjacency(nodes, edges)
        selected_nodes, selected_edges, components = select_nodes(
            nodes,
            edges,
            adjacency,
            component,
            seed_node,
            drop_isolated,
        )
        if not selected_nodes:
            raise ValueError('No nodes matched the selected component filter')
        selected_adjacency = build_adjacency(selected_nodes, selected_edges)
        positions = compute_positions(selected_nodes, selected_edges, components)
        resolved_output_path = make_output_path(resolved_db_path, output_path)
        plot_graph(
            selected_nodes,
            selected_edges,
            selected_adjacency,
            positions,
            runtime_evidence,
            resolved_output_path,
            label_nodes,
            show,
        )
        return resolved_output_path
    finally:
        connection.close()


def main() -> int:
    args = parse_args()
    output_path = save_graph_plot(
        args.db_path,
        output_path=args.output,
        component=args.component,
        seed_node=args.seed_node,
        drop_isolated=args.drop_isolated,
        label_nodes=args.label_nodes,
        show=args.show,
        runtime_overlay=args.runtime_overlay,
    )
    print(f'Wrote {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())