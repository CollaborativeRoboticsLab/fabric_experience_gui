from __future__ import annotations

import math

from fabric_experience_gui.fabric_graph import capture_live_snapshot, capture_parsed_plan


class FabricGraphClient:
    def __init__(self, timeout_sec: float = 5.0):
        if not math.isfinite(timeout_sec) or timeout_sec <= 0:
            raise ValueError('timeout_sec must be finite and positive')
        try:
            import rclpy
            from rclpy.context import Context
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.node import Node
            from fabric_msgs.srv import GetFabricPlanSnapshot, ParsePlan
            from capabilities2_msgs.srv import GetRunningCapabilities
        except ImportError as exc:
            raise RuntimeError('Fabric graph unavailable: missing ROS dependencies') from exc

        self._rclpy = rclpy
        self._timeout_sec = timeout_sec
        self._context = Context()
        rclpy.init(context=self._context)
        try:
            self._node = Node('fabric_inspector_graph_client', context=self._context)
            self._executor = SingleThreadedExecutor(context=self._context)
            self._executor.add_node(self._node)
            self._snapshot_type = GetFabricPlanSnapshot
            self._parse_type = ParsePlan
            self._running_type = GetRunningCapabilities
            self._snapshot = self._node.create_client(GetFabricPlanSnapshot, '/fabric/plan/get_snapshot')
            self._parse = self._node.create_client(ParsePlan, '/fabric/plan/parse')
            self._running = self._node.create_client(GetRunningCapabilities, '/capabilities/get_running_capabilities')
        except Exception:
            if hasattr(self, '_executor'):
                self._executor.shutdown()
            if hasattr(self, '_node'):
                self._node.destroy_node()
            rclpy.shutdown(context=self._context)
            raise

    def _request(self, client, request, name):
        if not client.wait_for_service(timeout_sec=self._timeout_sec):
            raise RuntimeError(f'service {name} not available')
        future = client.call_async(request)
        try:
            self._executor.spin_until_future_complete(future, timeout_sec=self._timeout_sec)
        except Exception:
            client.remove_pending_request(future)
            future.cancel()
            raise
        if not future.done():
            client.remove_pending_request(future)
            future.cancel()
            raise TimeoutError(f'service {name} timed out')
        response = future.result()
        if response is None:
            raise RuntimeError(f'service {name} returned no response')
        return response

    def snapshot(self, include_dependencies: bool = False):
        response = self._request(self._snapshot, self._snapshot_type.Request(), '/fabric/plan/get_snapshot')
        running = None
        if include_dependencies and response.has_plan:
            try:
                result = self._request(
                    self._running, self._running_type.Request(), '/capabilities/get_running_capabilities'
                )
                running = result.running_capabilities
            except (RuntimeError, TimeoutError):
                pass
        return capture_live_snapshot(response, running_capabilities=running)

    def parse(self, plan_xml: str):
        request = self._parse_type.Request()
        request.plan = plan_xml
        response = self._request(self._parse, request, '/fabric/plan/parse')
        return capture_parsed_plan(response)

    def close(self):
        self._executor.shutdown()
        self._node.destroy_node()
        self._rclpy.shutdown(context=self._context)