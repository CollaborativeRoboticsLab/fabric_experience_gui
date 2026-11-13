#!/usr/bin/env python3

import json
from pathlib import Path
import sys

script_dir = Path(__file__).resolve().parent
if str(script_dir) in sys.path:
    sys.path.remove(str(script_dir))

from fabric_experience_gui.automation import parse_focused_checks_args, run_focused_checks


def main() -> int:
    args, extra_colcon_args = parse_focused_checks_args()
    report = run_focused_checks(args.workspace_root, extra_colcon_args=extra_colcon_args)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())