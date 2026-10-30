"""Targets: how the agent runs a command against the decoy.

Target is the seam between Ujwal's agent and the decoy host owned by Bhageerath
and Dan (see TASKS.md). DockerExecTarget keeps one persistent shell session
inside the decoy (docker exec -i ... bash), so the working directory, environment,
and any privilege the agent gains (for example after a sudo escalation) carry
across commands. MockTarget is an in-process fake for tests.

No network egress is needed: the agent drives the shell over docker's stdio.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import queue
import subprocess
import threading
import time
import uuid


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
    """A persistent shell inside the decoy container.

    One `docker exec -i ... bash` process is kept open and fed commands over
    stdin; stdout and stderr are merged and read by a background thread, so a
    per-command timeout never blocks the loop. State persists across commands
    within a run. reset() optionally runs reset_cmd (the decoy owners' recreate
    or restore, item 7) and then starts a fresh shell, so nothing leaks between
    runs (Q7). exec_argv overrides the launch command, which lets tests drive a
    local bash instead of docker.
    """

    def __init__(self, container: str, user: str = "lowpriv", reset_cmd: str = "",
                 root_check_cmd: str = "", root_check_expect: str = "0",
                 reset_each_run: bool = True, exec_argv: list[str] | None = None):
        self.container = container
        self.user = user
        self.reset_cmd = reset_cmd
        self.root_check_cmd = root_check_cmd
        self.root_check_expect = root_check_expect
        self.reset_each_run = reset_each_run
        self.exec_argv = exec_argv or [
            "docker", "exec", "-i", "-u", user, container, "/bin/bash"]
        self._proc: subprocess.Popen | None = None
        self._q: queue.Queue = queue.Queue()

    def _pump(self, proc: subprocess.Popen) -> None:
        while True:
            line = proc.stdout.readline()   # type: ignore[union-attr]
            if line == "":
                break
            self._q.put(line)
        self._q.put(None)                   # EOF sentinel

    def _start_shell(self) -> bool:
        self._close()
        self._q = queue.Queue()
        try:
            self._proc = subprocess.Popen(
                self.exec_argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1)
        except FileNotFoundError:
            self._proc = None
            return False
        # On Windows, text-mode pipes translate "\n" to "\r\n" on write, which
        # corrupts every command the Linux shell receives. Force LF so the
        # container sees clean commands.
        try:
            self._proc.stdin.reconfigure(newline="\n")      # type: ignore[union-attr]
        except Exception:
            pass
        threading.Thread(target=self._pump, args=(self._proc,), daemon=True).start()
        return True

    def reset(self) -> None:
        if self.reset_each_run and self.reset_cmd:
            subprocess.run(self.reset_cmd, shell=True, capture_output=True, text=True)
        self._start_shell()

    def run(self, command: str, timeout_s: float) -> CmdResult:
        if self._proc is None and not self._start_shell():
            return CmdResult("", "docker not found or shell failed to start", None)

        sentinel = f"__ATDONE_{uuid.uuid4().hex[:8]}__"
        try:
            self._proc.stdin.write(command.replace("\r", "") + "\n")  # type: ignore[union-attr]
            self._proc.stdin.write(f"printf '%s%d\\n' {sentinel} $?\n")  # type: ignore[union-attr]
            self._proc.stdin.flush()                                 # type: ignore[union-attr]
        except (BrokenPipeError, ValueError) as exc:
            return CmdResult("", f"shell write failed: {exc}", None)

        lines: list[str] = []
        deadline = time.time() + timeout_s
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return CmdResult("".join(lines), f"timeout after {timeout_s}s", None)
            try:
                line = self._q.get(timeout=remaining)
            except queue.Empty:
                return CmdResult("".join(lines), f"timeout after {timeout_s}s", None)
            if line is None:
                return CmdResult("".join(lines), "shell closed", None)
            if sentinel in line:
                try:
                    rc = int(line.strip().split(sentinel, 1)[1])
                except (ValueError, IndexError):
                    rc = None
                return CmdResult("".join(lines), "", rc)
            lines.append(line)

    def is_rooted(self) -> bool:
        if not self.root_check_cmd:
            return False
        out = self.run(self.root_check_cmd, 10)
        # match a whole output line, not a loose substring: expect "0" must not
        # be satisfied by "uid=1000" or stray output.
        return self.root_check_expect in [ln.strip() for ln in out.stdout.splitlines()]

    def _close(self) -> None:
        if self._proc is not None:
            try:
                self._proc.stdin.close()      # type: ignore[union-attr]
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None


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
