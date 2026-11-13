#!/usr/bin/env python3

from pathlib import Path
import sys

script_dir = Path(__file__).resolve().parent
if str(script_dir) in sys.path:
    sys.path.remove(str(script_dir))

from fabric_experience_gui.app import main


if __name__ == '__main__':
    raise SystemExit(main())