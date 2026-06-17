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
        agent_uuid: str | None = None,
        base_url: str | None = "https://app.band.ai",
        approval_timeout: float = 300.0,
        poll_interval: float = 3.0,
    ) -> None:
        """Validate credentials and build the Band REST client (clear error if absent)."""
        key = api_key or os.environ.get("BAND_API_KEY")
        if not key:
            raise RuntimeError("BAND_API_KEY is required for --bus band; use --bus memory offline")
        self._agent_uuid = agent_uuid or os.environ.get("BAND_AGENT_ID")
        if not self._agent_uuid:
            raise RuntimeError(
                "BAND_AGENT_ID is required for --bus band (agent UUID, used for mentions)"
            )
        try:
            from band.client.rest import (
                ChatMessageRequest,
                ChatMessageRequestMentionsItem,
                RestClient,
            )
        except ImportError as exc:  # pragma: no cover - depends on the optional 'live' extra
            raise RuntimeError("band-sdk not installed; run `uv sync --extra live`") from exc
        self._message_request = ChatMessageRequest
        self._mention_item = ChatMessageRequestMentionsItem
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
        self._mentions: list[Any] | None = None

    def _recipient_mentions(self) -> list[Any]:
        """Mentions for outgoing messages: every room participant except this agent.

        Band rejects messages with no mention and rejects mentioning yourself
        (``cannot_mention_self``), so an agent must @ another participant. Cached after
        the first lookup.
        """
        if self._mentions is None:
            try:
                resp = self._client.agent_api_participants.list_agent_chat_participants(
                    self._chat_id
                )
            except Exception as exc:
                raise RuntimeError(
                    f"cannot read participants of room {self._chat_id} ({exc}); "
                    "is the agent added to this room?"
                ) from exc
            others = [
                pid
                for p in (getattr(resp, "data", None) or [])
                if (pid := getattr(p, "id", None)) and pid != self._agent_uuid
            ]
            if not others:
                raise RuntimeError(
                    "Band requires mentioning another participant, but this room has only the "
                    "agent — add a human (or another agent) to the room"
                )
            self._mentions = [self._mention_item(id=pid) for pid in others]
        return self._mentions

    def _post(self, content: str) -> None:
        """Post a message to the room, mentioning the other participant(s) (Band requires it)."""
        message = self._message_request(content=content, mentions=self._recipient_mentions())
        self._client.agent_api_messages.create_agent_chat_message(self._chat_id, message=message)

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
        """Read the agent's next inbound room message and interpret it as a decision.

        The Band REST shape is ``GetAgentNextMessageResponse.data`` -> ``ChatMessage``
        (``content`` / ``sender_type`` / ``id``). We skip our own and system posts,
        mark the message processed so the queue advances, and return None when there
        is no decisive human message yet — the caller keeps polling until the timeout.
        """
        try:
            result = self._client.agent_api_messages.get_agent_next_message(self._chat_id)
        except Exception:  # transient / no message yet — handled as "nothing to read"
            return None
        message = getattr(result, "data", None)
        if message is None:
            return None
        message_id = getattr(message, "id", None)
        if message_id:
            try:
                self._client.agent_api_messages.mark_agent_message_processed(
                    self._chat_id, message_id
                )
            except Exception:
                pass  # best-effort: advancing the queue is not critical to the decision
        if (getattr(message, "sender_type", "") or "").lower() in {"agent", "system"}:
            return None  # ignore our own / system posts; only a human reply is the gate
        raw = getattr(message, "content", "") or ""
        text = raw.strip().lower()
        if "approve" in text or text in {"y", "yes", "lgtm", "/approve"}:
            decision = DecisionType.APPROVE
        elif "decline" in text or "reject" in text or text in {"n", "no", "/decline"}:
            decision = DecisionType.DECLINE
        else:
            return None
        return Decision(
            issue_id=request.issue_id, decision=decision, actor="human", rationale=raw[:200]
        )
