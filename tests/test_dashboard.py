"""Dashboard tests (Phase C). Skipped automatically if Flask is not installed.
Uses Flask's test client, the mock backend, and the mock target, so no model,
GPU, or network is needed. Run: python -m unittest tests.test_dashboard
"""
from __future__ import annotations

from pathlib import Path
import json
import sys
import time
import unittest
from unittest.mock import Mock, patch

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

    def test_reset_cmd_rejected_for_every_target_before_start(self):
        with patch("dashboard.app.manager.start_batch") as start:
            for target in ("mock", "docker", "unknown"):
                for value in ("echo unexpected", " ", "x; y", None, False, 0, [], {}):
                    with self.subTest(target=target, value=value):
                        response = self.client.post("/api/run", json={
                            "target": target, "reset_cmd": value})
                        self.assertEqual(response.status_code, 400)
                        self.assertIn("reset_cmd", response.get_json()["error"])
            start.assert_not_called()

    def test_absent_or_empty_reset_cmd_keeps_normal_mock_request(self):
        with patch("dashboard.app.manager.start_batch", return_value="batch") as start:
            for extra in ({}, {"reset_cmd": ""}):
                with self.subTest(extra=extra):
                    response = self.client.post("/api/run", json={
                        "backend": "mock", "target": "mock", **extra})
                    self.assertEqual(response.status_code, 200)
                    cfg = start.call_args.args[0]
                    self.assertEqual(cfg.target_kind, "mock")
                    self.assertEqual(cfg.backend, "mock")
                    self.assertEqual(cfg.reset_cmd, "")

    def test_setup_failure_reporting_and_counts(self):
        from agent.config import RunConfig
        from dashboard.broker import RunManager

        completed = {
            "success": False, "outcome": "gave_up", "steps_taken": 1,
            "wall_clock_s": 1.0, "guardrail_flags": 0, "traps_fired": [],
        }
        result = Mock(outcome="gave_up", steps_taken=1)
        result.to_dict.return_value = completed
        setup_error = Mock(outcome="error", steps_taken=0, error="shell unavailable")
        scenarios = (
            ("reset", [RuntimeError("reset denied")], None, result, 0, 0),
            ("later reset", [None, RuntimeError("reset denied")], None, result, 1, 1),
            ("seed", [None], RuntimeError("seed denied"), result, 0, 0),
            ("shell", [None], None, setup_error, 0, 1),
        )
        for name, resets, seed_error, run_result, count, calls in scenarios:
            with self.subTest(stage=name):
                manager = RunManager()
                cfg = RunConfig(target_kind="docker", cht_on=True, run_id="batch")
                with patch("dashboard.broker.threading.Thread") as thread, \
                     patch("dashboard.broker.reset_container", side_effect=resets), \
                     patch("dashboard.broker.seed_decoy", side_effect=seed_error) as seed, \
                     patch("dashboard.broker.run_agent", return_value=run_result) as run:
                    manager.start_batch(cfg, 3)
                    # Drive only the worker under mocks; never launch Docker or the agent.
                    thread.call_args.kwargs["target"]()
                self.assertEqual(run.call_count, calls)
                if name == "reset":
                    seed.assert_not_called()
                agg = manager.aggregate("batch")
                self.assertEqual(agg["status"], "failed")
                self.assertEqual(agg["last_outcome"], "Setup Failed")
                self.assertEqual(agg["completed"], count)
                self.assertEqual(agg["dsr"]["num"], count)
                self.assertEqual(agg["tsr"]["num"], 0)
                self.assertEqual(agg["gbr"]["num"], count)
                self.assertEqual(agg["failed_run"], count + 1)
                self.assertTrue(agg["error"])
                with patch("dashboard.app.manager", manager):
                    response = self.client.get("/api/batch/batch")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.get_json(), agg)
                    stream = self.client.get("/api/stream/batch").get_data(as_text=True)
                events = [json.loads(line[6:]) for line in stream.splitlines()
                          if line.startswith("data: ")]
                self.assertEqual(events[-1]["type"], "batch_end")
                self.assertEqual(events[-1]["status"], "failed")
                self.assertEqual(events[-1]["error"], agg["error"])
                self.assertEqual(sum(e["type"] == "batch_end" for e in events), 1)

    def test_mock_batch_does_not_reset_or_seed_containers(self):
        from agent.config import RunConfig
        from dashboard.broker import RunManager

        manager = RunManager()
        result = Mock()
        result.to_dict.return_value = {
            "success": False, "outcome": "gave_up", "wall_clock_s": 1.0,
            "guardrail_flags": 0, "traps_fired": [],
        }
        with patch("dashboard.broker.threading.Thread") as thread, \
             patch("dashboard.broker.reset_container") as reset, \
             patch("dashboard.broker.seed_decoy") as seed, \
             patch("dashboard.broker.run_agent", return_value=result) as run:
            manager.start_batch(RunConfig(target_kind="mock", cht_on=True, run_id="mock"), 2)
            thread.call_args.kwargs["target"]()
        reset.assert_not_called()
        seed.assert_not_called()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(manager.aggregate("mock")["completed"], 2)
        self.assertEqual(manager._history["mock"][-1], {"type": "batch_end"})

    def test_docker_batch_recreates_then_seeds_before_each_run(self):
        from agent.config import RunConfig
        from dashboard.broker import RunManager

        manager = RunManager()
        result = Mock(outcome="gave_up", steps_taken=1)
        result.to_dict.return_value = {
            "success": False, "outcome": "gave_up", "wall_clock_s": 1.0,
            "guardrail_flags": 0, "traps_fired": [],
        }
        order = []
        with patch("dashboard.broker.threading.Thread") as thread, \
             patch("dashboard.broker.reset_container", side_effect=lambda *a: order.append("reset")), \
             patch("dashboard.broker.seed_decoy", side_effect=lambda *a: order.append("seed")), \
             patch("dashboard.broker.run_agent",
                   side_effect=lambda *a, **kw: (order.append("run"), result)[1]):
            manager.start_batch(RunConfig(target_kind="docker", cht_on=True, run_id="docker"), 2)
            thread.call_args.kwargs["target"]()
        self.assertEqual(order, ["reset", "seed", "run"] * 2)
        self.assertEqual(manager.aggregate("docker")["completed"], 2)
        self.assertEqual(manager._history["docker"][-1], {"type": "batch_end"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
