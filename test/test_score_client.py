import os
import sys
from pathlib import Path
import builtins
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from fabric_experience_gui.services import score_plan_live
from fabric_experience_gui.services.score_client import LiveScorePlanClient


def test_score_plan_live_with_fake_client():
    class FakeNodeExplanation:
        candidate_node_id = 'runner_1'
        skill_name = 'detect'
        selected_key = 'detect'
        estimator_window = 'empirical'
        fallback_level = 'matched'
        reason = 'matched evidence'

    class FakePlan:
        planning_request_id = 'req_1'
        candidate_plan_id = 'plan_1'
        graph_hash = 'graph_1'
        selected = False
        scoring_supported = True
        feasible = True
        sequential_graph = True
        feasibility_reason = 'ok'
        terminal_success_estimate = 0.8
        expected_runtime_seconds = 5.5
        expected_energy_delta_percentage = 0.0
        expected_fault_burden = 0.1
        expected_resource_demand = 0.2
        expected_uncertainty = 0.3
        final_rapfs = 0.72
        score_components = 'runtime=5.5;success=0.8'
        calibration_version = 'c1'
        normalizer_version = 'n1'
        estimator_version = 'e1'
        weight_version = 'w1'
        recorded_at_sec = 1
        recorded_at_nanosec = 2
        node_explanations = [FakeNodeExplanation()]

    class FakeResponse:
        scored = True
        message = 'ok'
        node_found = True
        plan = FakePlan()
        node_explanation = FakeNodeExplanation()

    class FakeClient:
        def request(self, task_description, plan_xml, planning_request_id='', candidate_plan_id='', candidate_node_id=''):
            assert task_description == 'pick object'
            assert '<Plan>' in plan_xml
            assert planning_request_id == 'req_1'
            assert candidate_plan_id == 'plan_1'
            assert candidate_node_id == 'runner_1'
            return FakeResponse()

        def close(self):
            return None

    payload = score_plan_live(
        'pick object',
        '<Plan><Runner name="detect" /></Plan>',
        planning_request_id='req_1',
        candidate_plan_id='plan_1',
        candidate_node_id='runner_1',
        client_factory=lambda: FakeClient(),
    )

    assert payload['scored'] is True
    assert payload['plan']['final_rapfs'] == 0.72
    assert payload['node_explanations'][0]['candidate_node_id'] == 'runner_1'


def test_live_score_client_missing_dependencies(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {'rclpy', 'rclpy.node', 'fabric_msgs.srv'}:
            raise ModuleNotFoundError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', fake_import)

    with pytest.raises(RuntimeError, match='live scoring unavailable'):
        LiveScorePlanClient()


def test_live_score_client_uses_fabric_service(monkeypatch):
    calls = []
    response = object()

    class FakeScorePlan:
        class Request:
            pass

    class FakeNode:
        def __init__(self, name):
            self.name = name

        def create_client(self, service_type, service_name):
            calls.append((service_type, service_name))
            return SimpleNamespace(
                wait_for_service=lambda timeout_sec: True,
                call_async=lambda request: SimpleNamespace(result=lambda: response),
            )

        def destroy_node(self):
            pass

    monkeypatch.setitem(sys.modules, 'rclpy', SimpleNamespace(
        ok=lambda: True,
        spin_until_future_complete=lambda *args, **kwargs: None,
    ))
    monkeypatch.setitem(sys.modules, 'rclpy.node', SimpleNamespace(Node=FakeNode))
    monkeypatch.setitem(sys.modules, 'fabric_msgs.srv', SimpleNamespace(ScorePlan=FakeScorePlan))

    client = LiveScorePlanClient()
    try:
        assert calls == [(FakeScorePlan, '/fabric/experience/score')]
        assert client.request('pick object', '<Plan />') is response
    finally:
        client.close()