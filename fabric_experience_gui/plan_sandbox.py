from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from typing import Any, Dict, List
from xml.etree import ElementTree as ET


def parse_optional_json(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    data = json.loads(stripped)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return {}


def score_payload_node_explanations(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(payload.get('node_explanations'), list):
        return [item for item in payload['node_explanations'] if isinstance(item, dict)]
    plan = payload.get('plan')
    if isinstance(plan, dict) and isinstance(plan.get('node_explanations'), list):
        return [item for item in plan['node_explanations'] if isinstance(item, dict)]
    return []


def score_payload_plan_metrics(payload: Dict[str, Any]) -> Dict[str, Any]:
    plan_payload = payload.get('plan') if isinstance(payload.get('plan'), dict) else payload
    metrics = {}
    for key in [
        'feasible',
        'final_rapfs',
        'terminal_success_estimate',
        'expected_runtime_seconds',
        'expected_energy_delta_percentage',
        'expected_fault_burden',
        'expected_resource_demand',
        'expected_uncertainty',
        'score_components',
        'planning_request_id',
        'candidate_plan_id',
        'graph_hash',
    ]:
        if key in plan_payload:
            metrics[key] = plan_payload[key]
    return metrics


def build_plan_sandbox_graph(xml_text: str, score_payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not xml_text.strip():
        raise ValueError('Fabric XML is empty.')

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f'Failed to parse Fabric XML: {exc}') from exc

    if root.tag != 'Plan':
        raise ValueError('Fabric XML must start with a <Plan> root element.')

    score_payload = score_payload or {}
    node_overlays = score_payload_node_explanations(score_payload)
    plan_metrics = score_payload_plan_metrics(score_payload)

    overlay_by_candidate_id = {
        str(item.get('candidate_node_id') or ''): item for item in node_overlays if item.get('candidate_node_id')
    }
    overlay_by_skill_name = {
        str(item.get('skill_name') or ''): item for item in node_overlays if item.get('skill_name')
    }

    counters = defaultdict(int)
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    def next_id(prefix: str) -> str:
        counters[prefix] += 1
        return f'{prefix}_{counters[prefix]}'

    def make_label(element: ET.Element, node_kind: str, node_id: str) -> str:
        if node_kind == 'runner':
            for key in ('name', 'capability', 'id', 'label'):
                value = element.attrib.get(key, '').strip()
                if value:
                    return value
            return node_id
        if node_kind == 'control':
            control_type = element.attrib.get('type', '').strip() or element.attrib.get('kind', '').strip() or 'control'
            return f'control:{control_type}'
        return 'Plan'

    def add_node(element: ET.Element, node_kind: str) -> str:
        node_id = next_id(node_kind)
        label = make_label(element, node_kind, node_id)
        overlay = overlay_by_candidate_id.get(node_id)
        if overlay is None and node_kind == 'runner':
            overlay = overlay_by_skill_name.get(label)
        nodes[node_id] = {
            'id': node_id,
            'kind': node_kind,
            'label': label,
            'tag': element.tag,
            'attributes': dict(element.attrib),
            'score_overlay': overlay or {},
        }
        return node_id

    def add_edge(source: str, target: str, label: str, edge_kind: str) -> None:
        edges.append({
            'id': f'edge_{len(edges) + 1}',
            'source': source,
            'target': target,
            'label': label,
            'kind': edge_kind,
        })

    def walk(element: ET.Element, parent_id: str | None = None) -> str:
        if element.tag == 'Plan':
            node_kind = 'plan'
        elif element.tag == 'Control':
            node_kind = 'control'
        elif element.tag == 'Runner':
            node_kind = 'runner'
        else:
            node_kind = 'runner'

        node_id = add_node(element, node_kind)
        if parent_id is not None:
            add_edge(parent_id, node_id, 'contains', 'contains')

        child_ids = [walk(child, node_id) for child in list(element)]

        if element.tag == 'Control':
            control_type = element.attrib.get('type', '').strip()
            if control_type == 'sequential':
                for left, right in zip(child_ids, child_ids[1:], strict=False):
                    add_edge(left, right, 'success', 'flow')
            elif control_type in ('parallel_all', 'parallel_any'):
                for child_id in child_ids:
                    add_edge(node_id, child_id, control_type, 'branch')
            elif control_type == 'recovery' and child_ids:
                primary = child_ids[0]
                for recovery_child in child_ids[1:]:
                    add_edge(primary, recovery_child, 'failure', 'recovery')
        return node_id

    walk(root)

    summary = {
        'node_count': len(nodes),
        'edge_count': len(edges),
        'runner_count': sum(1 for node in nodes.values() if node['kind'] == 'runner'),
        'control_count': sum(1 for node in nodes.values() if node['kind'] == 'control'),
        'plan_metrics': plan_metrics,
    }
    return {
        'nodes': nodes,
        'edges': edges,
        'summary': summary,
    }


def build_tuning_proposal(
    proposal_kind: str,
    summary: str,
    notes: str,
    *,
    db_path: str,
    audit_root: str,
    selected_graph_node_id: str,
    selected_plan_node_id: str,
    graph_nodes: Dict[str, Dict[str, Any]],
    graph_neighbors: Dict[str, List[Dict[str, Any]]],
    graph_communities: Dict[str, List[str]],
    prompt_audit_row_count: int,
    plan_nodes: Dict[str, Dict[str, Any]],
    plan_edges: List[Dict[str, Any]],
    plan_summary_text: str,
) -> Dict[str, Any]:
    return {
        'schema_version': 1,
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'proposal_kind': proposal_kind,
        'summary': summary,
        'notes': notes,
        'source': {
            'db_path': db_path,
            'audit_root': audit_root,
            'selected_graph_node_id': selected_graph_node_id,
            'selected_plan_node_id': selected_plan_node_id,
        },
        'read_only_policy': {
            'mutates_database': False,
            'expected_follow_up': 'review artifact and apply accepted config or export changes explicitly outside the inspector',
        },
        'graph_snapshot': {
            'node_count': len(graph_nodes),
            'edge_count': sum(len(neighbors) for neighbors in graph_neighbors.values()) // 2 if graph_neighbors else 0,
            'community_membership_count': sum(len(ids) for ids in graph_communities.values()),
        },
        'audit_snapshot': {
            'prompt_audit_rows': prompt_audit_row_count,
        },
        'plan_sandbox_snapshot': {
            'node_count': len(plan_nodes),
            'edge_count': len(plan_edges),
            'summary_text': plan_summary_text,
        },
    }