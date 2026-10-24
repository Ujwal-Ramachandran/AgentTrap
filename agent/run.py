"""CLI wrapper: python -m agent.run (Q2).

The run harness normally calls run_agent() directly; this is for manual
one-off runs during development.
"""
from __future__ import annotations

import argparse
import json

from .config import Budgets, RunConfig
from .loop import run_agent


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Run one AgentTrap pentest-agent run.")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--target", choices=["mock", "docker"], default="mock")
    ap.add_argument("--container", default="agenttrap-decoy")
    ap.add_argument("--cht-on", action="store_true", help="decoy seeded with CHT deception")
    ap.add_argument("--hardened", action="store_true", help="defense-aware agent (Phase B)")
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)

    cfg = RunConfig(
        model=args.model, target_kind=args.target, container=args.container,
        cht_on=args.cht_on, hardened=args.hardened,
        budgets=Budgets(max_steps=args.max_steps), results_dir=args.results_dir,
    )
    if args.run_id:
        cfg.run_id = args.run_id

    result = run_agent(cfg)
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
