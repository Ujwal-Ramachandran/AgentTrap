"""Run the AgentTrap CLI repeatedly without adding batch-specific output."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run python -m agent.run repeatedly with the same arguments.")
    parser.add_argument("--runs", type=int, required=True,
                        help="number of sequential agent runs")
    args, agent_args = parser.parse_known_args(argv)

    if args.runs < 1:
        parser.error("--runs must be at least 1")

    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-m", "agent.run", *agent_args]
    for _ in range(args.runs):
        completed = subprocess.run(command, cwd=root)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
