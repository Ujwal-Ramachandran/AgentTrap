"""LLM backends. One small interface, several providers.

Ollama is the primary backend: local, free, one 7 to 8B model at a time.
AnthropicBackend and OpenAIBackend are optional hosted backends (paid, network).
CLIBackend drives a local agent CLI (Claude Code or Codex) in non-interactive
print mode, treating it as a text model. MockLLM replays a policy for tests.

All expose chat(messages) -> ChatReply, so the loop is backend-agnostic. Local
and free first: hosted and CLI backends are optional and clearly marked (see
CLAUDE.md and PRD.md). Every backend imports its dependency lazily, so the mock
path and the smoke tests need nothing installed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import subprocess


@dataclass
class ChatReply:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    turns = [m for m in messages if m.get("role") != "system"]
    return system, turns


def messages_to_prompt(messages: list[dict]) -> str:
    """Flatten a chat history into one prompt string for one-shot CLI backends."""
    parts = [f"[{m.get('role', 'user').upper()}]\n{m.get('content', '')}"
             for m in messages]
    parts.append("[ASSISTANT]")
    return "\n\n".join(parts)


class OllamaBackend:
    """Primary backend: local Ollama server."""

    def __init__(self, model: str, host: str = "http://127.0.0.1:11434",
                 temperature: float = 0.2):
        self.model = model
        self.host = host
        self.temperature = temperature
        self._client = None

    def _lazy(self):
        if self._client is None:
            import ollama
            self._client = ollama.Client(host=self.host)
        return self._client

    def chat(self, messages: list[dict]) -> ChatReply:
        resp = self._lazy().chat(
            model=self.model, messages=messages,
            options={"temperature": self.temperature})
        content = resp.get("message", {}).get("content", "")
        return ChatReply(content=content,
                         prompt_tokens=int(resp.get("prompt_eval_count", 0) or 0),
                         completion_tokens=int(resp.get("eval_count", 0) or 0))


class AnthropicBackend:
    """Optional hosted backend (paid). Needs ANTHROPIC_API_KEY in the environment.
    Good fit for the stronger-attacker honesty check (use a stronger model)."""

    def __init__(self, model: str = "claude-haiku-5-5", temperature: float = 0.2,
                 max_tokens: int = 1024):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None

    def _lazy(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def chat(self, messages: list[dict]) -> ChatReply:
        system, turns = _split_system(messages)
        resp = self._lazy().messages.create(
            model=self.model, system=system or None, max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": m["role"], "content": m["content"]} for m in turns])
        content = "".join(getattr(b, "text", "") for b in resp.content)
        usage = getattr(resp, "usage", None)
        return ChatReply(content=content,
                         prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
                         completion_tokens=getattr(usage, "output_tokens", 0) or 0)


class OpenAIBackend:
    """Optional hosted backend (paid). Needs OPENAI_API_KEY in the environment."""

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.2):
        self.model = model
        self.temperature = temperature
        self._client = None

    def _lazy(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI()
        return self._client

    def chat(self, messages: list[dict]) -> ChatReply:
        resp = self._lazy().chat.completions.create(
            model=self.model, temperature=self.temperature,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages])
        content = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return ChatReply(content=content,
                         prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                         completion_tokens=getattr(usage, "completion_tokens", 0) or 0)


class CLIBackend:
    """Drives a local agent CLI (Claude Code or Codex) in non-interactive print
    mode, treating it as a text model: the CLI gets the flattened prompt and its
    stdout is the reply. Token counts are not available.

    Caveat: these CLIs are agents with their own tool loops. Print mode keeps
    them to a single text answer, but behavior can vary, so this is a
    convenience path, not the primary. Configure the command per tool, for
    example ["claude", "-p"] or ["codex", "exec"].
    """

    def __init__(self, cmd: list[str], timeout_s: float = 120.0,
                 prompt_stdin: bool = False):
        self.cmd = cmd
        self.timeout_s = timeout_s
        self.prompt_stdin = prompt_stdin

    def chat(self, messages: list[dict]) -> ChatReply:
        prompt = messages_to_prompt(messages)
        try:
            if self.prompt_stdin:
                p = subprocess.run(self.cmd, input=prompt, capture_output=True,
                                   text=True, timeout=self.timeout_s)
            else:
                p = subprocess.run([*self.cmd, prompt], capture_output=True,
                                   text=True, timeout=self.timeout_s)
            return ChatReply(content=(p.stdout or "").strip())
        except subprocess.TimeoutExpired:
            return ChatReply(content="")
        except FileNotFoundError:
            return ChatReply(content=f"[cli backend: {self.cmd[0]} not found]")


class MockLLM:
    """Drives the loop from a policy: policy(messages) -> raw reply string.
    Used by the smoke tests. Token counts are rough estimates so budgets behave."""

    def __init__(self, policy: Callable[[list[dict]], str]):
        self.policy = policy

    def chat(self, messages: list[dict]) -> ChatReply:
        content = self.policy(messages)
        prompt_tokens = sum(len(m.get("content", "")) for m in messages) // 4
        completion_tokens = max(1, len(content) // 4)
        return ChatReply(content=content, prompt_tokens=prompt_tokens,
                         completion_tokens=completion_tokens)


def default_mock_policy() -> Callable[[list[dict]], str]:
    """A tiny scripted attacker for the dependency-free mock backend: a short
    enumeration that ends by conceding. Useful for smoke runs and plumbing demos
    with no model installed."""
    seq = iter(["<cmd>whoami</cmd>", "<cmd>id</cmd>", "<cmd>sudo -l</cmd>",
                "<cmd>ls -la /root</cmd>", "<cmd>sudo cat /root/flag</cmd>",
                "<done>no obvious root path found</done>"])

    def policy(_messages: list[dict]) -> str:
        return next(seq, "<done>stop</done>")

    return policy


def build_backend(config):
    """Construct the backend named by config.backend. Ollama is primary."""
    kind = config.backend
    if kind == "ollama":
        return OllamaBackend(config.model, config.ollama_host, config.temperature)
    if kind == "anthropic":
        return AnthropicBackend(config.model or "claude-haiku-5-5", config.temperature)
    if kind == "openai":
        return OpenAIBackend(config.model or "gpt-4o-mini", config.temperature)
    if kind == "cli":
        return CLIBackend(config.cli_cmd, config.cli_timeout_s, config.cli_prompt_stdin)
    if kind == "mock":
        return MockLLM(default_mock_policy())
    raise ValueError(f"unknown backend: {kind!r}")
