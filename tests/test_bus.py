"""Phase 1.2 — InMemoryBus preserves order, retains context, handoffs, and approval."""

from trustband.bus import AgentMessage, ApprovalRequest, InMemoryBus
from trustband.contracts import Decision, DecisionType, FixPlan


def test_message_ordering():
    bus = InMemoryBus()
    for i in range(3):
        bus.send(AgentMessage(sender="planner", kind="note", text=f"msg{i}"))
    texts = [m.text for m in bus.history()]
    assert texts == ["msg0", "msg1", "msg2"]


def test_share_and_get_context():
    bus = InMemoryBus()
    plan = FixPlan(issue_id="BUG-1", root_cause="flat subtraction")
    bus.share_context("FixPlan", plan)
    stored = bus.get_context("FixPlan")
    assert stored is not None
    assert stored["root_cause"] == "flat subtraction"
    assert bus.get_context("missing") is None


def test_handoff_shares_artifact_and_records_message():
    bus = InMemoryBus()
    plan = FixPlan(issue_id="BUG-1", root_cause="flat subtraction")
    bus.handoff(sender="planner", recipient="coder", artifact=plan)

    # Artifact is retrievable from shared context by its type name.
    assert bus.get_context("FixPlan")["root_cause"] == "flat subtraction"

    # A handoff message was recorded with the right metadata.
    handoffs = [m for m in bus.history() if m.kind == "handoff"]
    assert len(handoffs) == 1
    assert handoffs[0].sender == "planner"
    assert handoffs[0].recipient == "coder"
    assert handoffs[0].artifact_type == "FixPlan"


def test_request_approval_invokes_handler_and_records_trail():
    captured = {}

    def decline_handler(request: ApprovalRequest) -> Decision:
        captured["issue_id"] = request.issue_id
        return Decision(
            issue_id=request.issue_id,
            decision=DecisionType.DECLINE,
            actor="reviewer-bot",
            rationale="needs more tests",
        )

    bus = InMemoryBus(approval_handler=decline_handler)
    decision = bus.request_approval(
        ApprovalRequest(issue_id="BUG-1", summary="merge?", artifact_type="Patch")
    )

    assert captured["issue_id"] == "BUG-1"
    assert decision.approved is False
    assert decision.actor == "reviewer-bot"

    kinds = [m.kind for m in bus.history()]
    assert kinds == ["approval_request", "approval_response"]


def test_default_handler_auto_approves():
    bus = InMemoryBus()
    decision = bus.request_approval(ApprovalRequest(issue_id="BUG-1", summary="merge?"))
    assert decision.approved is True
    assert decision.actor == "auto"
