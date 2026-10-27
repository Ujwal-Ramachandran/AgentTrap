"""CLI wrapper: python -m agent.run (Q2).

The run harness normally calls run_agent() directly; this is for manual one-off
runs during development. Ollama is the default backend.
"""
from __future__ import annotations

import argparse
import json
import time

from .config import Budgets, RunConfig
from .loop import run_agent

_DEFAULT_MODEL = {
    "ollama": "qwen3:8b",
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-4o-mini",
    "cli": "",
    "mock": "",
}


def _live_event(event: dict) -> None:
    """Print command and token state in the same terminal as the harness."""
    event_type = event.get("type")
    if event_type == "run_start":
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
              f"run {event.get('run_id')} started", flush=True)
    elif event_type == "command_start":
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"step {event['step']} | command: {event['command']} | "
            f"step tokens: {event['step_tokens']} "
            f"(prompt={event['prompt_tokens']}, "
            f"completion={event['completion_tokens']}) | "
            f"total tokens: {event['total_tokens']}",
            flush=True)
    elif event_type == "step":
        if event.get("exit_code") is not None:
            print(f"  -> exit={event['exit_code']}", flush=True)
        elif event.get("note"):
            print(f"  -> {event['note']}", flush=True)
    elif event_type == "run_end":
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
              f"run ended: outcome={event.get('outcome')}, "
              f"steps={event.get('steps_taken')}, "
              f"total tokens={event.get('total_tokens')}", flush=True)


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
    ap.add_argument("--no-live", action="store_true",
                    help="disable live command and token output")
    args = ap.parse_args(argv)

    cfg = RunConfig(
        backend=args.backend, model=args.model or _DEFAULT_MODEL[args.backend],
        target_kind=args.target, container=args.container,
        cht_on=args.cht_on, hardened=args.hardened, screen_kind=args.screen,
        budgets=Budgets(max_steps=args.max_steps), results_dir=args.results_dir,
    )
    if args.run_id:
        cfg.run_id = args.run_id

    result = run_agent(cfg, on_event=None if args.no_live else _live_event)
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
