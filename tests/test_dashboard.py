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
        self.assertIn(b"AgentTrap", r.data)

    def test_run_lifecycle(self):
        r = self.client.post("/api/run", json={"backend": "mock", "target": "mock",
                                               "max_steps": 6})
        self.assertEqual(r.status_code, 200)
        run_id = r.get_json()["run_id"]

        result = None
        for _ in range(100):  # the run is quick; poll up to ~5s
            resp = self.client.get(f"/api/result/{run_id}")
            if resp.status_code == 200:
                result = resp.get_json()
                break
            time.sleep(0.05)
        self.assertIsNotNone(result, "run did not finish in time")
        self.assertEqual(result["type"], "run_end")
        self.assertIn(result["outcome"],
                      ("rooted", "gave_up", "looped", "budget_exhausted", "error"))

    def test_result_pending_is_202(self):
        resp = self.client.get("/api/result/no-such-run")
        self.assertEqual(resp.status_code, 202)


if __name__ == "__main__":
    unittest.main(verbosity=2)
