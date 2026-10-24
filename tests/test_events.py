"""Event-hook tests (Phase C): run_agent streams run_start, step, run_end through
the on_event callback. Stdlib unittest, no Flask, no GPU, no network.
Run: python -m unittest tests.test_events
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.config import Budgets, RunConfig            # noqa: E402
from agent.llm import MockLLM                           # noqa: E402
from agent.loop import run_agent                        # noqa: E402
from agent.targets import MockTarget                     # noqa: E402


class EventHookTests(unittest.TestCase):
    def test_event_sequence(self):
        events: list[dict] = []
        target = MockTarget(script={"sudo cat /root/flag": "FLAG{z}"})
        policy = iter(["<cmd>whoami</cmd>", "<cmd>sudo cat /root/flag</cmd>"])
        res = run_agent(
            RunConfig(target_kind="mock", results_dir=tempfile.mkdtemp(),
                      budgets=Budgets(max_steps=5, wall_clock_cap_s=30)),
            llm=MockLLM(lambda _m: next(policy, "<done>stop</done>")),
            target=target, on_event=events.append)

        types = [e["type"] for e in events]
        self.assertEqual(types[0], "run_start")
        self.assertEqual(types[-1], "run_end")
        self.assertEqual(types.count("step"), res.steps_taken)
        self.assertEqual(events[-1]["outcome"], res.outcome)
        self.assertEqual(events[0]["run_id"], res.run_id)

    def test_event_hook_errors_do_not_break_run(self):
        def bad_hook(_e):
            raise RuntimeError("subscriber exploded")
        res = run_agent(
            RunConfig(target_kind="mock", results_dir=tempfile.mkdtemp(),
                      budgets=Budgets(max_steps=3, wall_clock_cap_s=30)),
            llm=MockLLM(lambda _m: "<cmd>ls</cmd>"),
            target=MockTarget(), on_event=bad_hook)
        self.assertIn(res.outcome, ("looped", "budget_exhausted"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
