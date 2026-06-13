"""The agent collaboration layer.

``AgentBus`` is the abstract "shared room": agents exchange messages, share
structured context, hand off typed artifacts, and request human approval through
it. ``InMemoryBus`` implements it offline and deterministically; ``BandBus``
(Phase 4) wraps the real Band SDK. Agents depend only on this interface, so the
unverified Band API never leaks into the rest of the system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from trustband.contracts import Decision, DecisionType


class AgentMessage(BaseModel):
    """An envelope on the bus. ``recipient=None`` broadcasts to the room."""

    sender: str
    kind: str
    recipient: str | None = None
    text: str = ""
    artifact_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    """A request for the human gate to approve or decline an artifact."""

    issue_id: str
    summary: str
    artifact_type: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


ApprovalHandler = Callable[[ApprovalRequest], Decision]


def auto_approve(request: ApprovalRequest) -> Decision:
    """Default offline handler: approve everything (stands in for a human)."""
    return Decision(
        issue_id=request.issue_id,
        decision=DecisionType.APPROVE,
        actor="auto",
        rationale="auto-approved (offline default handler)",
    )


class AgentBus(ABC):
    """Abstract collaboration layer shared by all agents."""

    @abstractmethod
    def send(self, message: AgentMessage) -> None:
        """Post a message to the room."""

    @abstractmethod
    def history(self) -> list[AgentMessage]:
        """Return all messages posted so far, in order."""

    @abstractmethod
    def share_context(self, key: str, artifact: BaseModel) -> None:
        """Publish a structured artifact into the shared room state under ``key``."""

    @abstractmethod
    def get_context(self, key: str) -> dict[str, Any] | None:
        """Read a previously shared artifact, or None if absent."""

    @abstractmethod
    def handoff(self, sender: str, recipient: str, artifact: BaseModel) -> None:
        """Hand a typed artifact from one agent to another (shares it + records it)."""

    @abstractmethod
    def request_approval(self, request: ApprovalRequest) -> Decision:
        """Block for a human-in-the-loop decision (or the configured handler)."""


class InMemoryBus(AgentBus):
    """Offline, deterministic implementation of :class:`AgentBus`."""

    def __init__(self, approval_handler: ApprovalHandler | None = None) -> None:
        """Create an empty room.

        Args:
            approval_handler: callback invoked by ``request_approval``; defaults
                to :func:`auto_approve`.
        """
        self._messages: list[AgentMessage] = []
        self._context: dict[str, dict[str, Any]] = {}
        self._approval_handler: ApprovalHandler = approval_handler or auto_approve

    def send(self, message: AgentMessage) -> None:
        """Append a message to the transcript."""
        self._messages.append(message)

    def history(self) -> list[AgentMessage]:
        """Return a copy of the transcript in send order."""
        return list(self._messages)

    def share_context(self, key: str, artifact: BaseModel) -> None:
        """Store the artifact's serialized form under ``key``."""
        self._context[key] = artifact.model_dump()

    def get_context(self, key: str) -> dict[str, Any] | None:
        """Return the stored artifact dict for ``key``, or None."""
        return self._context.get(key)

    def handoff(self, sender: str, recipient: str, artifact: BaseModel) -> None:
        """Share the artifact under its type name and record a handoff message."""
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
        """Record the request, invoke the handler, record and return the decision."""
        self.send(
            AgentMessage(
                sender="orchestrator",
                kind="approval_request",
                text=request.summary,
                artifact_type=request.artifact_type,
                payload=request.payload,
            )
        )
        decision = self._approval_handler(request)
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
