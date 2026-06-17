"""Remote agent shims can stand in for local agents in the pipeline."""

from pathlib import Path

import pytest

from trustband.agents import Planner, Reproducer, Reviewer, SecurityReviewer, Triage
from trustband.bus import AgentMessage, InMemoryBus
from trustband.contracts import FileChange, Issue, Patch
from trustband.demo import CORRECT_PRICING, make_demo_fake_llm
from trustband.orchestrator import Orchestrator
from trustband.remote_agent import RemoteCoder

FIXTURE = Path(__file__).parent.parent / "fixtures" / "buggy_app"


class RemotePatchBus(InMemoryBus):
    """In-memory bus that simulates a remote coder peer replying with a Patch."""

    def send(self, message: AgentMessage) -> None:
        """Record the message and synthesize a remote patch for code tasks."""
        super().send(message)
        if message.kind == "remote_task":
            patch = Patch(
                issue_id=message.payload["issue"]["id"],
                summary="remote coder fix",
                changes=[FileChange(path="pricing.py", new_content=CORRECT_PRICING)],
            )
            self.share_context("RemotePatch", patch)


def _issue() -> Issue:
    return Issue(
        id="BUG-1",
        title="percentage discount",
        repo_path=str(FIXTURE),
        failing_test="test_percentage_discount",
    )


def test_remote_coder_can_drive_pipeline(tmp_path):
    bus = RemotePatchBus()
    llm = make_demo_fake_llm()
    orchestrator = Orchestrator(
        bus,
        Triage(bus, llm),
        Reproducer(bus, llm),
        Planner(bus, llm),
        RemoteCoder(bus),
        SecurityReviewer(bus),
        Reviewer(bus, llm),
        artifacts_dir=str(tmp_path / "artifacts"),
    )

    result = orchestrator.run(_issue())

    assert result.merged is True
    assert any(message.kind == "remote_task" for message in bus.history())
    assert bus.get_context("RemotePatch") is not None


def test_remote_coder_fails_when_peer_does_not_reply():
    bus = InMemoryBus()
    plan = Planner(bus, make_demo_fake_llm()).plan(_issue())

    with pytest.raises(RuntimeError, match="did not return RemotePatch"):
        RemoteCoder(bus).code(_issue(), plan)
