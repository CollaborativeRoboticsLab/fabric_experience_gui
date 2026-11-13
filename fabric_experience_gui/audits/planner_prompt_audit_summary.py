from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def iter_audit_files(audit_root: Path) -> Iterable[Path]:
    if not audit_root.exists():
        return []
    return sorted(path for path in audit_root.iterdir() if path.is_file() and path.suffix == '.json')


def iteration_sort_key(item: Tuple[str, Any]) -> Tuple[int, str]:
    key, _ = item
    if key.startswith('iteration_'):
        try:
            return int(key.split('_', 1)[1]), key
        except ValueError:
            pass
    return 10**9, key


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def assess_community_mode_viability(summary: Dict[str, Any], iteration_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not iteration_rows:
        return {
            'status': 'insufficient_data',
            'reason': 'no planner prompt audit iterations available',
            'community_signal_ratio': 0.0,
            'mean_prompt_reduction_ratio': 0.0,
            'community_selected_iteration_count': 0,
        }

    community_signal_ratio = summary['community_signal_iterations'] / max(1, summary['iteration_count'])
    mean_prompt_reduction_ratio = sum(float(row['prompt_reduction_ratio']) for row in iteration_rows) / len(iteration_rows)
    community_selected_iteration_count = sum(1 for row in iteration_rows if row['selected_semantic_context_mode'] == 'community')

    if community_signal_ratio > 0.5 and mean_prompt_reduction_ratio >= 0.20:
        status = 'viable'
        reason = 'community summaries appear often enough and materially reduce prompt size'
    elif community_signal_ratio >= 0.25 and mean_prompt_reduction_ratio >= 0.10:
        status = 'needs_review'
        reason = 'community summaries provide partial signal or only modest prompt reduction'
    else:
        status = 'not_viable_yet'
        reason = 'community summaries are too sparse or save too little prompt budget'

    return {
        'status': status,
        'reason': reason,
        'community_signal_ratio': community_signal_ratio,
        'mean_prompt_reduction_ratio': mean_prompt_reduction_ratio,
        'community_selected_iteration_count': community_selected_iteration_count,
    }


def build_report(audit_documents: List[Dict[str, Any]], high_prompt_chars: int, low_signal_items: int) -> Dict[str, Any]:
    iteration_rows: List[Dict[str, Any]] = []
    request_rows: List[Dict[str, Any]] = []
    low_signal_rows: List[Dict[str, Any]] = []

    refinement_iteration_count = 0
    community_signal_iterations = 0

    for document in audit_documents:
        planning_request_id = str(document.get('planning_request_id') or '')
        request_uuid = str(document.get('request_uuid') or '')
        task_description = str(document.get('task_description') or '')
        iterations = document.get('iterations')
        if not isinstance(iterations, dict):
            continue

        previous_selected_prompt_chars = None
        request_iteration_rows: List[Dict[str, Any]] = []
        for iteration_key, entry in sorted(iterations.items(), key=iteration_sort_key):
            if not isinstance(entry, dict):
                continue

            phase = str(entry.get('phase') or '')
            iteration = to_int(entry.get('iteration'), 0)
            prompt_comparison = entry.get('prompt_comparison') if isinstance(entry.get('prompt_comparison'), dict) else {}
            semantic_counts = entry.get('semantic_counts') if isinstance(entry.get('semantic_counts'), dict) else {}
            refinement_context = entry.get('refinement_context') if isinstance(entry.get('refinement_context'), dict) else {}

            selected_mode = str(entry.get('selected_semantic_context_mode') or 'detailed')
            detailed_chars = to_int(prompt_comparison.get('detailed_chars'), 0)
            community_chars = to_int(prompt_comparison.get('community_chars'), 0)
            selected_prompt_chars = community_chars if selected_mode == 'community' else detailed_chars
            reduction_chars = to_int(prompt_comparison.get('reduction_chars'), detailed_chars - community_chars)
            reduction_ratio = to_float(prompt_comparison.get('reduction_ratio'), 0.0)
            community_summary_count = to_int(semantic_counts.get('community_summaries'), 0)
            semantic_signal_items = sum(to_int(value, 0) for value in semantic_counts.values())
            community_has_signal = community_summary_count > 0
            high_prompt_low_signal = selected_prompt_chars >= high_prompt_chars and semantic_signal_items <= low_signal_items

            refinement_delta = None
            refinement_trend = 'n/a'
            if previous_selected_prompt_chars is not None:
                refinement_delta = selected_prompt_chars - previous_selected_prompt_chars
                if refinement_delta < 0:
                    refinement_trend = 'shrank'
                elif refinement_delta > 0:
                    refinement_trend = 'expanded'
                else:
                    refinement_trend = 'unchanged'

            row = {
                'planning_request_id': planning_request_id,
                'request_uuid': request_uuid,
                'task_description': task_description,
                'iteration_key': iteration_key,
                'iteration': iteration,
                'phase': phase,
                'selected_semantic_context_mode': selected_mode,
                'detailed_chars': detailed_chars,
                'community_chars': community_chars,
                'selected_prompt_chars': selected_prompt_chars,
                'prompt_reduction_chars': reduction_chars,
                'prompt_reduction_ratio': reduction_ratio,
                'semantic_signal_items': semantic_signal_items,
                'community_summary_count': community_summary_count,
                'community_has_signal': community_has_signal,
                'high_prompt_low_signal': high_prompt_low_signal,
                'selected_prompt_delta_from_previous': refinement_delta,
                'selected_prompt_trend': refinement_trend,
                'refinement_attempt_index': to_int(refinement_context.get('attempt_index'), 0),
                'draft_plan_chars': to_int(refinement_context.get('draft_plan_chars'), 0),
                'critique_chars': to_int(refinement_context.get('critique_chars'), 0),
            }
            iteration_rows.append(row)
            request_iteration_rows.append(row)

            if phase == 'refinement':
                refinement_iteration_count += 1
            if community_has_signal:
                community_signal_iterations += 1
            if high_prompt_low_signal:
                low_signal_rows.append(row)

            previous_selected_prompt_chars = selected_prompt_chars

        if not request_iteration_rows:
            continue

        max_selected_chars = max(row['selected_prompt_chars'] for row in request_iteration_rows)
        request_rows.append(
            {
                'planning_request_id': planning_request_id,
                'request_uuid': request_uuid,
                'task_description': task_description,
                'iteration_count': len(request_iteration_rows),
                'refinement_iteration_count': sum(1 for row in request_iteration_rows if row['phase'] == 'refinement'),
                'community_signal_iteration_count': sum(1 for row in request_iteration_rows if row['community_has_signal']),
                'high_prompt_low_signal_iteration_count': sum(1 for row in request_iteration_rows if row['high_prompt_low_signal']),
                'max_selected_prompt_chars': max_selected_chars,
                'final_selected_prompt_trend': request_iteration_rows[-1]['selected_prompt_trend'],
                'final_selected_prompt_delta_from_previous': request_iteration_rows[-1]['selected_prompt_delta_from_previous'],
            }
        )

    summary = {
        'request_count': len(request_rows),
        'iteration_count': len(iteration_rows),
        'refinement_iteration_count': refinement_iteration_count,
        'community_signal_iterations': community_signal_iterations,
        'iterations_without_community_signal': len(iteration_rows) - community_signal_iterations,
        'high_prompt_low_signal_iterations': len(low_signal_rows),
        'high_prompt_chars_threshold': high_prompt_chars,
        'low_signal_items_threshold': low_signal_items,
    }
    summary['community_mode_viability'] = assess_community_mode_viability(summary, iteration_rows)
    return {
        'summary': summary,
        'iteration_prompt_audit': iteration_rows,
        'request_prompt_audit': request_rows,
        'high_prompt_low_signal_requests': low_signal_rows,
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


def export_planner_prompt_audit_summary(
    audit_root: Path,
    out_dir: Path,
    high_prompt_chars: int = 1200,
    low_signal_items: int = 2,
) -> Dict[str, Any]:
    documents = [load_json(path) for path in iter_audit_files(audit_root)]
    report = build_report(documents, high_prompt_chars, low_signal_items)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'planner_prompt_audit_summary.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    write_csv(out_dir / 'iteration_prompt_audit.csv', report['iteration_prompt_audit'])
    write_csv(out_dir / 'request_prompt_audit.csv', report['request_prompt_audit'])
    write_csv(out_dir / 'high_prompt_low_signal_requests.csv', report['high_prompt_low_signal_requests'])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Summarize planner prompt-audit artifacts across generation and refinement iterations.')
    parser.add_argument('audit_root', type=Path, help='Directory containing planner prompt audit JSON files')
    parser.add_argument('--out-dir', type=Path, default=Path('planner_prompt_audit_exports'))
    parser.add_argument('--high-prompt-chars', type=int, default=1200)
    parser.add_argument('--low-signal-items', type=int, default=2)
    args = parser.parse_args()

    report = export_planner_prompt_audit_summary(args.audit_root, args.out_dir, high_prompt_chars=args.high_prompt_chars, low_signal_items=args.low_signal_items)
    print(
        f"wrote {args.out_dir} requests={report['summary']['request_count']} "
        f"iterations={report['summary']['iteration_count']} "
        f"high_prompt_low_signal={report['summary']['high_prompt_low_signal_iterations']}"
    )
    return 0


__all__ = [
    'assess_community_mode_viability',
    'build_report',
    'export_planner_prompt_audit_summary',
    'iter_audit_files',
    'iteration_sort_key',
    'load_json',
    'main',
    'to_float',
    'to_int',
    'write_csv',
]


if __name__ == '__main__':
    raise SystemExit(main())