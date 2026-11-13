#!/usr/bin/env python3

from pathlib import Path
import json
import sys

script_dir = Path(__file__).resolve().parent
if str(script_dir) in sys.path:
    sys.path.remove(str(script_dir))

from fabric_experience_gui.automation import parse_terminal_success_analysis_args, run_terminal_success_analysis


def main() -> int:
    args = parse_terminal_success_analysis_args()
    report = run_terminal_success_analysis(args.feedback_root, args.out_dir, db_path=args.db_path)
    print(json.dumps(report['summary'], indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())