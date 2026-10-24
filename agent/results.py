"""Structured outputs: StepRecord (per step) and RunResult (per run), answering
Q4 and Q5.

StepRecord lines are written as JSONL to results/logs/<run_id>.jsonl (the full
transcript). RunResult is the summary returned by run_agent and appended to
results/runs.jsonl; it feeds TSR, DSR, and GBR (see PRD.md, "Metrics").
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json

# outcome types logged per run (see PRD.md, "Metrics")
OUTCOME_ROOTED = "rooted"
OUTCOME_GAVE_UP = "gave_up"
OUTCOME_LOOPED = "looped"
OUTCOME_FLOODED = "flooded"
OUTCOME_BUDGET = "budget_exhausted"
OUTCOME_ERROR = "error"


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
    steps_taken: int = 0
    total_tokens: int = 0
    wall_clock_s: float = 0.0
    traps_fired: list[str] = field(default_factory=list)
    guardrail_flags: int = 0   # inputs PromptGuard 2 flagged this run (Phase B)
    transcript_path: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class StepLogger:
    """Writes one JSONL file per run under results/logs/."""

    def __init__(self, results_dir: str, run_id: str):
        self.dir = Path(results_dir) / "logs"
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


def append_run(results_dir: str, result: RunResult) -> None:
    """Append one run summary to results/runs.jsonl."""
    p = Path(results_dir) / "runs.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
