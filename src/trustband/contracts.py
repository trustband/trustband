"""Structured-context contracts exchanged between agents over the bus.

These Pydantic models are both the artifacts handed off inside the Band room
(Issue -> FixPlan -> Patch -> VerdictReport -> ReviewReport -> Decision) and the
objective surface the Verifier asserts against. Keeping them typed makes the
whole pipeline deterministically testable offline.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """Review finding severity, mirroring Band's plan/review taxonomy."""

    CRITICAL = "critical"
    RISK = "risk"
    GAP = "gap"
    SUGGESTION = "suggestion"


class Verdict(StrEnum):
    """The Verifier's overall judgement on a patch."""

    TRUSTWORTHY = "trustworthy"
    REJECTED = "rejected"


class ReviewStatus(StrEnum):
    """Reviewer outcome; ``REQUEST_CHANGES`` loops back to the Coder."""

    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"


class DecisionType(StrEnum):
    """Human (or auto) gate decision."""

    APPROVE = "approve"
    DECLINE = "decline"


class Issue(BaseModel):
    """A bug/issue to fix, pointing at a target repository."""

    id: str
    title: str
    description: str = ""
    repo_path: str
    failing_test: str | None = None
    labels: list[str] = Field(default_factory=list)


class FixPlan(BaseModel):
    """Planner output: root-cause hypothesis and acceptance criteria."""

    issue_id: str
    root_cause: str
    files_to_touch: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    test_strategy: str = ""
    notes: str = ""


class FileChange(BaseModel):
    """A single file fully replaced by ``new_content`` (repo-relative path)."""

    path: str
    new_content: str


class Patch(BaseModel):
    """Coder output: a set of file changes for one issue, possibly revised."""

    issue_id: str
    summary: str = ""
    changes: list[FileChange] = Field(default_factory=list)
    revision: int = 1


class SuiteResult(BaseModel):
    """Parsed result of one pytest run over the target repo."""

    passed: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    returncode: int = 0
    duration_s: float = 0.0

    @property
    def all_green(self) -> bool:
        """True when no test failed or errored."""
        return not self.failed and not self.errors


class AssertionResult(BaseModel):
    """One named trajectory assertion the Verifier evaluated."""

    name: str
    passed: bool
    detail: str = ""


class VerdictReport(BaseModel):
    """Verifier output — the differentiator. Evidence that the patch earns the merge."""

    issue_id: str
    verdict: Verdict
    target_tests: list[str] = Field(default_factory=list)
    newly_passing: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    still_failing: list[str] = Field(default_factory=list)
    touched_files: list[str] = Field(default_factory=list)
    assertions: list[AssertionResult] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    baseline: SuiteResult | None = None
    after: SuiteResult | None = None

    @property
    def trustworthy(self) -> bool:
        """True when the verdict is trustworthy."""
        return self.verdict == Verdict.TRUSTWORTHY


class Finding(BaseModel):
    """A single reviewer finding."""

    severity: Severity
    message: str
    path: str | None = None
    line: int | None = None


class ReviewReport(BaseModel):
    """Reviewer output: status plus categorized findings."""

    issue_id: str
    status: ReviewStatus
    findings: list[Finding] = Field(default_factory=list)
    summary: str = ""

    @property
    def approved(self) -> bool:
        """True when the reviewer approved (no changes requested)."""
        return self.status == ReviewStatus.APPROVE


class Decision(BaseModel):
    """Human-in-the-loop gate decision on whether to open/merge the PR."""

    issue_id: str
    decision: DecisionType
    actor: str = "human"
    rationale: str = ""

    @property
    def approved(self) -> bool:
        """True when the gate approved."""
        return self.decision == DecisionType.APPROVE


class IssueCategory(StrEnum):
    """How the Triage agent classifies an incoming issue."""

    BUG = "bug"
    FEATURE = "feature"
    QUESTION = "question"
    FLAKY = "flaky"


class TriageReport(BaseModel):
    """Triage output: whether the issue is actionable and how to target it."""

    issue_id: str
    actionable: bool
    category: IssueCategory = IssueCategory.BUG
    severity: Severity = Severity.RISK
    target_tests: list[str] = Field(default_factory=list)
    rationale: str = ""


class SecurityReport(BaseModel):
    """Security/risk review of a patch (distinct from functional review)."""

    issue_id: str
    findings: list[Finding] = Field(default_factory=list)
    summary: str = ""

    @property
    def clean(self) -> bool:
        """True when no finding is CRITICAL (a critical finding blocks the merge)."""
        return not any(finding.severity == Severity.CRITICAL for finding in self.findings)


class ReproReport(BaseModel):
    """Reproducer output: whether the bug reproduces, and on which test(s).

    ``authored_test`` is set when the Reproducer had to write a failing test (no
    pre-existing one); that test becomes a scaffold applied to every verifier run.
    """

    issue_id: str
    reproduced: bool
    target_tests: list[str] = Field(default_factory=list)
    authored_test: Patch | None = None
    detail: str = ""
