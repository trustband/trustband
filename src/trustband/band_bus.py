"""Live Band implementation of :class:`AgentBus` over the band-sdk REST API (band==1.0.0).

This maps the four AgentBus primitives onto a real Band room (``chat_id``) using
``RestClient.agent_api_messages``: every ``send`` / ``handoff`` / ``share_context``
posts a message to the room, and ``request_approval`` posts a request then polls the
room for a human reply. The offline pipeline never imports this module, so band-sdk
stays an optional dependency (``uv sync --extra live``).

Live round-trips require ``BAND_API_KEY`` and a real room; they run only under the
``integration`` marker. The decision-parsing in ``_read_decision`` is written against
the SDK's response shape but is pending live verification — see docs/band-findings.md.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from pydantic import BaseModel

from trustband.bus import AgentBus, AgentMessage, ApprovalRequest
from trustband.contracts import Decision, DecisionType


class BandBus(AgentBus):
    """Collaboration layer backed by a real Band room."""

    def __init__(
        self,
        chat_id: str,
        agent_id: str = "orchestrator",
        api_key: str | None = None,
        base_url: str | None = "https://app.band.ai",
        approval_timeout: float = 300.0,
        poll_interval: float = 3.0,
    ) -> None:
        """Validate the key and build the Band REST client (clear error if absent)."""
        key = api_key or os.environ.get("BAND_API_KEY")
        if not key:
            raise RuntimeError("BAND_API_KEY is required for --bus band; use --bus memory offline")
        try:
            from band.client.rest import ChatMessageRequest, RestClient
        except ImportError as exc:  # pragma: no cover - depends on the optional 'live' extra
            raise RuntimeError("band-sdk not installed; run `uv sync --extra live`") from exc
        self._message_request = ChatMessageRequest
        if base_url:
            self._client = RestClient(api_key=key, base_url=base_url)
        else:
            self._client = RestClient(api_key=key)
        self._chat_id = chat_id
        self._agent_id = agent_id
        self._approval_timeout = approval_timeout
        self._poll_interval = poll_interval
        self._messages: list[AgentMessage] = []
        self._context: dict[str, dict[str, Any]] = {}

    def _post(self, content: str) -> None:
        """Post a message to the Band room."""
        self._client.agent_api_messages.create_agent_chat_message(
            self._chat_id, message=self._message_request(content=content)
        )

    def send(self, message: AgentMessage) -> None:
        """Mirror the message locally and post it to the room."""
        self._messages.append(message)
        self._post(message.model_dump_json())

    def history(self) -> list[AgentMessage]:
        """Return the locally mirrored transcript of what this bus sent."""
        return list(self._messages)

    def share_context(self, key: str, artifact: BaseModel) -> None:
        """Store the artifact locally and publish it to the room as structured context."""
        self._context[key] = artifact.model_dump()
        envelope = {"trustband_kind": "context", "key": key, "artifact": self._context[key]}
        self._post(json.dumps(envelope))

    def get_context(self, key: str) -> dict[str, Any] | None:
        """Return a previously shared artifact dict, or None."""
        return self._context.get(key)

    def handoff(self, sender: str, recipient: str, artifact: BaseModel) -> None:
        """Share the artifact under its type name and post a handoff message."""
        artifact_type = type(artifact).__name__
        self.share_context(artifact_type, artifact)
        self.send(
            AgentMessage(
                sender=sender,
                recipient=recipient,
                kind="handoff",
                text=f"handoff {artifact_type}",
                artifact_type=artifact_type,
                payload=artifact.model_dump(),
            )
        )

    def request_approval(self, request: ApprovalRequest) -> Decision:
        """Post an approval request to the room and poll for a human decision."""
        self.send(
            AgentMessage(
                sender=self._agent_id,
                kind="approval_request",
                text=request.summary,
                artifact_type=request.artifact_type,
                payload=request.payload,
            )
        )
        decision = self._poll_for_decision(request)
        self.send(
            AgentMessage(
                sender=decision.actor,
                kind="approval_response",
                text=decision.rationale,
                artifact_type="Decision",
                payload=decision.model_dump(),
            )
        )
        return decision

    def _poll_for_decision(self, request: ApprovalRequest) -> Decision:
        """Poll the room until a human approves/declines, or time out (declining)."""
        deadline = time.monotonic() + self._approval_timeout
        while time.monotonic() < deadline:
            decision = self._read_decision(request)
            if decision is not None:
                return decision
            time.sleep(self._poll_interval)
        return Decision(
            issue_id=request.issue_id,
            decision=DecisionType.DECLINE,
            actor="human",
            rationale="approval timed out with no response",
        )

    def _read_decision(self, request: ApprovalRequest) -> Decision | None:
        """Read the next room message and interpret it as an approval decision, if any.

        Returns None when no decisive message is available yet (handled, not swallowed):
        the caller keeps polling until the timeout.
        """
        try:
            result = self._client.agent_api_messages.get_agent_next_message(self._chat_id)
        except Exception:  # network blip / no message yet — treat as "nothing to read"
            return None
        message = getattr(result, "message", None) or result
        content = getattr(message, "content", None)
        if not content:
            return None
        text = str(content).strip().lower()
        if "approve" in text or text in {"y", "yes", "lgtm", "/approve"}:
            return Decision(
                issue_id=request.issue_id,
                decision=DecisionType.APPROVE,
                actor="human",
                rationale=str(content)[:200],
            )
        if "decline" in text or "reject" in text or text in {"n", "no", "/decline"}:
            return Decision(
                issue_id=request.issue_id,
                decision=DecisionType.DECLINE,
                actor="human",
                rationale=str(content)[:200],
            )
        return None
