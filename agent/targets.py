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
import re


@dataclass
class CmdResult:
    stdout: str
    stderr: str
    exit_code: int | None


class Target(Protocol):
    def reset(self) -> None: ...
    def run(self, command: str, timeout_s: float) -> CmdResult: ...
    def is_rooted(self) -> bool: ...
    def close(self) -> None: ...


class DockerExecTarget:
    """A persistent shell inside the decoy container.

    One `docker exec -i ... bash` process is kept open and fed commands over
    stdin; stdout and stderr are merged and read by a background thread, so a
    per-command timeout never blocks the loop. State persists across commands
    within a run. reset() starts a fresh shell; container recreation belongs to
    the dashboard/experiment harness. reset_cmd and reset_each_run are retained
    for call compatibility, but nonempty reset_cmd values are unsupported.
    exec_argv overrides the launch command, which lets tests drive a local bash
    instead of docker.
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
        self._pump_thread: threading.Thread | None = None
        self._start_error = ""
        self._q: queue.Queue = queue.Queue()
        self._session_failed = False

    def _pump(self, proc: subprocess.Popen) -> None:
        output_queue = self._q
        try:
            while True:
                line = proc.stdout.readline()   # type: ignore[union-attr]
                if line == b"":
                    break
                output_queue.put(line)
        except (OSError, ValueError):
            # The pipe can be invalidated while the process is being stopped.
            pass
        finally:
            output_queue.put(None)              # EOF sentinel

    def _start_shell(self) -> bool:
        self._close()
        self._q = queue.Queue()
        self._start_error = ""
        try:
            self._proc = subprocess.Popen(
                self.exec_argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, bufsize=0)
        except (FileNotFoundError, OSError) as exc:
            self._proc = None
            self._start_error = str(exc)
            return False
        self._pump_thread = threading.Thread(
            target=self._pump, args=(self._proc,), daemon=True)
        self._pump_thread.start()
        return True

    def reset(self) -> None:
        if self.reset_cmd != "":
            raise ValueError("reset_cmd is unsupported; use managed container recreation")
        self._session_failed = False
        if not self._start_shell():
            self._session_failed = True
            raise RuntimeError(f"target reset failed to start shell: {self._start_error}")
        # Popen success alone does not mean Docker successfully opened the shell.
        ready = self.run(":", timeout_s=10.0)
        if ready.exit_code != 0:
            self._close()
            self._session_failed = True
            detail = (ready.stderr or ready.stdout or "shell readiness check failed")[:1000]
            raise RuntimeError(f"target reset failed: {detail}")

    def run(self, command: str, timeout_s: float) -> CmdResult:
        if self._session_failed:
            return CmdResult("", "shell session invalidated; reset required", None)
        if self._proc is None and not self._start_shell():
            detail = f": {self._start_error}" if self._start_error else ""
            return CmdResult("", f"docker not found or shell failed to start{detail}", None)

        sentinel = f"__ATDONE_{uuid.uuid4().hex[:8]}__"
        command_to_run = _make_noninteractive(command)
        try:
            # Merge streams inside the container, before Docker transports them.
            # A brace group preserves cwd/environment in the persistent shell.
            command_bytes = ("{\n" + command_to_run.rstrip("\r\n")
                             + "\n} 2>&1\n").encode("utf-8")
            sentinel_bytes = (
                f"printf '\\n%s%d\\n' {sentinel} $?\n".encode("ascii"))
            self._proc.stdin.write(command_bytes)                    # type: ignore[union-attr]
            self._proc.stdin.write(sentinel_bytes)                   # type: ignore[union-attr]
            self._proc.stdin.flush()                                 # type: ignore[union-attr]
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._close()
            return CmdResult("", f"shell write failed: {exc}", None)

        lines: list[str] = []
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._close()
                self._session_failed = True
                return CmdResult("".join(lines), f"timeout after {timeout_s}s", None)
            try:
                line = self._q.get(timeout=remaining)
            except queue.Empty:
                self._close()
                self._session_failed = True
                return CmdResult("".join(lines), f"timeout after {timeout_s}s", None)
            if line is None:
                return CmdResult("".join(lines), "shell closed", None)
            text_line = line.decode("utf-8", errors="replace")
            if sentinel in text_line:
                try:
                    rc = int(text_line.strip().split(sentinel, 1)[1])
                except (ValueError, IndexError):
                    rc = None
                output = "".join(lines)
                # Remove only the framing newline, retaining command output.
                return CmdResult(output[:-1] if output.endswith("\n") else output, "", rc)
            lines.append(text_line)

    def is_rooted(self, timeout_s: float = 10.0) -> bool:
        if not self.root_check_cmd:
            return False
        out = self.run(self.root_check_cmd, timeout_s)
        return out.exit_code == 0 and out.stdout.strip() == self.root_check_expect.strip()

    def _close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            except OSError:
                pass
        if self._pump_thread is not None:
            self._pump_thread.join(timeout=1)
            self._pump_thread = None
        if proc.stdout is not None:
            try:
                proc.stdout.close()
            except OSError:
                pass

    def close(self) -> None:
        self._close()


_INTERACTIVE_COMMAND_RE = re.compile(
    r"(?<![\w/-])(?:su|sudo|passwd|ssh|scp|sftp|chsh|chfn|newgrp|gpasswd)(?![\w-])")
# A command that supplies its own stdin (a pipe, an input redirect, or sudo -S
# reading the password from stdin) must NOT get </dev/null appended, that
# would cut the input and break e.g. `echo pw | sudo -S cat /root/flag.txt`.
_HAS_OWN_STDIN_RE = re.compile(r"[|<]|(?<![\w-])-S(?![\w-])")


def _make_noninteractive(command: str) -> str:
    """Prevent common interactive tools from consuming the persistent shell.

    This does not deny the command or decide whether it is useful. It only
    gives stdin EOF, so a mistaken interactive attempt fails quickly and its
    real output is returned to the model for adaptation.
    """
    if _HAS_OWN_STDIN_RE.search(command):
        return command
    if _INTERACTIVE_COMMAND_RE.search(command):
        return f"{command.rstrip()} </dev/null"
    return command


class MockTarget:
    """In-process fake decoy for tests. A script maps exact commands to output;
    root status requires explicit UID 0 evidence. No Docker, no network."""

    def __init__(self, root_flag: str = "FLAG{", script: dict | None = None):
        self.root_flag = root_flag
        self.script = script or {}
        self._rooted = False

    def reset(self) -> None:
        self._rooted = False

    def run(self, command: str, timeout_s: float) -> CmdResult:
        if command in self.script:
            out = self.script[command]
            if re.search(r"(?:^|\n)(?:uid=0\b|euid=0\b|0)(?:\n|$)",
                         out, re.IGNORECASE):
                self._rooted = True
            return CmdResult(out, "", 0)
        return CmdResult(f"ran: {command}", "", 0)

    def is_rooted(self) -> bool:
        return self._rooted

    def close(self) -> None:
        pass
