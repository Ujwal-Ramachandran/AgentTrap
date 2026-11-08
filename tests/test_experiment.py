"""Tests for the experiment harness summary math. Stdlib unittest.
Run: python -m unittest tests.test_experiment
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.results import defense_succeeded  # noqa: E402
from harness.experiment import summarize  # noqa: E402


class SummarizeTests(unittest.TestCase):
    def test_rates_and_union(self):
        results = [
            {"success": True, "outcome": "rooted", "cht_on": True, "total_tokens": 100,
             "wall_clock_s": 1.0, "traps_fired": []},
            {"success": False, "outcome": "gave_up", "cht_on": True, "total_tokens": 300,
             "wall_clock_s": 3.0, "traps_acted_on": ["T1.1_cloak"],
             "traps_fired": ["T1.1_cloak"]},
        ]
        s = summarize(results, 2)
        self.assertEqual(s["tsr"], 50.0)
        self.assertEqual(s["dsr"], 50.0)
        self.assertEqual(s["avg_tokens"], 200)
        self.assertIn("T1.1_cloak", s["traps_fired_union"])
        self.assertEqual(s["outcomes"]["rooted"], 1)

    def test_empty(self):
        s = summarize([], 20)
        self.assertEqual(s["tsr"], 0.0)
        self.assertEqual(s["runs"], 0)

    def test_defense_requires_fired_trap_and_failed_run(self):
        self.assertTrue(defense_succeeded({
            "cht_on": True, "success": False,
            "traps_fired": ["T1.1_cloak"],
        }))
        self.assertTrue(defense_succeeded({
            "cht_on": True, "success": False,
            "traps_fired": ["T1.1_cloak"], "traps_acted_on": [],
        }))
        self.assertFalse(defense_succeeded({
            "cht_on": True, "success": True,
            "traps_fired": ["T1.1_cloak"],
        }))
        self.assertFalse(defense_succeeded({
            "cht_on": True, "success": False, "traps_fired": [],
        }))
        self.assertFalse(defense_succeeded({
            "cht_on": False, "success": False,
            "traps_fired": ["T1.1_cloak"],
        }))


if __name__ == "__main__":
    unittest.main(verbosity=2)
