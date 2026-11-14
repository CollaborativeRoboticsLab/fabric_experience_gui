import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from fabric_experience_gui.plan_sandbox import build_plan_sandbox_graph, build_tuning_proposal, parse_optional_json
from fabric_experience_gui.draft_model import DraftModel
from fabric_experience_gui.services.fabric_graph_client import parse_runnable_specs


def test_runnable_spec_pairs_require_consistent_metadata():
    from types import SimpleNamespace
    import pytest

    def response(keys, specs):
        return SimpleNamespace(index_of_specs=keys, runnable_specs=[SimpleNamespace(spec=spec) for spec in specs])

    valid = 'interface:\n  name: demo/Interface\nprovider:\n  name: demo/Provider\n'
    assert parse_runnable_specs(response(['demo/Provider'], [valid])) == (('demo/Interface', 'demo/Provider'),)
    for payload in (response([], [valid]), response(['other'], [valid]),
                    response(['demo/Provider'], ['interface: [']),
                    response(['demo/Provider'], [valid + 'provider: {name: demo/Provider}\n']),
                    response([' '], ['interface: {name: demo/Interface}\nprovider: {name: " "}\n']),
                    response(['demo/Provider', 'demo/Provider'], [valid, valid]),
                    response(['demo/Provider'], ['provider: {name: demo/Provider}'])):
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