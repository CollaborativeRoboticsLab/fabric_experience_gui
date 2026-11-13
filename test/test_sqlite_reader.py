import sqlite3
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from fabric_experience_gui.storage import InspectorDatabase, load_prompt_audit_snapshot


def create_minimal_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        '''
        CREATE TABLE node_information (id TEXT PRIMARY KEY, name TEXT, provider TEXT, descriptions TEXT, type INTEGER);
        CREATE TABLE graph_node (id TEXT PRIMARY KEY, level INTEGER, cluster_id INTEGER, feature_vector TEXT DEFAULT '');
        CREATE TABLE edge_information (
            id TEXT PRIMARY KEY, source TEXT, target TEXT, relationship TEXT, edge_type TEXT DEFAULT '',
            edge_strength_class TEXT DEFAULT '', structural_score REAL DEFAULT 0.0,
            matched_runtime_inputs INTEGER DEFAULT 0, total_runtime_inputs INTEGER DEFAULT 0,
            matched_parameter_keys TEXT DEFAULT ''
        );
        CREATE TABLE graph_edge (id TEXT PRIMARY KEY, source TEXT, target TEXT);
        CREATE TABLE community_information (id TEXT PRIMARY KEY, description TEXT);
        CREATE TABLE graph_community (id TEXT PRIMARY KEY, level INTEGER, node_ids TEXT, edge_ids TEXT, occurrence REAL);
        CREATE TABLE plan_feedback_statistics (
            planning_request_id TEXT, candidate_plan_id TEXT, graph_hash TEXT, selected INTEGER,
            scoring_supported INTEGER DEFAULT 0, feasible INTEGER DEFAULT 0, sequential_graph INTEGER DEFAULT 0,
            feasibility_reason TEXT DEFAULT '', terminal_success_estimate REAL DEFAULT 0.0,
            expected_runtime_seconds REAL DEFAULT 0.0, expected_energy_delta_percentage REAL DEFAULT 0.0,
            expected_fault_burden REAL DEFAULT 0.0, expected_resource_demand REAL DEFAULT 0.0,
            expected_uncertainty REAL DEFAULT 0.0, final_rapfs REAL DEFAULT 0.0, terminal_outcome TEXT,
            terminal_success INTEGER, runtime_seconds REAL, energy_delta_percentage REAL, warning_count INTEGER,
            error_count INTEGER, human_judgement TEXT, score_components TEXT, calibration_version TEXT DEFAULT '',
            normalizer_version TEXT, estimator_version TEXT, weight_version TEXT, recorded_at_sec INTEGER,
            recorded_at_nanosec INTEGER, provenance TEXT
        );
        CREATE TABLE plan_node_score_explanation (
            planning_request_id TEXT, candidate_plan_id TEXT, graph_hash TEXT, candidate_node_id TEXT,
            skill_name TEXT, skill_id TEXT, requested_context_key TEXT, requested_context_class TEXT,
            selected_skill_id TEXT, selected_key TEXT, estimator_window TEXT, fallback_level TEXT,
            proxy_source TEXT, reason TEXT, semantic_familiarity REAL DEFAULT 0.0,
            semantic_relevant_capabilities TEXT DEFAULT '', semantic_related_entities TEXT DEFAULT '',
            semantic_dependencies TEXT DEFAULT '', semantic_plan_patterns TEXT DEFAULT '',
            semantic_fault_concepts TEXT DEFAULT '', semantic_community_summaries TEXT DEFAULT '',
            estimator_names TEXT DEFAULT '', estimator_values TEXT DEFAULT '', estimator_available TEXT DEFAULT '',
            estimator_reasons TEXT DEFAULT '', recorded_at_sec INTEGER, recorded_at_nanosec INTEGER,
            provenance TEXT
        );
        CREATE TABLE scoring_epoch_statistics (
            epoch_id TEXT PRIMARY KEY, strategy_name TEXT, calibration_version TEXT,
            normalizer_version TEXT, estimator_version TEXT, weight_version TEXT,
            uncertainty_weight_locked INTEGER DEFAULT 1, calibration_summary TEXT,
            selection_bias_summary TEXT, active INTEGER DEFAULT 0, start_sec INTEGER, start_nanosec INTEGER,
            end_sec INTEGER, end_nanosec INTEGER, recorded_at_sec INTEGER, recorded_at_nanosec INTEGER,
            provenance TEXT
        );
        '''
    )
    connection.execute(
        "INSERT INTO node_information VALUES (?, ?, ?, ?, ?)",
        ('node_1', 'DetectObject', 'demo', 'detect object', 1),
    )
    connection.execute(
        "INSERT INTO graph_node VALUES (?, ?, ?, ?)",
        ('node_1', 0, 3, '[0.1, 0.2]'),
    )
    connection.execute(
        "INSERT INTO edge_information VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ('edge_1', 'node_1', 'node_2', 'depends_on', 'parameter', 'strong', 0.8, 1, 1, 'object_pose'),
    )
    connection.execute(
        "INSERT INTO graph_edge VALUES (?, ?, ?)",
        ('edge_1', 'node_1', 'node_2'),
    )
    connection.execute(
        "INSERT INTO community_information VALUES (?, ?)",
        ('community_1', 'vision community'),
    )
    connection.execute(
        "INSERT INTO graph_community VALUES (?, ?, ?, ?, ?)",
        ('community_1', 1, '["node_1"]', '["edge_1"]', 0.9),
    )
    connection.execute(
        "INSERT INTO plan_feedback_statistics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ('req_1', 'plan_1', 'graph_1', 1, 1, 1, 1, 'ok', 0.9, 5.0, 0.0, 0.0, 0.0, 0.1, 0.7, 'success', 1, 5.2, 0.0, 0, 0, '', '{}', 'v1', 'n1', 'e1', 'w1', 10, 20, 'test'),
    )
    connection.execute(
        "INSERT INTO plan_node_score_explanation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ('req_1', 'plan_1', 'graph_1', 'runner_1', 'demo/DetectObject', 'detect', 'task:pick', 'task:pick', 'detect', 'task:pick', 'empirical', 'context_key', 'requested_skill', 'matched', 0.6, 'detect,estimate', 'apple,table', 'camera_ready', 'detect_then_pick', 'occlusion', 'vision summary', 'success_probability', '0.9', '1', 'posterior', 10, 20, 'test'),
    )
    connection.execute(
        "INSERT INTO scoring_epoch_statistics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ('epoch_1', 'analysis', 'c1', 'n1', 'e1', 'w1', 1, 'cal summary', 'bias summary', 1, 1, 0, 2, 0, 3, 0, 'test'),
    )
    connection.commit()
    connection.close()


def test_load_all_snapshots(tmp_path: Path):
    db_path = tmp_path / 'core_graphrag.sqlite3'
    create_minimal_db(db_path)

    snapshots = InspectorDatabase(db_path).load_all()

    names = [snapshot.name for snapshot in snapshots]
    assert 'Nodes' in names
    assert 'Edges' in names
    assert 'Communities' in names
    assert 'Plan Feedback' in names
    assert 'Node Explanations' in names
    assert 'Scoring Epochs' in names

    nodes = next(snapshot for snapshot in snapshots if snapshot.name == 'Nodes')
    assert nodes.rows[0]['name'] == 'DetectObject'

    communities = next(snapshot for snapshot in snapshots if snapshot.name == 'Communities')
    assert communities.rows[0]['description'] == 'vision community'
    assert communities.rows[0]['node_ids'] == ['node_1']

    explanations = next(snapshot for snapshot in snapshots if snapshot.name == 'Node Explanations')
    assert explanations.rows[0]['semantic_community_summaries'] == 'vision summary'


def test_load_prompt_audit_snapshot(tmp_path: Path):
    audit_root = tmp_path / 'planner_prompt_audit'
    audit_root.mkdir()
    (audit_root / 'req_1_10_20.json').write_text(
        '{\n'
        '  "planning_request_id": "req_1",\n'
        '  "request_uuid": "uuid_1",\n'
        '  "iterations": {\n'
        '    "iteration_1": {\n'
        '      "phase": "generation",\n'
        '      "selected_semantic_context_mode": "detailed",\n'
        '      "prompt_comparison": {\n'
        '        "detailed_chars": 1500,\n'
        '        "community_chars": 900,\n'
        '        "reduction_chars": 600,\n'
        '        "reduction_ratio": 0.4\n'
        '      },\n'
        '      "semantic_counts": {\n'
        '        "community_summaries": 1,\n'
        '        "relevant_capabilities": 2\n'
        '      }\n'
        '    },\n'
        '    "iteration_2": {\n'
        '      "phase": "refinement",\n'
        '      "selected_semantic_context_mode": "community",\n'
        '      "prompt_comparison": {\n'
        '        "detailed_chars": 1600,\n'
        '        "community_chars": 1000,\n'
        '        "reduction_chars": 600,\n'
        '        "reduction_ratio": 0.375\n'
        '      },\n'
        '      "semantic_counts": {\n'
        '        "community_summaries": 2,\n'
        '        "relevant_capabilities": 2\n'
        '      },\n'
        '      "refinement_context": {\n'
        '        "attempt_index": 0,\n'
        '        "draft_plan_chars": 320,\n'
        '        "critique_chars": 120\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )

    snapshot = load_prompt_audit_snapshot(audit_root)

    assert snapshot.name == 'Prompt Audits'
    assert len(snapshot.rows) == 2
    assert snapshot.rows[0]['phase'] == 'generation'
    assert snapshot.rows[1]['phase'] == 'refinement'
    assert snapshot.rows[1]['draft_plan_chars'] == 320