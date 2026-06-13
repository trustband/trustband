"""LLM client abstraction.

Agents depend only on :class:`LLMClient`. ``FakeLLM`` replays canned, structured
responses so the whole pipeline runs offline and deterministically; ``RealLLM``
(wired in Phase 4) will call a real provider. Keeping the boundary here means no
network access or API keys are needed for the offline checkpoints.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


def extract_json(text: str) -> str:
    """Return the JSON payload from a model response, tolerating ```json fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


class LLMClient(ABC):
    """Minimal text-completion interface used by the agents."""

    @abstractmethod
    def complete(self, prompt: str, *, kind: str = "") -> str:
        """Return a completion for ``prompt``. ``kind`` hints the expected artifact."""


class FakeLLM(LLMClient):
    """Deterministic client that replays canned responses keyed by ``kind``.

    A response may be a single string or a list of strings. A list is consumed
    by call order (1st call -> [0], 2nd -> [1], clamped to the last), which lets
    a scenario return a flawed patch on round 1 and a clean one on round 2.
    """

    def __init__(self, responses: dict[str, str | list[str]], default: str = "{}") -> None:
        """Store the canned responses and an optional default for unknown kinds."""
        self._responses = dict(responses)
        self._default = default
        self.calls: list[tuple[str, str]] = []
        self._counts: dict[str, int] = {}

    def complete(self, prompt: str, *, kind: str = "") -> str:
        """Record the call and return the canned response for ``kind`` by call order."""
        self.calls.append((kind, prompt))
        index = self._counts.get(kind, 0)
        self._counts[kind] = index + 1
        value = self._responses.get(kind, self._default)
        if isinstance(value, list):
            return value[min(index, len(value) - 1)] if value else self._default
        return value


_SYSTEM_PROMPTS = {
    "triage": "You are a triage agent classifying software issues.",
    "plan": "You are a senior engineer planning a bug fix.",
    "code": "You are a coding agent producing a minimal, correct patch.",
    "review": "You are a rigorous code reviewer.",
}
_JSON_INSTRUCTION = (
    " Respond with a single valid JSON object matching the requested schema and nothing "
    "else — no prose, no markdown code fences."
)


class RealLLM(LLMClient):
    """Real client backed by the Anthropic Messages API (Claude).

    Used only in live mode (``--llm real``); the offline pipeline uses
    :class:`FakeLLM`. The API key and the ``anthropic`` SDK are resolved lazily so
    importing this module never requires either. Defaults to ``claude-opus-4-8``;
    sampling parameters are omitted because they are rejected on current models.
    """

    def __init__(
        self,
        model: str = "claude-opus-4-8",
        api_key: str | None = None,
        max_tokens: int = 16000,
    ) -> None:
        """Validate the key and build the Anthropic client (clear error if absent)."""
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for --llm real (use --llm fake)")
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on the optional 'live' extra
            raise RuntimeError("anthropic SDK not installed; run `uv sync --extra live`") from exc
        self._anthropic = anthropic
        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=key)

    def complete(self, prompt: str, *, kind: str = "") -> str:
        """Call Claude and return the concatenated text blocks of the response."""
        system = _SYSTEM_PROMPTS.get(kind, "Respond only with the requested content.")
        system += _JSON_INSTRUCTION
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except self._anthropic.APIError as exc:  # pragma: no cover - needs a live key
            raise RuntimeError(f"Anthropic API call failed ({kind}): {exc}") from exc
        return "".join(block.text for block in response.content if block.type == "text")
