"""Input screening for the hardened agent (Phase B).

When the agent is hardened, each observation (the shell output fed back to the
model) is screened first. PromptGuard2Screen is Meta PromptGuard 2, a small
DeBERTa classifier that flags prompt-injection text; it is expected to catch the
one injection trap (T5.2) and miss the four deception traps, which is the point
of GBR (see PRD.md). NullScreen never flags (plain cells). MockScreen flags a
marker, for tests.

A screen returns a ScreenResult; the loop records screened/flagged per step,
counts guardrail_flags, and withholds flagged input from the model.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScreenResult:
    flagged: bool
    score: float = 0.0
    label: str = ""


class NullScreen:
    def screen(self, text: str) -> ScreenResult:
        return ScreenResult(flagged=False)


class MockScreen:
    """Flags any text containing a marker. For tests only."""

    def __init__(self, marker: str = "IGNORE PREVIOUS INSTRUCTIONS"):
        self.marker = marker.lower()

    def screen(self, text: str) -> ScreenResult:
        hit = self.marker in (text or "").lower()
        return ScreenResult(flagged=hit, score=1.0 if hit else 0.0,
                            label="injection" if hit else "benign")


class PromptGuard2Screen:
    """Meta PromptGuard 2 via transformers. The model is gated on Hugging Face,
    so accept its license and set HF auth before first use. Loaded lazily and
    kept alongside the attacker model (about 90 to 350MB; see ARCHITECTURE.md)."""

    def __init__(self, model_id: str = "meta-llama/Llama-Prompt-Guard-2-86M",
                 threshold: float = 0.5):
        self.model_id = model_id
        self.threshold = threshold
        self._pipe = None

    def _lazy(self):
        if self._pipe is None:
            from transformers import pipeline
            self._pipe = pipeline("text-classification", model=self.model_id,
                                  truncation=True, max_length=512)
        return self._pipe

    def screen(self, text: str) -> ScreenResult:
        if not text:
            return ScreenResult(flagged=False)
        out = self._lazy()(text)[0]
        label = str(out.get("label", "")).lower()
        score = float(out.get("score", 0.0))
        # PromptGuard 2 marks malicious input (label such as "LABEL_1" or "injection").
        is_malicious = ("1" in label) or ("inject" in label) or ("malicious" in label)
        return ScreenResult(flagged=is_malicious and score >= self.threshold,
                            score=score, label=label)


def build_screen(config):
    """Pick the screen for this run. Plain runs always get NullScreen."""
    if not config.hardened or config.screen_kind == "null":
        return NullScreen()
    if config.screen_kind == "mock":
        return MockScreen()
    return PromptGuard2Screen(config.promptguard_model, config.screen_threshold)
