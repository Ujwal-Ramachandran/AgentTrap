"""Targets: how the agent runs a command against the decoy.

Target is the seam between Ujwal's agent and the decoy host owned by Bhageerath
and Dan (see TASKS.md). DockerExecTarget keeps one persistent shell session
inside the decoy (docker exec -i ... bash), so the working directory, environment,
and any privilege the agent gains (for example after a sudo escalation) carry
across commands. MockTarget is an in-process fake for tests.

No network egress is needed: the agent drives the shell over docker's stdio.

Portability note: the shell is driven in binary mode (bufsize=0, bytes in and
out) and decoded with errors="replace". That sidesteps both Windows pipe bugs
at the source: no text-mode CRLF translation corrupts the commands we send, and
the container's UTF-8 output never trips cp1252 decoding.
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
        self._pump_thread: threading.Thread | None = None
        self._start_error = ""
        self._q: queue.Queue = queue.Queue()

    def _pump(self, proc: subprocess.Popen) -> None:
        try:
            while True:
                line = proc.stdout.readline()   # type: ignore[union-attr]
                if line == b"":
                    break
                self._q.put(line)
        except OSError:
            # The pipe can be invalidated while the process is being stopped.
            pass
        finally:
            self._q.put(None)                   # EOF sentinel

    def _start_shell(self) -> bool:
        self._close()
        self._q = queue.Queue()
        self._start_error = ""
        try:
            # Binary mode: we write bytes with a clean "\n" and decode output
            # ourselves, so no OS-specific newline translation or codec applies.
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
        if self.reset_each_run and self.reset_cmd:
            subprocess.run(self.reset_cmd, shell=True, capture_output=True, text=True)
        self._start_shell()

    def run(self, command: str, timeout_s: float) -> CmdResult:
        if self._proc is None and not self._start_shell():
            detail = f": {self._start_error}" if self._start_error else ""
            return CmdResult("", f"docker not found or shell failed to start{detail}", None)

        # An interactive root shell (sudo -i/-s, su without -c) cannot work over
        # this non-interactive pipe: it swallows the next command as its own
        # input and returns a confusing 127. Tell the agent plainly so it runs a
        # single command instead of looping on it. Neutral: reveals no method.
        if _is_interactive_shell(command):
            return CmdResult(
                "", "interactive shell not available: this shell is "
                "non-interactive (commands are piped in). Run a single command "
                "instead of opening an interactive root shell.", 2)

        sentinel = f"__ATDONE_{uuid.uuid4().hex[:8]}__"
        command_to_run = _make_noninteractive(command)
        try:
            # rstrip any CR/LF the command carried in, then send a clean LF.
            command_bytes = (command_to_run.rstrip("\r\n") + "\n").encode("utf-8")
            sentinel_bytes = (
                f"printf '%s%d\\n' {sentinel} $?\n".encode("ascii"))
            self._proc.stdin.write(command_bytes)                    # type: ignore[union-attr]
            self._proc.stdin.write(sentinel_bytes)                   # type: ignore[union-attr]
            self._proc.stdin.flush()                                 # type: ignore[union-attr]
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._close()
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
            text_line = line.decode("utf-8", errors="replace")
            if sentinel in text_line:
                try:
                    rc = int(text_line.strip().split(sentinel, 1)[1])
                except (ValueError, IndexError):
                    rc = None
                return CmdResult("".join(lines), "", rc)
            lines.append(text_line)

    def is_rooted(self) -> bool:
        if not self.root_check_cmd:
            return False
        out = self.run(self.root_check_cmd, 10)
        # Match a whole output line, not a loose substring: expect "0" must not
        # be satisfied by "uid=1000" or stray output (the false-positive-root bug).
        return self.root_check_expect in [ln.strip() for ln in out.stdout.splitlines()]

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
    r"(?<![\w/-])(?:su|sudo|passwd|ssh|scp|sftp)(?![\w-])")
# Signals that the command already supplies its own stdin: a pipe, an input
# redirect / here-doc / here-string, or sudo's -S (read password from stdin).
_HAS_OWN_STDIN_RE = re.compile(r"[|<]|(?<![\w-])-S(?![\w-])")


# An interactive root shell opened over the pipe (sudo -i / sudo -s, or su
# without -c) breaks the sentinel framing and returns a bare 127. Detect it so
# run() can return a clear message instead. The -i/-s must belong to sudo (same
# command segment), so `grep -i x | sudo -S cat` is not misread.
_SUDO_SHELL_RE = re.compile(r"\bsudo\b[^|;&\n]*(?<!\S)-(?:i|s)(?!\S)")
_SU_RE = re.compile(r"\bsu\b(?![\w-])")


def _is_interactive_shell(command: str) -> bool:
    if _SUDO_SHELL_RE.search(command):
        return True
    if _SU_RE.search(command) and "-c" not in command:
        return True
    return False


def _make_noninteractive(command: str) -> str:
    """Prevent common interactive tools from consuming the persistent shell.

    This does not deny the command or decide whether it is useful. It only
    gives stdin EOF, so a mistaken interactive attempt fails quickly and its
    real output is returned to the model for adaptation.

    It must NOT touch a command that already feeds its own stdin, for example
    `echo pw | sudo -S cat /root/flag.txt` or `sudo -S cmd <<< pw`; appending
    `</dev/null` there would cut off the password and break a legitimate
    escalation, so such commands are left exactly as written.
    """
    if _HAS_OWN_STDIN_RE.search(command):
        return command
    if _INTERACTIVE_COMMAND_RE.search(command):
        return f"{command.rstrip()} </dev/null"
    return command


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

    def close(self) -> None:
        pass
