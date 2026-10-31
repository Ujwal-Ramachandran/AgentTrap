"""CLI wrapper: python -m agent.run (Q2).

The run harness normally calls run_agent() directly; this is for manual one-off
runs during development. Ollama is the default backend.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
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


def _result_payload(result, full: bool = False) -> dict:
    """Return the CLI result view without changing the persisted summary."""
    payload = result.to_dict()
    if not full:
        payload.pop("error", None)
        payload.pop("config", None)
    return payload


_CANONICAL_DECOY_SCRIPTS = {
    "agenttrap-sudo-find": "decoy/sudo_find/run_decoy.py",
    "agenttrap-cron-writable-copy": "decoy/cron_writable_copy/run_decoy.py",
    "agenttrap-cron-writable-suid-shell": (
        "decoy/cron_writable_suid_shell/run_decoy.py"
    ),
    "agenttrap-suid-writable-task": "decoy/suid_writable_task/run_decoy.py",
    "agenttrap-suid-command-exec": "decoy/suid_command_exec/run_decoy.py",
}

_DECOY_SCRIPTS = {
    **_CANONICAL_DECOY_SCRIPTS,
    # Historical aliases keep old run summaries and scripts reproducible.
    "agenttrap-simple": "decoy/sudo_find/run_decoy.py",
    "agenttrap-simple-2": "decoy/cron_writable_copy/run_decoy.py",
    "agenttrap-simple-3": "decoy/cron_writable_suid_shell/run_decoy.py",
    "agenttrap-simple-4": "decoy/suid_writable_task/run_decoy.py",
    "agenttrap-simple-5": "decoy/suid_command_exec/run_decoy.py",
}


def _prepare_docker_decoy(container: str, script: str | None = None) -> None:
    """Build the selected image and create a fresh container with its name."""
    root = Path(__file__).resolve().parents[1]
    inferred_script = script is None
    script = script or _DECOY_SCRIPTS.get(container)
    if script is None:
        known = ", ".join(sorted(_CANONICAL_DECOY_SCRIPTS))
        raise RuntimeError(
            f"unknown Docker decoy {container!r}; choose one of: {known}")
    decoy_script = (root / script).resolve()
    if not decoy_script.is_file():
        raise RuntimeError(f"decoy script does not exist: {decoy_script}")

    try:
        image_exists = subprocess.run(
            ["docker", "image", "inspect", container],
            capture_output=True, text=True, check=False,
        ).returncode == 0
        subprocess.run(
            ["docker", "rm", "-f", container],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("docker is required for a Docker target") from exc

    command = [
        sys.executable, str(decoy_script),
        "--name", container,
        "--image", container,
    ]
    if image_exists and inferred_script:
        command.append("--no-build")
    completed = subprocess.run(command, cwd=root, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"decoy preparation failed with exit code {completed.returncode}")


def _read_docker_flag(container: str) -> str:
    """Read the freshly generated flag without exposing it to the agent."""
    try:
        completed = subprocess.run(
            ["docker", "exec", "-u", "root", container, "cat", "/root/flag.txt"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"could not read generated flag from Docker: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "unknown Docker error"
        raise RuntimeError(f"could not read generated flag from Docker: {detail}")
    flag = completed.stdout.strip()
    if not re.fullmatch(r"FLAG\{[^{}\r\n]+\}", flag):
        raise RuntimeError("decoy generated an invalid flag")
    return flag


def _remove_docker_decoy(container: str) -> None:
    """Remove the run container while preserving the image for reuse."""
    try:
        inspected = subprocess.run(
            ["docker", "container", "inspect", container],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if inspected.returncode != 0:
            return
        completed = subprocess.run(
            ["docker", "rm", "-f", container],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"could not remove Docker container {container!r}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "unknown Docker error"
        raise RuntimeError(
            f"could not remove Docker container {container!r}: {detail}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Run one AgentTrap pentest-agent run.")
    ap.add_argument("--backend", choices=["ollama", "anthropic", "openai", "cli", "mock"],
                    default="ollama", help="model backend (ollama is primary; mock needs nothing)")
    ap.add_argument("--model", default=None, help="model id (defaults per backend)")
    ap.add_argument("--target", choices=["mock", "docker"], default="mock")
    ap.add_argument(
        "--container",
        default="agenttrap-suid-writable-task",
        help="decoy image/profile; a fresh container with this name is created",
    )
    ap.add_argument(
        "--decoy-script",
        default=None,
        help="optional custom decoy launcher; otherwise inferred from --container",
    )
    ap.add_argument("--cht-on", action="store_true", help="decoy seeded with CHT deception")
    ap.add_argument("--hardened", action="store_true", help="defense-aware agent + screening")
    ap.add_argument("--screen", choices=["promptguard2", "mock", "null"],
                    default="promptguard2", help="input screen when hardened")
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--no-live", action="store_true",
                    help="disable live command and token output")
    ap.add_argument("--keep-container", action="store_true",
                    help="keep the Docker container after the run for debugging")
    ap.add_argument("--full", action="store_true",
                    help="include full result details, including error and config")
    args = ap.parse_args(argv)

    generated_flag = ""
    result = None
    try:
        if args.target == "docker":
            try:
                _prepare_docker_decoy(args.container, args.decoy_script)
                generated_flag = _read_docker_flag(args.container)
            except RuntimeError as exc:
                ap.error(str(exc))

        cfg = RunConfig(
            backend=args.backend, model=args.model or _DEFAULT_MODEL[args.backend],
            target_kind=args.target, container=args.container,
            cht_on=args.cht_on, hardened=args.hardened, screen_kind=args.screen,
            budgets=Budgets(max_steps=args.max_steps), results_dir=args.results_dir,
        )
        if generated_flag:
            # This value is used only by the harness exact-match scorer. It is not
            # included in the model prompt.
            cfg.root_flag = generated_flag
        if args.run_id:
            cfg.run_id = args.run_id

        result = run_agent(cfg, on_event=None if args.no_live else _live_event)
    finally:
        if args.target == "docker" and not args.keep_container:
            try:
                _remove_docker_decoy(args.container)
                print(f"Removed Docker container: {args.container}", flush=True)
            except RuntimeError as exc:
                print(f"WARNING: {exc}", file=sys.stderr, flush=True)
                if result is None:
                    raise
    if result is None:
        raise RuntimeError("agent run did not produce a result")
    print(json.dumps(_result_payload(result, full=args.full), indent=2))


if __name__ == "__main__":
    main()
