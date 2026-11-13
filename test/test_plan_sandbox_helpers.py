import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from fabric_experience_gui.plan_sandbox import build_plan_sandbox_graph, build_tuning_proposal, parse_optional_json


def test_parse_optional_json_and_build_plan_graph():
    payload = parse_optional_json(
        '{'
        '"plan": {'
        '  "final_rapfs": 0.72,'
        '  "expected_runtime_seconds": 5.5,'
        '  "node_explanations": ['
        '    {'
        '      "candidate_node_id": "runner_1",'
        '      "skill_name": "detect",'
        '      "reason": "matched evidence"'
        '    }'
        '  ]'
        '}'
        '}'
    )
    sandbox = build_plan_sandbox_graph(
        '<Plan><Control type="sequential"><Runner name="detect" /><Runner name="pick" /></Control></Plan>',
        payload,
    )

    assert sandbox['summary']['node_count'] >= 4
    assert sandbox['summary']['plan_metrics']['final_rapfs'] == 0.72
    assert sandbox['nodes']['runner_1']['score_overlay']['reason'] == 'matched evidence'


def test_build_tuning_proposal_helper():
    proposal = build_tuning_proposal(
        'threshold_recalibration',
        'Review threshold drift',
        'Observed mismatch between offline review and runtime decisions.',
        db_path='/tmp/core_graphrag.sqlite3',
        audit_root='/tmp/planner_prompt_audit',
        selected_graph_node_id='node_1',
        selected_plan_node_id='runner_1',
        graph_nodes={'node_1': {'id': 'node_1'}},
        graph_neighbors={'node_1': []},
        graph_communities={'node_1': ['community_1']},
        prompt_audit_row_count=4,
        plan_nodes={'runner_1': {'id': 'runner_1'}},
        plan_edges=[{'id': 'edge_1'}],
        plan_summary_text='Plan Sandbox',
    )

    assert proposal['proposal_kind'] == 'threshold_recalibration'
    assert proposal['read_only_policy']['mutates_database'] is False
    assert proposal['graph_snapshot']['node_count'] == 1
    assert proposal['audit_snapshot']['prompt_audit_rows'] == 4