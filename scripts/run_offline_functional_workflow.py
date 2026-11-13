#!/usr/bin/env python3

import json
from pathlib import Path
import sys

script_dir = Path(__file__).resolve().parent
if str(script_dir) in sys.path:
    sys.path.remove(str(script_dir))

from fabric_experience_gui.automation import parse_offline_workflow_args, run_offline_functional_workflow


def main() -> int:
    args = parse_offline_workflow_args()
    report = run_offline_functional_workflow(
        args.db_path,
        args.audit_root,
        args.feedback_root,
        args.out_dir,
        planning_request_id=args.planning_request_id,
        candidate_plan_id=args.candidate_plan_id,
        graph_hash=args.graph_hash,
        candidate_node_id=args.candidate_node_id,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    explanation = report.get('explanation_verification')
    if explanation is None:
        return 0
    if not explanation.get('found'):
        return 2
    return 0 if explanation.get('success') else 3


if __name__ == '__main__':
    raise SystemExit(main())