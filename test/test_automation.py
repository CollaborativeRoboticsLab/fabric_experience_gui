from pathlib import Path
import json
import sys

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SERVER_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / 'fabric_server'
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(SERVER_PACKAGE_ROOT))

from fabric_experience_gui import automation


def test_run_offline_functional_workflow_orchestrates_exports(monkeypatch, tmp_path: Path):
    db_path = tmp_path / 'core_graphrag.sqlite3'
    db_path.write_text('', encoding='utf-8')
    audit_root = tmp_path / 'planner_prompt_audit'
    audit_root.mkdir()
    feedback_root = tmp_path / 'feedback'
    feedback_root.mkdir()
    out_dir = tmp_path / 'outputs'

    calls = []

    def fake_retrieval(db, out):
        calls.append(('retrieval', db, out))
        return {'summary': {'plan_count': 1}}

    def fake_planner(audit, out):
        calls.append(('planner', audit, out))
        return {'summary': {'request_count': 2}}

    def fake_reasoning(feedback, db, out):
        calls.append(('reasoning', feedback, db, out))
        return {'summary': {'candidate_count': 3}}

    def fake_decision(audit, feedback, db, out):
        calls.append(('decision', audit, feedback, db, out))
        return {'summary': {'request_count': 2}, 'request_prompt_decision_support': []}

    def fake_analysis(feedback, db, out):
        calls.append(('analysis', feedback, db, out))
        return {'summary': {'sample_count': 4, 'best_single_threshold': 0.5}}

    def fake_verify(db, request_id, plan_id, graph_hash, candidate_node_id=''):
        calls.append(('verify', db, request_id, plan_id, graph_hash, candidate_node_id))
        return {'found': True, 'success': True}

    monkeypatch.setattr(automation, 'export_retrieval_prompt_audit', fake_retrieval)
    monkeypatch.setattr(automation, 'export_planner_prompt_audit_summary', fake_planner)
    monkeypatch.setattr(automation, 'export_reasoning_outcomes', fake_reasoning)
    monkeypatch.setattr(automation, 'export_prompt_decision_support', fake_decision)
    monkeypatch.setattr(automation, 'export_terminal_success_analysis', fake_analysis)
    monkeypatch.setattr(automation, 'verify_plan_score_explanation', fake_verify)

    report = automation.run_offline_functional_workflow(
        db_path,
        audit_root,
        feedback_root,
        out_dir,
        planning_request_id='req_1',
        candidate_plan_id='plan_1',
        graph_hash='graph_1',
        candidate_node_id='runner_1',
    )

    assert [call[0] for call in calls] == ['retrieval', 'planner', 'reasoning', 'decision', 'analysis', 'verify']
    assert report['explanation_verification']['success'] is True
    assert report['terminal_success_analysis']['summary']['sample_count'] == 4
    assert json.loads((out_dir / 'explanation_verification.json').read_text(encoding='utf-8'))['success'] is True


def test_run_focused_checks_runs_build_then_ctest(monkeypatch, tmp_path: Path):
    workspace_root = tmp_path / 'ws'
    workspace_root.mkdir()
    calls = []

    def fake_run(command, cwd):
        calls.append((list(command), cwd))
        return {'command': list(command), 'returncode': 0, 'output': ''}

    monkeypatch.setattr(automation, '_run_command', fake_run)

    report = automation.run_focused_checks(workspace_root, extra_colcon_args=['--symlink-install'])

    expected_packages = [
        'fabric_experience_validator',
        'fabric_experience_estimator',
        'fabric_experience_scorer_rapfs',
        'fabric_server',
    ]
    assert calls[0][0] == [
        'colcon', 'build', '--packages-up-to', *expected_packages, '--symlink-install',
    ]
    expected_targets = [
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
    assert [command for command, _ in calls[1:]] == [
        ['ctest', '--output-on-failure', '--test-dir', f'build/{package}', '-R', target]
        for package, target in expected_targets
    ]
    assert len(report['tests']) == len(automation.DEFAULT_CHECK_TARGETS)
    assert report['test_count'] == len(automation.DEFAULT_CHECK_TARGETS)


def test_run_terminal_success_analysis_invokes_export(monkeypatch, tmp_path: Path):
    feedback_root = tmp_path / 'feedback'
    feedback_root.mkdir()
    db_path = tmp_path / 'core_graphrag.sqlite3'
    db_path.write_text('', encoding='utf-8')
    out_dir = tmp_path / 'analysis'

    calls = []

    def fake_export(feedback, db, out):
        calls.append((feedback, db, out))
        return {'summary': {'sample_count': 2, 'best_single_threshold': 0.5}}

    monkeypatch.setattr(automation, 'export_terminal_success_analysis', fake_export)

    report = automation.run_terminal_success_analysis(feedback_root, out_dir, db_path=db_path)

    assert calls == [(feedback_root, db_path, out_dir)]
    assert report['summary']['sample_count'] == 2


def test_parse_terminal_success_analysis_args_normalizes_optional_db(tmp_path: Path):
    feedback_root = tmp_path / 'feedback'
    feedback_root.mkdir()

    args = automation.parse_terminal_success_analysis_args([
        '--feedback-root', str(feedback_root),
        '--out-dir', str(tmp_path / 'analysis'),
    ])

    assert args.feedback_root == feedback_root
    assert args.db_path is None