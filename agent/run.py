"""CLI wrapper: python -m agent.run (Q2).

The run harness normally calls run_agent() directly; this is for manual one-off
runs during development. Ollama is the default backend.
"""
from __future__ import annotations

import argparse
import json

from .config import Budgets, RunConfig
from .loop import run_agent

_DEFAULT_MODEL = {
    "ollama": "qwen3:8b",
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-4o-mini",
    "cli": "",
    "mock": "",
}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Run one AgentTrap pentest-agent run.")
    ap.add_argument("--backend", choices=["ollama", "anthropic", "openai", "cli", "mock"],
                    default="ollama", help="model backend (ollama is primary; mock needs nothing)")
    ap.add_argument("--model", default=None, help="model id (defaults per backend)")
    ap.add_argument("--target", choices=["mock", "docker"], default="mock")
    ap.add_argument("--container", default="agenttrap-decoy")
    ap.add_argument("--cht-on", action="store_true", help="decoy seeded with CHT deception")
    ap.add_argument("--hardened", action="store_true", help="defense-aware agent + screening")
    ap.add_argument("--screen", choices=["promptguard2", "mock", "null"],
                    default="promptguard2", help="input screen when hardened")
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)

    cfg = RunConfig(
        backend=args.backend, model=args.model or _DEFAULT_MODEL[args.backend],
        target_kind=args.target, container=args.container,
        cht_on=args.cht_on, hardened=args.hardened, screen_kind=args.screen,
        budgets=Budgets(max_steps=args.max_steps), results_dir=args.results_dir,
    )
    if args.run_id:
        cfg.run_id = args.run_id

    result = run_agent(cfg)
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
