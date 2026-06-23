#!/usr/bin/env python
"""CLI: run the JARVIS brain benchmark suite. Usage: python benchmarks/run.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.brain.benchmarks import run_all  # noqa: E402

if __name__ == "__main__":
    report = run_all()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["passed"] else 1)
