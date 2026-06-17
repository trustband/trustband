"""LLM client abstraction.

Agents depend only on :class:`LLMClient`. ``FakeLLM`` replays canned, structured
responses so the whole pipeline runs offline and deterministically; ``RealLLM``
(wired in Phase 4) will call a real provider. Keeping the boundary here means no
network access or API keys are needed for the offline checkpoints.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, ValidationError

_ModelT = TypeVar("_ModelT", bound=BaseModel)


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


class OpenAILLM(LLMClient):
    """OpenAI-compatible chat client (works with the OpenAI API and compatible proxies).

    Reads ``OPENAI_API_KEY`` and ``OPENAI_BASE_URL`` from the environment, and the
    model from the ``model`` arg or ``TRUSTBAND_MODEL`` (default ``gpt-5.4-high``).
    Uses ``max_completion_tokens`` and omits sampling params, since current GPT-5
    models reject ``max_tokens``/``temperature``. Talks raw HTTP via httpx so proxy
    quirks stay visible (e.g. a null ``content`` raises instead of silently passing).
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_completion_tokens: int = 8000,
        timeout: float = 180.0,
    ) -> None:
        """Validate the key and resolve model/base_url (clear error if the key is absent)."""
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for --llm real (OpenAI mode)")
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - depends on the optional 'live' extra
            raise RuntimeError("httpx not installed; run `uv sync --extra live`") from exc
        self._httpx = httpx
        self._key = key
        self.model = model or os.environ.get("TRUSTBAND_MODEL", "gpt-5.4-high")
        resolved = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.base_url = resolved.rstrip("/")
        self.max_completion_tokens = max_completion_tokens
        self._timeout = timeout

    def complete(self, prompt: str, *, kind: str = "", transport_retries: int = 2) -> str:
        """Call chat-completions and return the message content.

        Retries only genuinely transient *transport* errors (network/TLS blips);
        HTTP 4xx/5xx and empty content fail fast with a clear message. Schema/JSON
        retries live one layer up in :func:`parse_with_retry`, so the two never
        compound into a storm of calls.
        """
        system = _SYSTEM_PROMPTS.get(kind, "Respond only with the requested content.")
        system += _JSON_INSTRUCTION
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": self.max_completion_tokens,
        }
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._key}"}
        last_transport_error: Exception | None = None
        for attempt in range(transport_retries + 1):
            try:
                response = self._httpx.post(
                    url, headers=headers, json=payload, timeout=self._timeout
                )
            except self._httpx.TransportError as exc:  # network/TLS blip — worth retrying
                last_transport_error = exc
                time.sleep(1.5 * (attempt + 1))
                continue
            try:
                response.raise_for_status()
            except self._httpx.HTTPStatusError as exc:  # 4xx/5xx — surface, don't loop
                raise RuntimeError(f"OpenAI-compatible call failed ({kind}): {exc}") from exc
            data = response.json()
            choices = data.get("choices") or []
            content = choices[0].get("message", {}).get("content") if choices else None
            if not content:
                raise RuntimeError(
                    f"OpenAI-compatible response had no content (model={self.model}, kind={kind}); "
                    "try another TRUSTBAND_MODEL (e.g. gpt-5.4-high)"
                )
            return content
        raise RuntimeError(
            f"OpenAI-compatible call failed ({kind}) after {transport_retries + 1} attempts: "
            f"{last_transport_error}"
        )


class BudgetedLLM(LLMClient):
    """Wrap an LLMClient and cap completions per run — a guardrail against runaway cost.

    Real models cost money per call, and a misbehaving agent loop could otherwise burn
    through many large-prompt calls. After ``max_calls`` completions this raises,
    surfacing the runaway instead of silently spending.
    """

    def __init__(self, inner: LLMClient, max_calls: int = 30) -> None:
        """Wrap ``inner``, allowing at most ``max_calls`` completions per run."""
        self._inner = inner
        self._max_calls = max_calls
        self.calls = 0

    def complete(self, prompt: str, *, kind: str = "") -> str:
        """Enforce the call budget, then delegate to the wrapped client."""
        if self.calls >= self._max_calls:
            raise RuntimeError(
                f"LLM call budget exhausted ({self._max_calls} calls); "
                "raise --max-llm-calls if this run legitimately needs more"
            )
        self.calls += 1
        return self._inner.complete(prompt, kind=kind)


def parse_with_retry(
    llm: LLMClient,
    prompt: str,
    kind: str,
    model_cls: type[_ModelT],
    retries: int = 2,
) -> _ModelT:
    """Call the LLM and parse its JSON into ``model_cls``, repairing on failure.

    Real models occasionally emit malformed or schema-violating JSON. On a parse
    or validation error this re-prompts the model with the specific error and asks
    for valid JSON, up to ``retries`` extra attempts. Raises a clear RuntimeError if
    every attempt fails — the error is reported, never silently swallowed.
    """
    current = prompt
    last_error: Exception | None = None
    for _ in range(retries + 1):
        raw = llm.complete(current, kind=kind)
        try:
            return model_cls.model_validate_json(extract_json(raw))
        except (ValidationError, ValueError) as exc:
            last_error = exc
            current = (
                f"{prompt}\n\nYour previous reply could not be parsed as valid "
                f"{model_cls.__name__} JSON: {exc}\nReturn ONLY a single valid JSON object."
            )
    raise RuntimeError(
        f"LLM did not produce valid {model_cls.__name__} JSON "
        f"after {retries + 1} attempts: {last_error}"
    )
