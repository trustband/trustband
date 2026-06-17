"""Phase 3.2 — each agent produces its artifact, hands off, and respects evidence."""

from pathlib import Path

from trustband.agents import Coder, Planner, Reproducer, Reviewer, read_repo_context
from trustband.bus import InMemoryBus
from trustband.contracts import FileChange, Issue, Patch, Verdict, VerdictReport
from trustband.demo import make_demo_fake_llm
from trustband.llm import FakeLLM

FIXTURE = Path(__file__).parent.parent / "fixtures" / "buggy_app"


def _issue() -> Issue:
    return Issue(
        id="BUG-1",
        title="discount",
        repo_path=str(FIXTURE),
        failing_test="test_percentage_discount",
    )


def _dummy_patch() -> Patch:
    return Patch(issue_id="BUG-1", changes=[FileChange(path="pricing.py", new_content="x = 1\n")])


def test_read_repo_context_includes_source():
    context = read_repo_context(FIXTURE)
    assert "def order_total" in context


def test_planner_produces_plan_and_hands_off():
    bus = InMemoryBus()
    plan = Planner(bus, make_demo_fake_llm()).plan(_issue())
    assert plan.issue_id == "BUG-1"
    assert "pricing.py" in plan.files_to_touch
    assert bus.get_context("FixPlan") is not None


def test_coder_produces_fixing_patch():
    bus = InMemoryBus()
    llm = make_demo_fake_llm()
    plan = Planner(bus, llm).plan(_issue())
    patch = Coder(bus, llm).code(_issue(), plan)
    assert patch.changes[0].path == "pricing.py"
    assert "1 - discount_rate" in patch.changes[0].new_content


def test_reviewer_cannot_approve_rejected_verdict():
    bus = InMemoryBus()
    rejected = VerdictReport(
        issue_id="BUG-1", verdict=Verdict.REJECTED, regressions=["test_x"], reasons=["regression"]
    )
    review = Reviewer(bus, make_demo_fake_llm()).review(_issue(), _dummy_patch(), rejected)
    assert review.approved is False


def test_reviewer_approves_when_trustworthy():
    bus = InMemoryBus()
    good = VerdictReport(issue_id="BUG-1", verdict=Verdict.TRUSTWORTHY)
    review = Reviewer(bus, make_demo_fake_llm()).review(_issue(), _dummy_patch(), good)
    assert review.approved is True


def test_reproducer_rejects_trivially_passing_authored_test(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "thing.py").write_text("def broken():\n    return 1\n")
    issue = Issue(id="BUG-1", title="broken", repo_path=str(repo), description="broken")
    patch = Patch(
        issue_id="BUG-1",
        changes=[
            FileChange(
                path="test_thing.py",
                new_content="def test_trivial():\n    assert True\n",
            )
        ],
    )

    report = Reproducer(InMemoryBus(), FakeLLM({"reproduce": patch.model_dump_json()})).run(
        issue, []
    )

    assert report.reproduced is False
    assert report.authored_test is None
    assert "did not fail" in report.detail


def test_reproducer_rejects_authored_test_with_import_error(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "thing.py").write_text("def broken():\n    return 1\n")
    issue = Issue(id="BUG-1", title="broken", repo_path=str(repo), description="broken")
    patch = Patch(
        issue_id="BUG-1",
        changes=[
            FileChange(
                path="test_thing.py",
                new_content="from missing import nope\n\n\ndef test_broken():\n    assert nope()\n",
            )
        ],
    )

    report = Reproducer(InMemoryBus(), FakeLLM({"reproduce": patch.model_dump_json()})).run(
        issue, []
    )

    assert report.reproduced is False
    assert report.target_tests == []
    assert "pytest errors" in report.detail
