from __future__ import annotations

from typing import Any, Dict, List


class LiveScorePlanClient:
	def __init__(self, timeout_sec: float = 5.0):
		try:
			import rclpy
			from rclpy.node import Node
			from fabric_msgs.srv import ScorePlan
		except (ImportError, ModuleNotFoundError) as exc:
			raise RuntimeError(
				'live scoring unavailable: missing ROS score client dependencies (rclpy and fabric_msgs)'
			) from exc

		self._rclpy = rclpy
		self._timeout_sec = timeout_sec
		if not self._rclpy.ok():
			self._rclpy.init()

		class _ScoreNode(Node):
			def __init__(self):
				super().__init__('fabric_experience_gui_score_client')

		self._node = _ScoreNode()
		self._ScorePlan = ScorePlan
		self._client = self._node.create_client(ScorePlan, '/fabric/experience/score')

	def request(
		self,
		task_description: str,
		plan_xml: str,
		planning_request_id: str = '',
		candidate_plan_id: str = '',
		candidate_node_id: str = '',
	):
		if not self._client.wait_for_service(timeout_sec=self._timeout_sec):
			raise RuntimeError('service /fabric/experience/score not available')
		request = self._ScorePlan.Request()
		request.task_description = task_description
		request.plan_xml = plan_xml
		request.planning_request_id = planning_request_id
		request.candidate_plan_id = candidate_plan_id
		request.candidate_node_id = candidate_node_id
		future = self._client.call_async(request)
		self._rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout_sec)
		response = future.result()
		if response is None:
			raise RuntimeError('score service call failed')
		return response

	def close(self) -> None:
		self._node.destroy_node()


def _serialize_ros_message(message: Any, fields: List[str]) -> Dict[str, Any]:
	data: Dict[str, Any] = {}
	for field in fields:
		data[field] = getattr(message, field)
	return data


def score_response_to_payload(response: Any) -> Dict[str, Any]:
	plan = response.plan
	plan_payload = _serialize_ros_message(
		plan,
		[
			'planning_request_id',
			'candidate_plan_id',
			'graph_hash',
			'selected',
			'scoring_supported',
			'feasible',
			'sequential_graph',
			'feasibility_reason',
			'terminal_success_estimate',
			'expected_runtime_seconds',
			'expected_energy_delta_percentage',
			'expected_fault_burden',
			'expected_resource_demand',
			'expected_uncertainty',
			'final_rapfs',
			'score_components',
			'calibration_version',
			'normalizer_version',
			'estimator_version',
			'weight_version',
			'recorded_at_sec',
			'recorded_at_nanosec',
		],
	)
	node_explanations = []
	for node in getattr(plan, 'node_explanations', []):
		node_explanations.append(
			_serialize_ros_message(
				node,
				[
					'candidate_node_id',
					'skill_name',
					'selected_key',
					'estimator_window',
					'fallback_level',
					'reason',
				],
			)
		)
	plan_payload['node_explanations'] = node_explanations
	payload = {
		'scored': bool(getattr(response, 'scored', False)),
		'message': getattr(response, 'message', ''),
		'node_found': bool(getattr(response, 'node_found', False)),
		'plan': plan_payload,
		'node_explanations': node_explanations,
	}
	node_explanation = getattr(response, 'node_explanation', None)
	if node_explanation is not None:
		payload['node_explanation'] = _serialize_ros_message(
			node_explanation,
			[
				'candidate_node_id',
				'skill_name',
				'selected_key',
				'estimator_window',
				'fallback_level',
				'reason',
			],
		)
	return payload


def score_plan_live(
	task_description: str,
	plan_xml: str,
	planning_request_id: str = '',
	candidate_plan_id: str = '',
	candidate_node_id: str = '',
	timeout_sec: float = 5.0,
	client_factory=None,
) -> Dict[str, Any]:
	factory = client_factory or (lambda: LiveScorePlanClient(timeout_sec=timeout_sec))
	client = factory()
	try:
		response = client.request(
			task_description,
			plan_xml,
			planning_request_id=planning_request_id,
			candidate_plan_id=candidate_plan_id,
			candidate_node_id=candidate_node_id,
		)
		return score_response_to_payload(response)
	finally:
		close = getattr(client, 'close', None)
		if callable(close):
			close()


__all__ = ['LiveScorePlanClient', 'score_plan_live', 'score_response_to_payload']