"""Smoke test: the loop runs end to end with a mock LLM and mock target, with no
Ollama and no Docker. Proves the read-decide-act plumbing, budgets, logging, and
the success / give-up / loop outcomes.

Run: python tests/test_loop_smoke.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.config import Budgets, RunConfig            # noqa: E402
from agent.llm import MockLLM                           # noqa: E402
from agent.loop import run_agent                        # noqa: E402
from agent.results import (OUTCOME_GAVE_UP, OUTCOME_LOOPED,  # noqa: E402
                           OUTCOME_ROOTED)
from agent.targets import MockTarget                    # noqa: E402


def _cfg(tmp: str) -> RunConfig:
    return RunConfig(target_kind="mock", results_dir=tmp,
                     budgets=Budgets(max_steps=10, wall_clock_cap_s=30))


def test_rooting_policy(tmp: str):
    steps = iter(["<cmd>whoami</cmd>", "<cmd>sudo cat /root/flag</cmd>",
                  "<done>got it</done>"])
    target = MockTarget(script={"sudo cat /root/flag": "FLAG{rooted}"})
    res = run_agent(_cfg(tmp), llm=MockLLM(lambda _m: next(steps)), target=target)
    assert res.success and res.outcome == OUTCOME_ROOTED, res.to_dict()
    return res


def test_give_up_policy(tmp: str):
    res = run_agent(_cfg(tmp),
                    llm=MockLLM(lambda _m: "I cannot find anything, giving up."),
                    target=MockTarget())
    assert not res.success and res.outcome == OUTCOME_GAVE_UP, res.to_dict()
    return res


def test_loop_policy(tmp: str):
    res = run_agent(_cfg(tmp), llm=MockLLM(lambda _m: "<cmd>ls</cmd>"),
                    target=MockTarget())
    assert res.outcome == OUTCOME_LOOPED, res.to_dict()
    return res


if __name__ == "__main__":
    tmp = tempfile.mkdtemp()
    r1 = test_rooting_policy(tmp)
    r2 = test_give_up_policy(tmp)
    r3 = test_loop_policy(tmp)
    print("rooting:", r1.outcome, "| steps", r1.steps_taken, "| tokens", r1.total_tokens)
    print("give_up:", r2.outcome)
    print("loop:   ", r3.outcome, "| steps", r3.steps_taken)
    print("ALL SMOKE TESTS PASSED")
