"""LLM clients.

OllamaClient talks to a local Ollama server (one 7 to 8B model at a time).
MockLLM replays a policy function so the loop can be tested without a GPU.
Both expose chat(messages) -> ChatReply with token counts, so the loop tracks
the token budget the same way for real and mock runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class ChatReply:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class OllamaClient:
    """Thin wrapper over the ollama Python client. The dependency is imported
    lazily so mock runs and the smoke test need nothing installed."""

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
            model=self.model,
            messages=messages,
            options={"temperature": self.temperature},
        )
        content = resp.get("message", {}).get("content", "")
        return ChatReply(
            content=content,
            prompt_tokens=int(resp.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(resp.get("eval_count", 0) or 0),
        )


class MockLLM:
    """Drives the loop from a policy: policy(messages) -> raw reply string.

    Used by the smoke test. Token counts are rough estimates so budgets behave.
    """

    def __init__(self, policy: Callable[[list[dict]], str]):
        self.policy = policy

    def chat(self, messages: list[dict]) -> ChatReply:
        content = self.policy(messages)
        prompt_tokens = sum(len(m.get("content", "")) for m in messages) // 4
        completion_tokens = max(1, len(content) // 4)
        return ChatReply(content=content,
                         prompt_tokens=prompt_tokens,
                         completion_tokens=completion_tokens)
