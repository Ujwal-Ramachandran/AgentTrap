"""AT-SEC-001 regressions. All process creation is mocked; no Docker is needed."""
from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.targets import CmdResult, DockerExecTarget, MockTarget
from harness.experiment import reset_container, run_cell


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class ResetSecurityTests(unittest.TestCase):
    def test_direct_reset_rejects_commands_even_when_reset_disabled(self):
        for enabled in (True, False):
            for value in ("echo unexpected", " ", "x; y", None, False, 0, [], {}):
                with self.subTest(enabled=enabled, value=value), \
                     patch("agent.targets.subprocess.run") as run, \
                     patch("agent.targets.subprocess.Popen") as popen:
                    target = DockerExecTarget("decoy", reset_cmd=value, reset_each_run=enabled)
                    with self.assertRaisesRegex(ValueError, "reset_cmd is unsupported"):
                        target.reset()
                    run.assert_not_called()
                    popen.assert_not_called()

    def test_empty_reset_only_starts_and_checks_shell(self):
        target = DockerExecTarget("decoy")
        with patch.object(target, "_start_shell", return_value=True) as start, \
             patch.object(target, "run", return_value=CmdResult("", "", 0)) as ready, \
             patch("agent.targets.subprocess.run") as process:
            target.reset()
        start.assert_called_once_with()
        ready.assert_called_once_with(":", timeout_s=10.0)
        process.assert_not_called()

    def test_shell_launch_failure_is_reported(self):
        target = DockerExecTarget("decoy")
        target._start_error = "docker unavailable"
        with patch.object(target, "_start_shell", return_value=False), \
             patch.object(target, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "docker unavailable"):
                target.reset()
        run.assert_not_called()
        self.assertTrue(target._session_failed)

    def test_unusable_shell_is_closed_and_reported(self):
        for failure in (CmdResult("", "shell closed", None),
                        CmdResult("", "timeout", None), CmdResult("", "denied", 1)):
            with self.subTest(failure=failure):
                target = DockerExecTarget("decoy")
                with patch.object(target, "_start_shell", return_value=True), \
                     patch.object(target, "run", return_value=failure), \
                     patch.object(target, "_close") as close:
                    with self.assertRaisesRegex(RuntimeError, "target reset failed"):
                        target.reset()
                close.assert_called_once_with()
                self.assertTrue(target._session_failed)

    def test_mock_reset_still_clears_root_state(self):
        target = MockTarget(script={"id": "uid=0"})
        target.run("id", 1)
        self.assertTrue(target.is_rooted())
        target.reset()
        self.assertFalse(target.is_rooted())

    def test_recreation_uses_fixed_checked_argument_lists(self):
        with patch("harness.experiment.subprocess.run", side_effect=[
            completed("decoy\nother\n"), completed(), completed("container-id\n"),
            completed("true\n"),
        ]) as run:
            reset_container("registry:5000/decoy:latest", "decoy")
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            ["docker", "rm", "-f", "--", "decoy"],
            ["docker", "run", "-d", "--name", "decoy", "--network", "none", "--",
             "registry:5000/decoy:latest"],
            ["docker", "inspect", "--format", "{{.State.Running}}", "--", "decoy"],
        ])
        for call in run.call_args_list:
            self.assertIs(call.kwargs["shell"], False)
            self.assertEqual(call.kwargs["timeout"], 60)

    def test_absent_container_skips_removal_with_exact_name_matching(self):
        with patch("harness.experiment.subprocess.run", side_effect=[
            completed("decoy-other\n"), completed("id"), completed("true"),
        ]) as run:
            reset_container("image", "decoy")
        self.assertEqual([call.args[0][1] for call in run.call_args_list],
                         ["ps", "run", "inspect"])

    def test_invalid_operands_are_rejected_before_process_creation(self):
        for field in ("image", "container", "network"):
            for value in ("--help", "", "x;echo bad", "x y", "x\ny", None, [], {}):
                with self.subTest(field=field, value=value), \
                     patch("harness.experiment.subprocess.run") as run:
                    args = dict(image="image", container="decoy", network="none")
                    args[field] = value
                    with self.assertRaisesRegex(ValueError, f"invalid {field}"):
                        reset_container(**args)
                    run.assert_not_called()

    def test_every_reset_operation_stops_on_nonzero_timeout_or_launch_failure(self):
        operations = ("lookup", "removal", "creation", "verification")
        successful = [completed("decoy\n"), completed(), completed("id"), completed("true")]
        for index, operation in enumerate(operations):
            for failure, message in (
                (completed(stderr="permission denied", returncode=1), "permission denied"),
                (subprocess.TimeoutExpired(["docker"], 60), "timed out"),
                (OSError("unavailable"), "could not start"),
            ):
                with self.subTest(operation=operation, message=message), \
                     patch("harness.experiment.subprocess.run",
                           side_effect=successful[:index] + [failure]) as run:
                    with self.assertRaisesRegex(RuntimeError, f"{operation}.*{message}"):
                        reset_container("image", "decoy")
                    self.assertEqual(run.call_count, index + 1)

    def test_stopped_container_is_a_reset_failure(self):
        with patch("harness.experiment.subprocess.run", side_effect=[
            completed(), completed("id"), completed("false\n"),
        ]):
            with self.assertRaisesRegex(RuntimeError, "container is not running"):
                reset_container("image", "decoy")

    def test_reset_diagnostic_is_bounded(self):
        with patch("harness.experiment.subprocess.run",
                   return_value=completed(stderr="x" * 5000, returncode=1)):
            with self.assertRaises(RuntimeError) as raised:
                reset_container("image", "decoy")
        self.assertLess(len(str(raised.exception)), 1100)

    def test_experiment_harness_aborts_before_counting_target_setup_failure(self):
        args = SimpleNamespace(
            target="docker", runs=2, image="image", container="decoy", user="lowpriv",
            backend="mock", model="", think=None, screen="mock", max_steps=5,
            max_tokens=100, results_dir="unused", seed_script="unused")
        result = Mock()
        result.to_dict.return_value = {
            "outcome": "error", "steps_taken": 0, "error": "shell unavailable"}
        with patch("harness.experiment.reset_container") as reset, \
             patch("harness.experiment.seed_decoy") as seed, \
             patch("harness.experiment._read_docker_flag",
                   return_value="FLAG{test-flag}") as read_flag, \
             patch("harness.experiment.run_agent", return_value=result) as run:
            with self.assertRaisesRegex(RuntimeError, "target setup failed: shell unavailable"):
                run_cell(False, False, args)
        reset.assert_called_once_with("image", "decoy")
        read_flag.assert_called_once_with("decoy")
        seed.assert_not_called()
        run.assert_called_once()
