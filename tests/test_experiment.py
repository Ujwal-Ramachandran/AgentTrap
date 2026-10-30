"""Tests for the experiment harness summary math. Stdlib unittest.
Run: python -m unittest tests.test_experiment
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.experiment import summarize  # noqa: E402


class SummarizeTests(unittest.TestCase):
    def test_rates_and_union(self):
        results = [
            {"success": True, "outcome": "rooted", "total_tokens": 100,
             "wall_clock_s": 1.0, "guardrail_flags": 0, "traps_fired": []},
            {"success": False, "outcome": "gave_up", "total_tokens": 300,
             "wall_clock_s": 3.0, "guardrail_flags": 1, "traps_fired": ["T1.1_cloak"]},
        ]
        s = summarize(results, 2)
        self.assertEqual(s["tsr"], 50.0)
        self.assertEqual(s["dsr"], 50.0)
        self.assertEqual(s["gbr"], 50.0)        # one run had zero guardrail flags
        self.assertEqual(s["avg_tokens"], 200)
        self.assertIn("T1.1_cloak", s["traps_fired_union"])
        self.assertEqual(s["outcomes"]["rooted"], 1)

    def test_empty(self):
        s = summarize([], 20)
        self.assertEqual(s["tsr"], 0.0)
        self.assertEqual(s["runs"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
