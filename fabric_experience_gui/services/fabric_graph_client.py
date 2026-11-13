from __future__ import annotations

import math

import yaml

from fabric_experience_gui.fabric_graph import capture_live_snapshot, capture_parsed_plan


class _UniqueSafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in keys
                keys.add(key)
            except TypeError as exc:
                raise ValueError('Runnable specification contains an invalid mapping key.') from exc
            if duplicate:
                raise ValueError(f'Runnable specification contains a duplicate key: {key}.')
        return super().construct_mapping(node, deep=deep)


def parse_runnable_specs(response):
    if len(response.index_of_specs) != len(response.runnable_specs):
        raise ValueError('Runnable specification provider and spec counts do not match.')
    pairs = set()
    providers = set()
    for key, spec in zip(response.index_of_specs, response.runnable_specs):
        try:
            data = yaml.load(spec.spec, Loader=_UniqueSafeLoader)
        except (yaml.YAMLError, ValueError) as exc:
            raise ValueError(f'Invalid runnable specification YAML for {key}: {exc}') from exc
        if not isinstance(data, dict):
            raise ValueError(f'Invalid runnable specification for {key}.')
        interface = data.get('interface')
        provider = data.get('provider')
        if not isinstance(interface, dict) or not isinstance(provider, dict):
            raise ValueError(f'Runnable specification for {key} lacks interface or provider metadata.')
        interface_name = interface.get('name')
        provider_name = provider.get('name')
        if (not isinstance(key, str) or not key.strip() or key != key.strip() or
            not isinstance(interface_name, str) or not interface_name.strip() or
            interface_name != interface_name.strip() or not isinstance(provider_name, str) or provider_name != key):
            raise ValueError(f'Runnable specification for {key} has invalid or inconsistent names.')
        if provider_name in providers:
            raise ValueError(f'Duplicate runnable provider: {provider_name}.')
        providers.add(provider_name)
        pairs.add((interface_name, provider_name))
    return tuple(sorted(pairs))


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
            from capabilities2_msgs.srv import GetRunningCapabilities, GetRunnableSpecs
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
            self._runnable_type = GetRunnableSpecs
            self._snapshot = self._node.create_client(GetFabricPlanSnapshot, '/fabric/plan/get_snapshot')
            self._parse = self._node.create_client(ParsePlan, '/fabric/plan/parse')
            self._running = self._node.create_client(GetRunningCapabilities, '/capabilities/get_running_capabilities')
            self._runnable = self._node.create_client(GetRunnableSpecs, '/capabilities/get_runnable_specs')
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

    def runnable_specs(self):
        response = self._request(self._runnable, self._runnable_type.Request(), '/capabilities/get_runnable_specs')
        return parse_runnable_specs(response)

    def close(self):
        self._executor.shutdown()
        self._node.destroy_node()
        self._rclpy.shutdown(context=self._context)