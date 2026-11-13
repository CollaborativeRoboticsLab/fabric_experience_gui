#!/usr/bin/env python3

import argparse
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Launch the Experience Inspector rqt plugin with optional startup paths.'
    )
    parser.add_argument('--db-path', default='', help='Optional path to core_graphrag.sqlite3 opened on startup.')
    parser.add_argument('--audit-root', default='', help='Optional path to planner_prompt_audit opened on startup.')
    args, remaining = parser.parse_known_args()

    command = ['rqt', '--standalone', 'fabric_experience_gui/ExperienceInspectorPlugin', *remaining]
    plugin_args = []
    if args.db_path:
        plugin_args.extend(['--db-path', args.db_path])
    if args.audit_root:
        plugin_args.extend(['--audit-root', args.audit_root])
    if plugin_args:
        command.extend(['--args', *plugin_args])

    return subprocess.call(command)


if __name__ == '__main__':
    raise SystemExit(main())