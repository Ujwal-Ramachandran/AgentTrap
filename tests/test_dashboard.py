"""Dashboard tests (Phase C). Skipped automatically if Flask is not installed.
Uses Flask's test client, the mock backend, and the mock target, so no model,
GPU, or network is needed. Run: python -m unittest tests.test_dashboard
"""
from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import flask  # noqa: F401
    HAVE_FLASK = True
except Exception:
    HAVE_FLASK = False


@unittest.skipUnless(HAVE_FLASK, "flask not installed")
class DashboardTests(unittest.TestCase):
    def setUp(self):
        from dashboard.app import create_app
        self.client = create_app().test_client()

    def test_index_served(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Live Console", r.data)
        self.assertIn(b"Task Success Rate", r.data)
        self.assertIn(b"T5.2", r.data)

    def test_batch_lifecycle(self):
        r = self.client.post("/api/run", json={"backend": "mock", "target": "mock",
                                               "runs": 3, "max_steps": 6})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        batch_id, total = body["batch_id"], body["total"]
        self.assertEqual(total, 3)

        agg = None
        for _ in range(100):  # the batch is quick; poll up to ~5s
            resp = self.client.get(f"/api/batch/{batch_id}")
            if resp.status_code == 200:
                agg = resp.get_json()
                if agg["completed"] == total:
                    break
            time.sleep(0.05)
        self.assertIsNotNone(agg, "batch did not produce an aggregate")
        self.assertEqual(agg["completed"], total)
        for key in ("tsr", "dsr", "gbr"):
            self.assertEqual(agg[key]["den"], total)
            self.assertIn("pct", agg[key])
        self.assertIn(agg["last_outcome"],
                      ("Attack Success", "Defense Success", "Timeout"))

    def test_batch_pending_is_202(self):
        resp = self.client.get("/api/batch/no-such-batch")
        self.assertEqual(resp.status_code, 202)

    def test_selected_container_is_used_as_image(self):
        from unittest.mock import patch

        with patch("dashboard.app.manager.start_batch",
                   return_value="batch-decoy") as start_batch:
            response = self.client.post(
                "/api/run",
                json={"backend": "mock", "target": "docker",
                      "container": "agenttrap-decoy", "runs": 1},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(start_batch.call_args.kwargs["image"], "agenttrap-decoy")
        self.assertEqual(
            start_batch.call_args.args[0].container_user, "user1")
        self.assertFalse(start_batch.call_args.args[0].think)

    def test_thinking_on_is_passed_to_batch(self):
        from unittest.mock import patch

        with patch("dashboard.app.manager.start_batch",
                   return_value="batch-thinking") as start_batch:
            response = self.client.post(
                "/api/run",
                json={"backend": "mock", "target": "mock", "runs": 1,
                      "thinking": "thinking-on"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(start_batch.call_args.args[0].think)

    def test_selected_traps_are_passed_to_batch(self):
        from unittest.mock import patch

        with patch("dashboard.app.manager.start_batch",
                   return_value="batch-traps") as start_batch:
            response = self.client.post(
                "/api/run",
                json={"backend": "mock", "target": "mock", "runs": 1,
                      "traps": ["T5"]},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(start_batch.call_args.kwargs["enabled_traps"], ["T5"])

    def test_empty_trap_selection_turns_cht_off(self):
        response = self.client.post(
            "/api/run",
            json={"backend": "mock", "target": "mock", "runs": 1,
                  "traps": []},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["cht_on"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
