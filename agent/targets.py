"""Targets: how the agent runs a command against the decoy.

Target is the seam between Ujwal's agent and the decoy host owned by
Bhageerath and Dan (see TASKS.md). DockerExecTarget runs commands with
`docker exec` (no network egress needed; see Q3 and ARCHITECTURE.md).
MockTarget is an in-process fake for the smoke test.

Note on docker exec: each call is a fresh exec as a fixed user, so privilege
does not persist across commands. The baseline therefore treats success as flag
capture (root_flag appears in output). If the decoy build needs persistent
escalation across commands, we switch to one long-lived shell session; that is
a known refinement to coordinate with the decoy owners.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import subprocess


@dataclass
class CmdResult:
    stdout: str
    stderr: str
    exit_code: int | None


class Target(Protocol):
    def reset(self) -> None: ...
    def run(self, command: str, timeout_s: float) -> CmdResult: ...
    def is_rooted(self) -> bool: ...


class DockerExecTarget:
    """Runs each command in the decoy container via docker exec. The real image,
    seeded files, and exact win-condition are owned by the decoy build."""

    def __init__(self, container: str, root_check_cmd: str = "",
                 root_check_expect: str = "0", reset_each_run: bool = True,
                 user: str = "lowpriv"):
        self.container = container
        self.root_check_cmd = root_check_cmd
        self.root_check_expect = root_check_expect
        self.reset_each_run = reset_each_run
        self.user = user

    def reset(self) -> None:
        if not self.reset_each_run:
            return
        # Restart from the clean image so no state leaks between runs (Q7).
        subprocess.run(["docker", "restart", self.container],
                       capture_output=True, text=True)

    def run(self, command: str, timeout_s: float) -> CmdResult:
        try:
            p = subprocess.run(
                ["docker", "exec", "-u", self.user, self.container,
                 "bash", "-lc", command],
                capture_output=True, text=True, timeout=timeout_s,
            )
            return CmdResult(p.stdout, p.stderr, p.returncode)
        except subprocess.TimeoutExpired:
            return CmdResult("", f"timeout after {timeout_s}s", None)
        except FileNotFoundError:
            return CmdResult("", "docker not found on host", None)

    def is_rooted(self) -> bool:
        if not self.root_check_cmd:
            return False
        try:
            p = subprocess.run(
                ["docker", "exec", self.container, "bash", "-lc", self.root_check_cmd],
                capture_output=True, text=True, timeout=10,
            )
            return self.root_check_expect in (p.stdout or "")
        except Exception:
            return False


class MockTarget:
    """In-process fake decoy for tests. A script maps exact commands to output;
    the winning command emits the root flag. No Docker, no network."""

    def __init__(self, root_flag: str = "FLAG{", script: dict | None = None):
        self.root_flag = root_flag
        self.script = script or {}
        self._rooted = False

    def reset(self) -> None:
        self._rooted = False

    def run(self, command: str, timeout_s: float) -> CmdResult:
        if command in self.script:
            out = self.script[command]
            if self.root_flag and self.root_flag in out:
                self._rooted = True
            return CmdResult(out, "", 0)
        return CmdResult(f"ran: {command}", "", 0)

    def is_rooted(self) -> bool:
        return self._rooted
