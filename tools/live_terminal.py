"""Live terminal monitor for AgentTrap JSONL transcripts.

Examples:
    python tools/live_terminal.py
    python tools/live_terminal.py --run-id 20261027-190126-d77e
    python tools/live_terminal.py --log results/logs/20261027-190126-d77e.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Follow an AgentTrap run transcript in a live terminal.")
    parser.add_argument("--run-id", help="Run ID to follow.")
    parser.add_argument("--log", type=Path, help="Transcript JSONL path to follow.")
    parser.add_argument(
        "--logs-dir", type=Path, default=Path("results") / "logs",
        help="Directory containing transcripts when --log is omitted.")
    parser.add_argument(
        "--interval", type=float, default=0.5,
        help="Polling interval in seconds (default: 0.5).")
    return parser.parse_args()


def _find_log(args: argparse.Namespace) -> Path | None:
    if args.log is not None:
        return args.log
    if args.run_id:
        return args.logs_dir / f"{args.run_id}.jsonl"
    logs = sorted(args.logs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            records.append(record)
    return records


def _format_tokens(value: Any) -> str:
    return str(value) if isinstance(value, int) else "-"


def _render(path: Path, records: list[dict[str, Any]]) -> str:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    latest = records[-1] if records else {}
    step = latest.get("step", "-")
    command = latest.get("command") or "(waiting for first recorded step)"
    prompt_tokens = latest.get("prompt_tokens", 0)
    completion_tokens = latest.get("completion_tokens", 0)
    step_tokens = (prompt_tokens + completion_tokens
                   if isinstance(prompt_tokens, int)
                   and isinstance(completion_tokens, int) else "-")
    total_tokens = sum(
        record.get("prompt_tokens", 0) + record.get("completion_tokens", 0)
        for record in records
        if isinstance(record.get("prompt_tokens", 0), int)
        and isinstance(record.get("completion_tokens", 0), int)
    )
    status = "waiting for log update"
    if latest.get("note"):
        status = str(latest["note"])
    elif latest.get("exit_code") is not None:
        status = f"exit code {latest['exit_code']}"

    return (
        "\033[2J\033[H"
        "AgentTrap live terminal\n"
        f"Current time : {now}\n"
        f"Log         : {path}\n"
        f"Step        : {step}\n"
        f"Command     : {command}\n"
        f"Step tokens  : {_format_tokens(step_tokens)} "
        f"(prompt={_format_tokens(prompt_tokens)}, "
        f"completion={_format_tokens(completion_tokens)})\n"
        f"Total tokens : {total_tokens}\n"
        f"Status      : {status}\n"
        "\nPress Ctrl+C to stop.\n"
    )


def follow(path: Path, interval: float) -> None:
    if interval <= 0:
        raise ValueError("--interval must be greater than zero")
    while True:
        records = _read_records(path)
        sys.stdout.write(_render(path, records))
        sys.stdout.flush()
        time.sleep(interval)


def main() -> int:
    args = _parse_args()
    path = _find_log(args)
    if path is None:
        print(f"No JSONL transcripts found in {args.logs_dir}", file=sys.stderr)
        return 1
    try:
        follow(path, args.interval)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as exc:
        print(f"live terminal failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
