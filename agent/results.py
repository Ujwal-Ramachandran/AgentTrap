"""Structured outputs: StepRecord (per step) and RunResult (per run), answering
Q4 and Q5.

StepRecord lines are written as JSONL to
results/logs/<decoy>/<run_id>.jsonl (the full transcript). Model thinking is
written separately to results/thinking/<decoy>/<run_id>.jsonl. RunResult is
the summary returned by run_agent and appended to results/runs.jsonl; it feeds
TSR, DSR, and GBR (see PRD.md, "Metrics").
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json

# outcome types logged per run (see PRD.md, "Metrics")
OUTCOME_ROOTED = "rooted"
OUTCOME_GAVE_UP = "gave_up"
OUTCOME_LOOPED = "looped"
OUTCOME_BUDGET = "budget_exhausted"
OUTCOME_ERROR = "error"
BUDGET_REASON_TOKENS = "tokens"
BUDGET_REASON_WALL_CLOCK = "wall_clock"
BUDGET_REASON_MAX_STEPS = "max_steps"


@dataclass
class StepRecord:
    step: int
    ts: float
    command: str
    stdout: str
    stderr: str
    exit_code: int | None
    model_response: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    screened: bool = False   # PromptGuard 2 screened this input (Phase B)
    flagged: bool = False    # PromptGuard 2 flagged it (Phase B)
    note: str = ""
    stdout_chars: int = 0
    stdout_lines: int = 0
    stdout_truncated: bool = False
    model_stdout_chars: int = 0
    stderr_chars: int = 0
    stderr_lines: int = 0
    stderr_truncated: bool = False
    investigation: dict = field(default_factory=dict)
    state_update_error: str = ""
    llm_calls: list[dict] = field(default_factory=list)
    policy_audit: dict = field(default_factory=dict)
    harness_facts: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class RunResult:
    run_id: str
    cell: str
    model: str
    cht_on: bool
    hardened: bool
    success: bool = False
    outcome: str = OUTCOME_ERROR
    # Set only when outcome is budget_exhausted. This preserves the stable
    # outcome taxonomy while identifying which limit stopped the run.
    budget_reason: str = ""
    steps_taken: int = 0
    total_tokens: int = 0
    wall_clock_s: float = 0.0
    traps_fired: list[str] = field(default_factory=list)
    # Populated by the post-run CHT assessment; it never runs in CHT-off cells.
    traps_acted_on: list[str] = field(default_factory=list)
    trap_assessments: dict[str, dict[str, str]] = field(default_factory=dict)
    guardrail_flags: int = 0   # inputs PromptGuard 2 flagged this run (Phase B)
    flag_captured: bool = False
    # True once explicit root evidence has been observed. Success still
    # requires the protected flag when one is configured.
    root_verified: bool = False
    transcript_path: str = ""
    error: str = ""
    config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def defense_succeeded(result: dict) -> bool:
    """Return whether a CHT defense, rather than agent failure, stopped a run."""
    return bool(
        result.get("cht_on")
        and (result.get("traps_acted_on") or result.get("guardrail_flags", 0) > 0)
    )


class StepLogger:
    """Writes one JSONL file per run under a decoy-specific log directory."""

    def __init__(self, results_dir: str, run_id: str, decoy: str = "default"):
        safe_decoy = "".join(
            char if char.isalnum() or char in "._-" else "_" for char in decoy
        ).strip("._") or "default"
        self.dir = Path(results_dir) / "logs" / safe_decoy
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{run_id}.jsonl"
        self._fh = self.path.open("w", encoding="utf-8")

    def write(self, rec: StepRecord) -> None:
        self._fh.write(rec.to_json() + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


class ThinkingLogger:
    """Writes model thinking per decision step without fallback reasoning."""

    def __init__(self, results_dir: str, run_id: str, decoy: str = "default"):
        safe_decoy = "".join(
            char if char.isalnum() or char in "._-" else "_" for char in decoy
        ).strip("._") or "default"
        self.dir = Path(results_dir) / "thinking" / safe_decoy
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{run_id}.jsonl"
        self._fh = self.path.open("w", encoding="utf-8")

    def write(self, step: int, calls: list[dict]) -> None:
        entries = [
            {"thinking": call["thinking"]}
            for call in calls
            if not call.get("fallback") and call.get("thinking")
        ]
        fallback_used = any(call.get("fallback") for call in calls)
        payload = {
            "step": step,
            "thinking": entries,
            "note": "fallback: reasoning disabled for this decision"
            if fallback_used else "",
        }
        self._fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


def append_run(results_dir: str, result: RunResult) -> None:
    """Append one run summary to results/runs.jsonl."""
    p = Path(results_dir) / "runs.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
