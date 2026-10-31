"""Run the AgentTrap CLI repeatedly and print a compact batch summary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def _average(results: list[dict], field: str) -> float:
    values = [result.get(field) for result in results
              if isinstance(result.get(field), (int, float))]
    return sum(values) / len(values) if values else 0.0


def _extract_result(output: str) -> dict | None:
    """Extract the final pretty-printed RunResult from CLI output."""
    starts = [index for index, char in enumerate(output) if char == "{"]
    for start in reversed(starts):
        try:
            result = json.loads(output[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and "outcome" in result:
            return result
    return None


def _print_live_progress(
    line: str,
    run_index: int,
    total_runs: int,
    completed: list[dict],
) -> None:
    """Render child live events as compact batch progress lines."""
    command_start = re.search(
        r"step\s+(\d+)\s+\|.*?total tokens:\s*(\d+)", line)
    if command_start:
        step, tokens = command_start.groups()
        print(
            f"[batch {run_index}/{total_runs}] step {step} | "
            f"tokens={tokens} | completed={len(completed)} | "
            f"rooted={sum(bool(r.get('success')) for r in completed)} | "
            f"flag={sum(bool(r.get('flag_captured')) for r in completed)} | "
            f"root={sum(bool(r.get('root_verified')) for r in completed)}",
            flush=True,
        )
        return

    run_end = re.search(
        r"run ended: outcome=([^,]+), steps=(\d+), total tokens=(\d+)",
        line,
    )
    if run_end:
        outcome, steps, tokens = run_end.groups()
        print(
            f"[batch {run_index}/{total_runs}] finished | "
            f"outcome={outcome} | steps={steps} | tokens={tokens}",
            flush=True,
        )


def _print_summary(results: list[dict | None], failures: int) -> None:
    print("\nBatch summary")
    print("-" * 106)
    print(f"{'Run':>3}  {'Outcome':<18} {'Success':<7} {'Steps':>5} "
          f"{'Tokens':>8} {'Time(s)':>8} {'Flag':>5} {'Root':>5} {'Budget reason':<14}")
    print("-" * 106)
    for index, result in enumerate(results, 1):
        if result is None:
            print(f"{index:>3}  {'cli_error':<18} {'no':<7} {'-':>5} "
                  f"{'-':>8} {'-':>8} {'-':>5} {'-':>5} {'-':<14}")
            continue
        print(
            f"{index:>3}  {str(result.get('outcome', 'unknown')):<18} "
            f"{'yes' if result.get('success') else 'no':<7} "
            f"{result.get('steps_taken', '-'):>5} "
            f"{result.get('total_tokens', '-'):>8} "
            f"{result.get('wall_clock_s', '-'):>8} "
            f"{'yes' if result.get('flag_captured') else 'no':>5} "
            f"{'yes' if result.get('root_verified') else 'no':>5} "
            f"{str(result.get('budget_reason') or '-'): <14}"
        )
    print("-" * 106)
    parsed = [result for result in results if result is not None]
    rooted = sum(bool(result.get("success")) for result in parsed)
    print(f"Runs: {len(results)} | Parsed: {len(parsed)} | "
          f"CLI errors: {failures}")
    outcomes = {}
    for result in parsed:
        outcome = str(result.get("outcome", "unknown"))
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    print(
        f"Flag captured: {sum(bool(result.get('flag_captured')) for result in parsed)} | "
        f"Root verified: {sum(bool(result.get('root_verified')) for result in parsed)} | "
        f"Rooted success: {rooted}"
    )
    print(
        f"Looped: {outcomes.get('looped', 0)} | "
        f"Gave up: {outcomes.get('gave_up', 0)} | "
        f"Budget exhausted: {outcomes.get('budget_exhausted', 0)} | "
        f"Errors: {outcomes.get('error', 0)}"
    )
    budget_reasons = {}
    for result in parsed:
        if result.get("outcome") == "budget_exhausted":
            reason = str(result.get("budget_reason") or "unknown")
            budget_reasons[reason] = budget_reasons.get(reason, 0) + 1
    print(
        f"Budget reasons: tokens={budget_reasons.get('tokens', 0)} | "
        f"wall clock={budget_reasons.get('wall_clock', 0)} | "
        f"max steps={budget_reasons.get('max_steps', 0)} | "
        f"unknown={budget_reasons.get('unknown', 0)}"
    )
    print(
        f"Average steps: {_average(parsed, 'steps_taken'):.2f} | "
        f"Average tokens: {_average(parsed, 'total_tokens'):.0f} | "
        f"Average time: {_average(parsed, 'wall_clock_s'):.2f}s"
    )


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
    results: list[dict | None] = []
    failures = 0
    completed: list[dict] = []
    for run_index in range(1, args.runs + 1):
        process = subprocess.Popen(
            command, cwd=root, stdout=subprocess.PIPE, stderr=None,
            text=True, bufsize=1)
        output: list[str] = []
        if process.stdout is not None:
            for line in process.stdout:
                output.append(line)
                _print_live_progress(line, run_index, args.runs, completed)
            process.stdout.close()
        returncode = process.wait()
        result = _extract_result("".join(output))
        results.append(result)
        if result is not None:
            completed.append(result)
        if returncode != 0:
            failures += 1
            _print_summary(results, failures)
            return returncode
    _print_summary(results, failures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
