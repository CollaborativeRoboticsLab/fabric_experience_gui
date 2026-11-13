from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

from fabric_experience_gui.storage.json_artifacts import load_json


def iter_generated_plan_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob('generated_plans.json') if path.is_file())


def load_generated_plan_index(root: Path) -> Dict[str, List[Dict[str, Any]]]:
    by_request: Dict[str, List[Dict[str, Any]]] = {}
    for path in iter_generated_plan_files(root):
        document = load_json(path)
        for iteration_key, iteration in sorted(document.items()):
            if not iteration_key.startswith('iteration_') or not isinstance(iteration, dict):
                continue
            selected_candidate_plan_id = str(iteration.get('selected_candidate_plan_id') or '')
            for plan_key, plan in sorted(iteration.items()):
                if not plan_key.startswith('plan_') or not isinstance(plan, dict):
                    continue
                planning_request_id = str(plan.get('planning_request_id') or '')
                if not planning_request_id:
                    continue
                candidate_plan_id = str(plan.get('candidate_plan_id') or '')
                record = {
                    'planning_request_id': planning_request_id,
                    'candidate_plan_id': candidate_plan_id,
                    'graph_hash': str(plan.get('graph_hash') or ''),
                    'iteration_key': iteration_key,
                    'plan_key': plan_key,
                    'selected': bool(plan.get('selected')) or candidate_plan_id == selected_candidate_plan_id,
                    'feasible': bool(plan.get('feasible')),
                    'final_rapfs': plan.get('final_rapfs', ''),
                    'terminal_success_estimate': plan.get('terminal_success_estimate', ''),
                    'reasoning': str(plan.get('reasoning') or ''),
                    'plan_xml': str(plan.get('plan') or ''),
                    'source_file': str(path),
                }
                by_request.setdefault(planning_request_id, []).append(record)

    for request_id, records in by_request.items():
        records.sort(
            key=lambda record: (
                not bool(record.get('selected')),
                str(record.get('iteration_key') or ''),
                str(record.get('plan_key') or ''),
            )
        )
    return by_request


__all__ = ['iter_generated_plan_files', 'load_generated_plan_index']