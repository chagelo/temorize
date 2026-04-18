#!/usr/bin/env python3
"""Compatibility entrypoint for `python3 temorize.py preview ...`."""

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.resolve()


def build_forward_command(argv):
    return [
        sys.executable,
        str(REPO_ROOT / "temorize.py"),
        "preview",
        *argv,
    ]


def main(argv=None):
    cmd = build_forward_command(argv or sys.argv[1:])
    return subprocess.run(cmd, cwd=REPO_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
