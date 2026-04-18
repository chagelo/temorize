#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.resolve()


def main():
    cmd = [
        sys.executable,
        str(REPO_ROOT / "temorize.py"),
        "preview",
        *sys.argv[1:],
    ]
    return subprocess.run(cmd, cwd=REPO_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
