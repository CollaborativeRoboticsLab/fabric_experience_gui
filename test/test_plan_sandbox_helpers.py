import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from fabric_experience_gui.plan_sandbox import build_plan_sandbox_graph, build_tuning_proposal, parse_optional_json
from fabric_experience_gui.draft_model import DraftModel
from fabric_experience_gui.services.fabric_graph_client import parse_runnable_specs


def test_runnable_spec_pair_discovery_checks_name_consistency_only():
    from types import SimpleNamespace
    import pytest

    def response(keys, specs):
        return SimpleNamespace(index_of_specs=keys, runnable_specs=[SimpleNamespace(spec=spec) for spec in specs])

    names_only = 'interface:\n  name: demo/Interface\nprovider:\n  name: demo/Provider\n'
    other_interface = 'interface: {name: demo/Other}\nprovider: {name: demo/Provider}\n'
    key = 'demo/Interface|demo/Provider'
    assert parse_runnable_specs(response([key], [names_only])) == (('demo/Interface', 'demo/Provider'),)
    assert parse_runnable_specs(response([key, 'demo/Other|demo/Provider'], [names_only, other_interface])) == (
        ('demo/Interface', 'demo/Provider'), ('demo/Other', 'demo/Provider'))
    for payload in (response([], [names_only]), response(['other'], [names_only]),
                    response(['demo/Provider'], [names_only]),
                    response(['demo/Other|demo/Provider'], [names_only]),
                    response([key], ['interface: [']),
                    response([key], [names_only + 'provider: {name: demo/Provider}\n']),
                    response([' '], ['interface: {name: demo/Interface}\nprovider: {name: " "}\n']),
                    response([key, key], [names_only, names_only]),
                    response([key], ['provider: {name: demo/Provider}'])):
        with pytest.raises(ValueError):
            parse_runnable_specs(payload)


def test_draft_model_preserves_structure_and_runner_parameters():
    xml = ('<?xml version="1.0"?><Plan name="example"><!--keep-->'
            '<Control type="sequential"><Runner interface="demo/A" provider="demo/AProvider" extra="1 &amp; 2">'
            '<!--runner comment--></Runner>'
           '<Control type="recovery"><Runner interface="demo/B" provider="demo/BProvider"/>'
           '</Control></Control></Plan>')
    draft = DraftModel(xml)
    assert draft.to_xml() == xml
    assert draft.root.children[0].children[1].children[0].path == (0, 1, 0)
    draft.set_runner_pair((0, 0), 'demo/C', 'demo/CProvider', {('demo/C', 'demo/CProvider')})
    output = draft.to_xml()
    assert '<!--keep-->' in output
    assert '<!--runner comment-->' in output
    restored = DraftModel(output)
    assert dict(restored.root.children[0].children[0].attributes) == {
        'interface': 'demo/C', 'provider': 'demo/CProvider', 'extra': '1 & 2'}


def test_draft_model_rejects_unsupported_or_unverified_edits():
    import pytest

    for xml in ('<Plan><Unknown/></Plan>', '<Plan><Control type="unknown"><Runner/></Control></Plan>',
                '<Plan><Runner interface="a"/></Plan>', '<!DOCTYPE Plan><Plan><Runner interface="a" provider="b"/></Plan>',
                '<Plan><Control type="sequential"/></Plan>',
                '<Plan><Runner interface="a" provider="b"><Parameters/></Runner></Plan>'):
        with pytest.raises(ValueError):
            DraftModel(xml)
    xml = '<Plan><Runner interface="a" provider="b"/></Plan>'
    draft = DraftModel(xml)
    with pytest.raises(ValueError, match='verified runnable pair'):
        draft.set_runner_pair((0,), 'a', 'other', {('a', 'b')})
    with pytest.raises(ValueError, match='path does not exist'):
        draft.set_runner_pair((0, 0), 'a', 'b', {('a', 'b')})
    with pytest.raises(ValueError, match='not a Runner'):
        draft.set_runner_pair((), 'a', 'b', {('a', 'b')})
    assert draft.to_xml() == xml


def test_draft_model_round_trips_supported_controls_and_parameters():
    for control_type in ('sequential', 'parallel_any', 'parallel_all', 'recovery'):
        xml = (f'<Plan><Control type="{control_type}" name="example">'
               '<Runner interface="demo/Old" provider="demo/OldProvider" x="0.5" enabled="true"/>'
               '</Control></Plan>')
        draft = DraftModel(xml)
        draft.set_runner_pair((0, 0), 'demo/New', 'demo/NewProvider', {('demo/New', 'demo/NewProvider')})
        restored = DraftModel(draft.to_xml())
        assert dict(restored.root.children[0].attributes) == {'type': control_type, 'name': 'example'}
        assert dict(restored.root.children[0].children[0].attributes) == {
            'interface': 'demo/New', 'provider': 'demo/NewProvider', 'x': '0.5', 'enabled': 'true'}


def test_draft_model_preserves_attribute_whitespace():
    xml = ('<?xml version="1.1" standalone="yes"?>'
           '<Plan><Runner interface="a" provider="b" value="one&#10;two&#9;three&#13;four"/></Plan>')
    draft = DraftModel(xml)
    original = dict(draft.root.children[0].attributes)['value']
    draft.set_runner_pair((0,), 'c', 'd', {('c', 'd')})
    restored = DraftModel(draft.to_xml())
    assert dict(restored.root.children[0].attributes)['value'] == original
    assert draft.to_xml().startswith('<?xml version="1.1" standalone="yes"?>')


def test_draft_round_trip_with_fabric_xml_parser():
    import subprocess
    import pytest

    probe = os.environ.get('FABRIC_GUI_PARSER_PROBE')
    if not probe:
        pytest.skip('Fabric XML parser probe is not enabled')

    def parse(xml):
        result = subprocess.run([probe], input=xml, text=True, capture_output=True, timeout=15, check=True)
        nodes = {}
        parameters = {}
        edges = []

        def decode(value):
            return bytes.fromhex(value).decode('utf-8') if value != '-' else ''

        for line in result.stdout.splitlines():
            parts = line.split()
            if parts[:2] == ['PROBE', 'N']:
                nodes[int(parts[2])] = (decode(parts[3]), decode(parts[4]), int(parts[5]))
            elif parts[:2] == ['PROBE', 'P']:
                parameters[(int(parts[2]), decode(parts[3]))] = (int(parts[4]), tuple(map(decode, parts[5:])))
            elif parts[:2] == ['PROBE', 'E']:
                edges.append((int(parts[2]), parts[3], decode(parts[4]), decode(parts[5]), int(parts[6])))
        return nodes, parameters, edges

    real_plan_xml = (Path(__file__).parent / 'fixtures' / 'fabric_server_default.xml').read_text(encoding='utf-8')
    real_plan = DraftModel(real_plan_xml)
    real_nodes, real_parameters, real_edges = parse(real_plan_xml)
    assert len(real_nodes) == 7
    assert sum(identity[:2] == ('fabric_capabilities/FabricCompletionRunner',
                                'fabric_capabilities/FabricCompletionRunner')
               for identity in real_nodes.values()) == 1
    assert real_edges
    pose_runner_id = next(node_id for node_id, identity in real_nodes.items()
                          if identity[:2] == ('nav2_capabilities/RobotPoseRunner',
                                              'nav2_capabilities/RobotPoseRunner'))
    map_parameter = real_parameters[(pose_runner_id, 'map')]
    real_plan.set_runner_parameter((0, 2), 'map', 'world')
    edited_nodes, edited_parameters, edited_edges = parse(real_plan.to_xml())
    assert edited_nodes == real_nodes and edited_edges == real_edges
    expected_parameters = dict(real_parameters)
    expected_parameters[(pose_runner_id, 'map')] = (map_parameter[0], ('world',))
    assert edited_parameters == expected_parameters

    xml = ('<Plan><Control type="sequential" name="main">'
           '<Runner interface="demo/I" provider="demo/P" speed="0.5" whole="1" decimal="1.0" '
           'enabled="true" label="one &amp; two&#10;three"/>'
           '<Control type="parallel_any"><Runner interface="demo/I" provider="demo/P" speed="1"/>'
           '<Control type="parallel_all"><Runner interface="demo/J" provider="demo/Q" enabled="true"/>'
           '<Runner interface="demo/K" provider="demo/T"/></Control></Control>'
           '<Control type="recovery"><Runner interface="demo/R" provider="demo/S"/></Control>'
           '</Control></Plan>')
    draft = DraftModel(xml)
    draft.set_runner_parameter((0, 0), 'temporary', 'value')
    draft.remove_runner_parameter((0, 0), 'temporary')
    original_nodes, original_parameters, original_edges = parse(xml)
    assert original_nodes
    assert parse(draft.to_xml()) == (original_nodes, original_parameters, original_edges)
    repeated = [(node_id, identity) for node_id, identity in original_nodes.items()
                if identity[:2] == ('demo/I', 'demo/P')]
    assert len(repeated) == 2 and repeated[0][1][2] != repeated[1][1][2]
    first_node = repeated[0][0]
    assert original_parameters[(first_node, 'speed')] == (1, ('0.500000',))
    assert original_parameters[(first_node, 'whole')] == (2, ('1',))
    assert original_parameters[(first_node, 'decimal')] == (1, ('1.000000',))
    assert original_parameters[(first_node, 'enabled')] == (0, ('true',))
    assert original_parameters[(first_node, 'label')] == (3, ('one & two\nthree',))
    assert {'start', 'success', 'failure'} <= {edge[1] for edge in original_edges}

    draft.set_runner_parameter((0, 0), 'speed', '1.25')
    edited_nodes, edited_parameters, edited_edges = parse(draft.to_xml())
    assert edited_nodes == original_nodes and edited_edges == original_edges
    assert edited_parameters.pop((first_node, 'speed')) == (1, ('1.250000',))
    original_parameters.pop((first_node, 'speed'))
    assert edited_parameters == original_parameters

    draft.set_runner_pair((0, 0), 'demo/New', 'demo/NewProvider', {('demo/New', 'demo/NewProvider')})
    renamed_nodes, renamed_parameters, renamed_edges = parse(draft.to_xml())
    assert renamed_nodes[first_node] == ('demo/New', 'demo/NewProvider', edited_nodes[first_node][2])
    assert {key: value for key, value in renamed_nodes.items() if key != first_node} == {
        key: value for key, value in edited_nodes.items() if key != first_node}
    expected_parameters = dict(edited_parameters)
    expected_parameters[(first_node, 'speed')] = (1, ('1.250000',))
    assert renamed_parameters == expected_parameters
    original_identity = edited_nodes[first_node]
    renamed_identity = renamed_nodes[first_node]
    expected_edges = [(source, event, *(renamed_identity if (interface, provider, instance) == original_identity
                                       else (interface, provider, instance)))
                      for source, event, interface, provider, instance in edited_edges]
    assert renamed_edges == expected_edges

    nested_content = ('<Plan><Runner interface="demo/I" provider="demo/P">'
                      '<Parameters x="ignored"/></Runner></Plan>')
    nested_nodes, nested_parameters, _ = parse(nested_content)
    nested_runner = next(node_id for node_id, identity in nested_nodes.items() if identity[0] == 'demo/I')
    assert (nested_runner, 'x') not in nested_parameters
    with pytest.raises(ValueError, match='Runner child elements'):
        DraftModel(nested_content)
    with pytest.raises(subprocess.CalledProcessError):
        parse('<Plan><Unknown/></Plan>')


def test_draft_runner_parameters_round_trip_and_reject_invalid_edits():
    import pytest

    xml = '<Plan><Runner interface="demo/I" provider="demo/P" old="1"/></Plan>'
    draft = DraftModel(xml)
    assert not draft.set_runner_parameter((0,), 'old', '1')
    assert not draft.set_runner_pair((0,), 'demo/I', 'demo/P', {('demo/I', 'demo/P')})
    assert draft.to_xml() == xml
    for name in ('interface', 'provider', 'xmlns', 'xml:lang', 'bad name', 'bad="x" other'):
        with pytest.raises(ValueError):
            draft.set_runner_parameter((0,), name, 'value')
        assert draft.to_xml() == xml
    with pytest.raises(ValueError):
        draft.set_runner_parameter((0,), 'value', '\x00')
    with pytest.raises(ValueError):
        draft.remove_runner_parameter((0,), 'provider')
    with pytest.raises(ValueError):
        draft.remove_runner_parameter((0,), 'missing')
    assert draft.to_xml() == xml
    draft.set_runner_parameter((0,), 'target', 'first\nsecond & "quoted"')
    draft.set_runner_parameter((0,), 'old', '2')
    draft.remove_runner_parameter((0,), 'old')
    restored = DraftModel(draft.to_xml())
    assert dict(restored.root.children[0].attributes) == {
        'interface': 'demo/I', 'provider': 'demo/P', 'target': 'first\nsecond & "quoted"'}


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