from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run(args: list[str]) -> int:
    completed = subprocess.run(args, cwd=ROOT)
    return completed.returncode


def run_tests() -> int:
    return _run([sys.executable, "-m", "pytest", "tests"])


def serve_example() -> int:
    return _run([sys.executable, "-m", "mkdocs", "serve", "-f", "example/mkdocs.yaml"])
