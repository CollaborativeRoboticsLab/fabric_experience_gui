from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from fabric_experience_gui.storage.database import TableSnapshot
from fabric_experience_gui.storage.json_artifacts import load_json


def iter_prompt_audit_files(audit_root: Path) -> Iterable[Path]:
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


def load_prompt_audit_snapshot(audit_root: Path) -> TableSnapshot:
    rows: List[Dict[str, Any]] = []
    for path in iter_prompt_audit_files(audit_root):
        document = load_json(path)
        iterations = document.get('iterations')
        if not isinstance(iterations, dict):
            continue
        for iteration_key, iteration in sorted(iterations.items(), key=iteration_sort_key):
            if not isinstance(iteration, dict):
                continue

            prompt_comparison = iteration.get('prompt_comparison') if isinstance(iteration.get('prompt_comparison'), dict) else {}
            semantic_counts = iteration.get('semantic_counts') if isinstance(iteration.get('semantic_counts'), dict) else {}
            refinement_context = iteration.get('refinement_context') if isinstance(iteration.get('refinement_context'), dict) else {}

            rows.append({
                'source_file': path.name,
                'planning_request_id': document.get('planning_request_id', ''),
                'request_uuid': document.get('request_uuid', ''),
                'iteration_key': iteration_key,
                'phase': iteration.get('phase', ''),
                'selected_semantic_context_mode': iteration.get('selected_semantic_context_mode', ''),
                'detailed_chars': prompt_comparison.get('detailed_chars', 0),
                'community_chars': prompt_comparison.get('community_chars', 0),
                'reduction_chars': prompt_comparison.get('reduction_chars', 0),
                'reduction_ratio': prompt_comparison.get('reduction_ratio', 0.0),
                'community_summaries': semantic_counts.get('community_summaries', 0),
                'relevant_capabilities': semantic_counts.get('relevant_capabilities', 0),
                'attempt_index': refinement_context.get('attempt_index', ''),
                'draft_plan_chars': refinement_context.get('draft_plan_chars', ''),
                'critique_chars': refinement_context.get('critique_chars', ''),
                'semantic_counts': semantic_counts,
                'refinement_context': refinement_context,
            })

    columns = [
        'source_file', 'planning_request_id', 'request_uuid', 'iteration_key', 'phase',
        'selected_semantic_context_mode', 'detailed_chars', 'community_chars', 'reduction_chars',
        'reduction_ratio', 'community_summaries', 'relevant_capabilities', 'attempt_index',
        'draft_plan_chars', 'critique_chars', 'semantic_counts', 'refinement_context',
    ]
    return TableSnapshot(name='Prompt Audits', columns=columns, rows=rows)


__all__ = ['iter_prompt_audit_files', 'iteration_sort_key', 'load_prompt_audit_snapshot']