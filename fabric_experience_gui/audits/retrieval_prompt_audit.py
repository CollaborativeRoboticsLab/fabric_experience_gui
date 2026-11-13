from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


SEMANTIC_COLUMNS = [
    'semantic_relevant_capabilities',
    'semantic_related_entities',
    'semantic_dependencies',
    'semantic_plan_patterns',
    'semantic_fault_concepts',
    'semantic_community_summaries',
]

DETAILED_COLUMNS = [
    'semantic_relevant_capabilities',
    'semantic_related_entities',
    'semantic_dependencies',
    'semantic_plan_patterns',
    'semantic_fault_concepts',
    'semantic_community_summaries',
]

COMMUNITY_COLUMNS = [
    'semantic_relevant_capabilities',
    'semantic_community_summaries',
]


def split_field(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item for item in value.split(',') if item]


def joined_text(row: Dict[str, Any], columns: List[str]) -> str:
    parts: List[str] = []
    for column in columns:
        parts.extend(split_field(row.get(column)))
    return '; '.join(parts)


def load_rows(db_path: Path) -> List[Dict[str, Any]]:
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.execute(
            'SELECT planning_request_id, candidate_plan_id, graph_hash, candidate_node_id, skill_name, skill_id, '
            'requested_context_key, requested_context_class, selected_skill_id, selected_key, estimator_window, '
            'fallback_level, proxy_source, reason, semantic_familiarity, semantic_relevant_capabilities, '
            'semantic_related_entities, semantic_dependencies, semantic_plan_patterns, semantic_fault_concepts, '
            'semantic_community_summaries, estimator_names, estimator_values, estimator_available, estimator_reasons, '
            'recorded_at_sec, recorded_at_nanosec, provenance FROM plan_node_score_explanation;'
        )
    except sqlite3.Error as exc:
        connection.close()
        raise SystemExit(f'failed to read plan_node_score_explanation: {exc}') from exc

    columns = [description[0] for description in cursor.description]
    rows = [dict(zip(columns, record)) for record in cursor.fetchall()]
    connection.close()
    return rows


def build_audit(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    audit_rows: List[Dict[str, Any]] = []
    per_plan: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        detailed_text = joined_text(row, DETAILED_COLUMNS)
        community_text = joined_text(row, COMMUNITY_COLUMNS)
        detailed_chars = len(detailed_text)
        community_chars = len(community_text)
        reduction_chars = detailed_chars - community_chars
        reduction_ratio = (reduction_chars / detailed_chars) if detailed_chars > 0 else 0.0
        community_count = len(split_field(row.get('semantic_community_summaries')))
        detailed_item_count = sum(len(split_field(row.get(column))) for column in DETAILED_COLUMNS)

        plan_key = '|'.join([
            row.get('planning_request_id') or '',
            row.get('candidate_plan_id') or '',
            row.get('graph_hash') or '',
        ])
        plan_summary = per_plan.setdefault(
            plan_key,
            {
                'planning_request_id': row.get('planning_request_id') or '',
                'candidate_plan_id': row.get('candidate_plan_id') or '',
                'graph_hash': row.get('graph_hash') or '',
                'node_count': 0,
                'detailed_chars': 0,
                'community_chars': 0,
                'community_summary_count': 0,
                'detailed_item_count': 0,
            },
        )
        plan_summary['node_count'] += 1
        plan_summary['detailed_chars'] += detailed_chars
        plan_summary['community_chars'] += community_chars
        plan_summary['community_summary_count'] += community_count
        plan_summary['detailed_item_count'] += detailed_item_count

        audit_rows.append(
            {
                'planning_request_id': row.get('planning_request_id') or '',
                'candidate_plan_id': row.get('candidate_plan_id') or '',
                'graph_hash': row.get('graph_hash') or '',
                'candidate_node_id': row.get('candidate_node_id') or '',
                'skill_name': row.get('skill_name') or '',
                'fallback_level': row.get('fallback_level') or '',
                'semantic_familiarity': row.get('semantic_familiarity') or 0.0,
                'detailed_item_count': detailed_item_count,
                'community_summary_count': community_count,
                'detailed_chars': detailed_chars,
                'community_chars': community_chars,
                'prompt_reduction_chars': reduction_chars,
                'prompt_reduction_ratio': reduction_ratio,
                'community_has_signal': community_count > 0,
                'reason': row.get('reason') or '',
            }
        )

    plan_rows: List[Dict[str, Any]] = []
    for summary in per_plan.values():
        detailed_chars = int(summary['detailed_chars'])
        community_chars = int(summary['community_chars'])
        reduction_chars = detailed_chars - community_chars
        summary['prompt_reduction_chars'] = reduction_chars
        summary['prompt_reduction_ratio'] = (reduction_chars / detailed_chars) if detailed_chars > 0 else 0.0
        summary['community_coverage_ratio'] = (
            summary['community_summary_count'] / summary['node_count'] if summary['node_count'] > 0 else 0.0
        )
        plan_rows.append(summary)

    return {
        'summary': {
            'node_explanation_count': len(audit_rows),
            'plan_count': len(plan_rows),
            'nodes_with_community_signal': sum(1 for row in audit_rows if row['community_has_signal']),
        },
        'node_prompt_audit': audit_rows,
        'plan_prompt_audit': plan_rows,
    }


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    columns = list(rows[0].keys())
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def export_retrieval_prompt_audit(db_path: Path, out_dir: Path) -> Dict[str, Any]:
    audit = build_audit(load_rows(db_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'retrieval_prompt_audit.json').write_text(json.dumps(audit, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    write_csv(out_dir / 'node_prompt_audit.csv', audit['node_prompt_audit'])
    write_csv(out_dir / 'plan_prompt_audit.csv', audit['plan_prompt_audit'])
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description='Export semantic retrieval and detailed-vs-community prompt audit tables from CoreGraphRAG evidence.')
    parser.add_argument('db', type=Path, help='Path to core_graphrag.sqlite3')
    parser.add_argument('--out-dir', type=Path, default=Path('retrieval_prompt_audit'))
    args = parser.parse_args()

    if not args.db.is_file():
        raise SystemExit(f'database not found: {args.db}')

    audit = export_retrieval_prompt_audit(args.db, args.out_dir)
    print(f"wrote {args.out_dir} nodes={audit['summary']['node_explanation_count']} plans={audit['summary']['plan_count']}")
    return 0


__all__ = [
    'COMMUNITY_COLUMNS',
    'DETAILED_COLUMNS',
    'SEMANTIC_COLUMNS',
    'build_audit',
    'export_retrieval_prompt_audit',
    'joined_text',
    'load_rows',
    'main',
    'split_field',
    'write_csv',
]


if __name__ == '__main__':
    raise SystemExit(main())