"""LLM client abstraction.

Agents depend only on :class:`LLMClient`. ``FakeLLM`` replays canned, structured
responses so the whole pipeline runs offline and deterministically; ``RealLLM``
(wired in Phase 4) will call a real provider. Keeping the boundary here means no
network access or API keys are needed for the offline checkpoints.
"""

from __future__ import annotations

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


class RealLLM(LLMClient):
    """Skeleton real client. Wired to a provider in Phase 4 (needs API keys)."""

    def __init__(
        self, provider: str = "anthropic", model: str | None = None, api_key: str | None = None
    ) -> None:
        """Capture provider settings; no network call happens until Phase 4."""
        self.provider = provider
        self.model = model
        self._api_key = api_key

    def complete(self, prompt: str, *, kind: str = "") -> str:
        """Not yet implemented — the offline pipeline uses :class:`FakeLLM`."""
        raise NotImplementedError(
            "RealLLM is wired in Phase 4 and requires provider API keys; "
            "use FakeLLM (--llm fake) for the offline pipeline."
        )
