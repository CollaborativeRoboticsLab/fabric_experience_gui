from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Sequence

from fabric_experience_gui.audits import export_planner_prompt_audit_summary, export_retrieval_prompt_audit
from fabric_server.prompt_decision_support import export_prompt_decision_support
from fabric_server.reasoning_outcomes import export_reasoning_outcomes
from fabric_server.score_explanation_verifier import verify_plan_score_explanation
from fabric_server.terminal_success_analysis import export_terminal_success_analysis


DEFAULT_PACKAGES_UP_TO = [
    'fabric_experience_validator',
    'fabric_experience_estimator',
    'fabric_experience_scorer_rapfs',
    'fabric_server',
]

DEFAULT_CHECK_TARGETS = [
    ('fabric_experience_validator', 'test_validation_plugins'),
    ('fabric_experience_estimator', 'test_estimator_plugins'),
    ('fabric_experience_scorer_rapfs', 'test_rapfs_scorer_plugin'),
    ('fabric_server', 'test_export_retrieval_prompt_audit'),
    ('fabric_server', 'test_export_prompt_decision_support'),
    ('fabric_server', 'test_summarize_planner_prompt_audit'),
    ('fabric_server', 'test_export_reasoning_outcomes'),
    ('fabric_server', 'test_export_terminal_success_analysis'),
    ('fabric_server', 'test_verify_plan_score_explanation'),
]


def _normalize_optional(value: str) -> str:
    return value.strip() if value and value.strip() else ''


def run_offline_functional_workflow(
    db_path: Path,
    audit_root: Path,
    feedback_root: Path,
    out_dir: Path,
    planning_request_id: str = '',
    candidate_plan_id: str = '',
    graph_hash: str = '',
    candidate_node_id: str = '',
) -> Dict[str, Any]:
    planning_request_id = _normalize_optional(planning_request_id)
    candidate_plan_id = _normalize_optional(candidate_plan_id)
    graph_hash = _normalize_optional(graph_hash)
    candidate_node_id = _normalize_optional(candidate_node_id)

    if not db_path.is_file():
        raise FileNotFoundError(f'missing db: {db_path}')
    if not audit_root.is_dir():
        raise FileNotFoundError(f'missing planner prompt audit dir: {audit_root}')
    if not feedback_root.is_dir():
        raise FileNotFoundError(f'missing feedback root: {feedback_root}')
    if any([planning_request_id, candidate_plan_id, graph_hash]) and not all([planning_request_id, candidate_plan_id, graph_hash]):
        raise ValueError('explanation verification requires planning_request_id, candidate_plan_id, and graph_hash together')

    out_dir.mkdir(parents=True, exist_ok=True)
    retrieval = export_retrieval_prompt_audit(db_path, out_dir / 'retrieval_prompt_audit')
    planner = export_planner_prompt_audit_summary(audit_root, out_dir / 'planner_prompt_audit_exports')
    reasoning = export_reasoning_outcomes(feedback_root, db_path, out_dir / 'reasoning_outcomes')
    decision_support = export_prompt_decision_support(audit_root, feedback_root, db_path, out_dir / 'prompt_decision_support')
    terminal_success_analysis = export_terminal_success_analysis(feedback_root, db_path, out_dir / 'terminal_success_analysis')

    explanation_report = None
    if planning_request_id:
        explanation_report = verify_plan_score_explanation(
            db_path,
            planning_request_id,
            candidate_plan_id,
            graph_hash,
            candidate_node_id=candidate_node_id,
        )
        (out_dir / 'explanation_verification.json').write_text(
            json.dumps(explanation_report, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )

    return {
        'retrieval': retrieval,
        'planner_summary': planner,
        'reasoning_outcomes': reasoning,
        'prompt_decision_support': decision_support,
        'terminal_success_analysis': terminal_success_analysis,
        'explanation_verification': explanation_report,
        'output_dir': str(out_dir),
    }


def _run_command(command: Sequence[str], cwd: Path) -> Dict[str, Any]:
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, check=False)
    output = '\n'.join(part for part in [result.stdout.strip(), result.stderr.strip()] if part).strip()
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{output}".strip())
    return {
        'command': list(command),
        'returncode': result.returncode,
        'output': output,
    }


def run_focused_checks(workspace_root: Path, extra_colcon_args: Sequence[str] | None = None) -> Dict[str, Any]:
    if not workspace_root.is_dir():
        raise FileNotFoundError(f'missing workspace root: {workspace_root}')

    extra_colcon_args = list(extra_colcon_args or [])
    build_command = ['colcon', 'build', '--packages-up-to', *DEFAULT_PACKAGES_UP_TO, *extra_colcon_args]
    build_result = _run_command(build_command, workspace_root)

    test_results = []
    for package_name, test_name in DEFAULT_CHECK_TARGETS:
        test_results.append(
            _run_command(
                ['ctest', '--output-on-failure', '--test-dir', f'build/{package_name}', '-R', test_name],
                workspace_root,
            )
        )

    return {
        'build': build_result,
        'tests': test_results,
        'test_count': len(test_results),
    }


def run_terminal_success_analysis(feedback_root: Path, out_dir: Path, db_path: Path | None = None) -> Dict[str, Any]:
    if not feedback_root.is_dir():
        raise FileNotFoundError(f'missing feedback root: {feedback_root}')
    if db_path is not None and not db_path.is_file():
        raise FileNotFoundError(f'missing db: {db_path}')
    return export_terminal_success_analysis(feedback_root, db_path, out_dir)


def parse_offline_workflow_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run the offline Experience workflow over saved artifacts.')
    parser.add_argument('--db-path', required=True, type=Path)
    parser.add_argument('--audit-root', required=True, type=Path)
    parser.add_argument('--feedback-root', required=True, type=Path)
    parser.add_argument('--out-dir', type=Path, default=Path('offline_functional_outputs'))
    parser.add_argument('--planning-request-id', default='')
    parser.add_argument('--candidate-plan-id', default='')
    parser.add_argument('--graph-hash', default='')
    parser.add_argument('--candidate-node-id', default='')
    return parser.parse_args(argv)


def parse_focused_checks_args(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, List[str]]:
    parser = argparse.ArgumentParser(description='Build the focused Experience packages and run the focused check targets.')
    parser.add_argument('--workspace-root', type=Path, default=Path.cwd())
    return parser.parse_known_args(argv)


def parse_terminal_success_analysis_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run offline terminal-success threshold analysis over saved feedback artifacts.')
    parser.add_argument('--feedback-root', required=True, type=Path)
    parser.add_argument('--db-path', default='', help='Optional path to core_graphrag.sqlite3 used to enrich the analysis.')
    parser.add_argument('--out-dir', type=Path, default=Path('terminal_success_analysis'))
    args = parser.parse_args(argv)
    args.db_path = Path(args.db_path) if str(args.db_path).strip() else None
    return args


__all__ = [
    'DEFAULT_CHECK_TARGETS',
    'DEFAULT_PACKAGES_UP_TO',
    'parse_focused_checks_args',
    'parse_offline_workflow_args',
    'parse_terminal_success_analysis_args',
    'run_focused_checks',
    'run_offline_functional_workflow',
    'run_terminal_success_analysis',
]