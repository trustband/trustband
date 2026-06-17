"""Remote agent client shims used to make agents real cross-process peers."""

from __future__ import annotations

from trustband.bus import AgentBus, AgentMessage
from trustband.contracts import FixPlan, Issue, Patch


class RemoteCoder:
    """Coder-compatible client that delegates patch creation to a remote peer."""

    name = "remote-coder"

    def __init__(self, bus: AgentBus, peer: str = "coder") -> None:
        """Bind the bus and remote peer name."""
        self.bus = bus
        self.peer = peer

    def code(self, issue: Issue, plan: FixPlan, prior_review=None) -> Patch:
        """Request a remote coder patch through the shared bus context."""
        payload = {
            "issue": issue.model_dump(),
            "plan": plan.model_dump(),
            "prior_review": prior_review.model_dump() if prior_review else None,
        }
        self.bus.send(
            AgentMessage(
                sender="orchestrator",
                recipient=self.peer,
                kind="remote_task",
                text=f"remote code task for {issue.id}",
                artifact_type="RemoteCodeTask",
                payload=payload,
            )
        )
        raw = self.bus.get_context("RemotePatch")
        if raw is None:
            raise RuntimeError(f"remote coder peer '{self.peer}' did not return RemotePatch")
        patch = Patch.model_validate(raw)
        patch.issue_id = issue.id
        self.bus.handoff(self.peer, "verifier", patch)
        return patch
