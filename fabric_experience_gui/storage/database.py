from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence


GRAPH_TABLES = {
    'Nodes': 'SELECT ni.id, ni.name, ni.provider, ni.type, gn.level, gn.cluster_id, gn.feature_vector '
             'FROM node_information ni LEFT JOIN graph_node gn ON gn.id = ni.id ORDER BY ni.name ASC;',
    'Edges': 'SELECT ei.id, ei.source, ei.target, ei.relationship, ei.edge_type, ei.edge_strength_class, '
             'ei.structural_score, ge.source AS projected_source, ge.target AS projected_target '
             'FROM edge_information ei LEFT JOIN graph_edge ge ON ge.id = ei.id ORDER BY ei.relationship ASC, ei.id ASC;',
    'Communities': 'SELECT gc.id, gc.level, gc.node_ids, gc.edge_ids, gc.occurrence, ci.description '
                   'FROM graph_community gc LEFT JOIN community_information ci ON ci.id = gc.id ORDER BY gc.level ASC, gc.id ASC;',
    'Plan Feedback': 'SELECT planning_request_id, candidate_plan_id, graph_hash, selected, feasible, '
                     'terminal_success_estimate, final_rapfs, terminal_outcome, terminal_success, calibration_version, '
                     'normalizer_version, estimator_version, weight_version, recorded_at_sec '
                     'FROM plan_feedback_statistics ORDER BY recorded_at_sec DESC, planning_request_id DESC;',
    'Node Explanations': 'SELECT planning_request_id, candidate_plan_id, graph_hash, candidate_node_id, skill_name, '
                         'fallback_level, semantic_familiarity, semantic_relevant_capabilities, semantic_related_entities, '
                         'semantic_dependencies, semantic_plan_patterns, semantic_fault_concepts, semantic_community_summaries, '
                         'reason, recorded_at_sec '
                         'FROM plan_node_score_explanation ORDER BY recorded_at_sec DESC, candidate_node_id ASC;',
    'Scoring Epochs': 'SELECT epoch_id, strategy_name, calibration_version, normalizer_version, estimator_version, '
                      'weight_version, uncertainty_weight_locked, active, start_sec, end_sec, recorded_at_sec '
                      'FROM scoring_epoch_statistics ORDER BY recorded_at_sec DESC, epoch_id DESC;',
}


@dataclass
class TableSnapshot:
    name: str
    columns: List[str]
    rows: List[Dict[str, Any]]


class InspectorDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def exists(self) -> bool:
        return self.db_path.is_file()

    def load_all(self) -> List[TableSnapshot]:
        snapshots: List[TableSnapshot] = []
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            for name, query in GRAPH_TABLES.items():
                snapshots.append(self._run_query(connection, name, query))
        return snapshots

    def _run_query(self, connection: sqlite3.Connection, name: str, query: str) -> TableSnapshot:
        cursor = connection.execute(query)
        columns = [description[0] for description in cursor.description]
        rows = [self._normalize_row(dict(row)) for row in cursor.fetchall()]
        return TableSnapshot(name=name, columns=columns, rows=rows)

    @staticmethod
    def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in row.items():
            normalized[key] = InspectorDatabase._normalize_value(value)
        return normalized

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if value is None:
            return ''
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return ''
        if text[0] in '[{' and text[-1] in ']}':
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
        return value


def format_cell(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, indent=2, sort_keys=True)
    return str(value)


def row_preview(row: Dict[str, Any], keys: Sequence[str]) -> str:
    parts = []
    for key in keys:
        value = row.get(key)
        if value in ('', None):
            continue
        parts.append(f'{key}={value}')
    return ', '.join(parts)