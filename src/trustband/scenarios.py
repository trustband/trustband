"""Showcase scenario registry: diverse bugs the band handles, with canned FakeLLMs.

Each scenario points at a fixture repo and supplies the deterministic FakeLLM
responses (triage/plan/code/review) the offline pipeline replays. A multi-round
``code`` list drives the revision loop: a flawed round-1 patch, then a clean
round-2 once the Verifier or Security agent pushes back.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from trustband.contracts import (
    FileChange,
    FixPlan,
    Issue,
    IssueCategory,
    Patch,
    ReviewReport,
    ReviewStatus,
    TriageReport,
)
from trustband.demo import make_demo_fake_llm
from trustband.llm import FakeLLM

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

NONE_GUARD_FIX = '''"""Text normalization helper."""


def normalize(text):
    """Return the text trimmed and lowercased; empty string for None."""
    if text is None:
        return ""
    return text.strip().lower()
'''

REGRESSION_BAD = '''"""Stats helpers."""


def _total(numbers):
    """Sum the unique numbers."""
    return sum(set(numbers))


def mean(numbers):
    """Return the arithmetic mean of the numbers."""
    if not numbers:
        return 0
    return _total(numbers) / len(numbers)


def summary(numbers):
    """Return count and total."""
    return {"count": len(numbers), "total": _total(numbers)}
'''

REGRESSION_GOOD = '''"""Stats helpers."""


def _total(numbers):
    """Sum the numbers."""
    return sum(numbers)


def mean(numbers):
    """Return the arithmetic mean of the numbers."""
    if not numbers:
        return 0
    return _total(numbers) / len(numbers)


def summary(numbers):
    """Return count and total."""
    return {"count": len(numbers), "total": _total(numbers)}
'''

RISKY_BAD = '''"""Calc helper."""


def add_one(value):
    """Return value + 1, parsing strings."""
    return eval(str(value)) + 1
'''

RISKY_GOOD = '''"""Calc helper."""


def add_one(value):
    """Return value + 1, parsing numeric strings safely."""
    return int(value) + 1
'''


def _patch_json(path: str, content: str, summary: str) -> str:
    """Serialize a single-file Patch to JSON for a FakeLLM ``code`` response."""
    patch = Patch(
        issue_id="X", summary=summary, changes=[FileChange(path=path, new_content=content)]
    )
    return patch.model_dump_json()


def _make_llm(
    *,
    actionable: bool,
    category: IssueCategory,
    root_cause: str,
    files: list[str],
    code: str | list[str],
    review_summary: str,
) -> FakeLLM:
    """Build a FakeLLM with canned triage/plan/code/review responses."""
    return FakeLLM(
        {
            "triage": TriageReport(
                issue_id="X", actionable=actionable, category=category
            ).model_dump_json(),
            "plan": FixPlan(
                issue_id="X", root_cause=root_cause, files_to_touch=files
            ).model_dump_json(),
            "code": code,
            "review": ReviewReport(
                issue_id="X", status=ReviewStatus.APPROVE, summary=review_summary
            ).model_dump_json(),
        }
    )


def _none_guard_llm() -> FakeLLM:
    return _make_llm(
        actionable=True,
        category=IssueCategory.BUG,
        root_cause="normalize() does not handle None input",
        files=["textutil.py"],
        code=_patch_json("textutil.py", NONE_GUARD_FIX, "guard None input"),
        review_summary="adds a None guard",
    )


def _regression_trap_llm() -> FakeLLM:
    return _make_llm(
        actionable=True,
        category=IssueCategory.BUG,
        root_cause="mean() divides by zero on empty input",
        files=["stats.py"],
        code=[
            _patch_json("stats.py", REGRESSION_BAD, "guard empty input (round 1)"),
            _patch_json("stats.py", REGRESSION_GOOD, "guard empty input, keep _total (round 2)"),
        ],
        review_summary="guards empty input without changing _total",
    )


def _risky_fix_llm() -> FakeLLM:
    return _make_llm(
        actionable=True,
        category=IssueCategory.BUG,
        root_cause="add_one() does not parse string input",
        files=["calc.py"],
        code=[
            _patch_json("calc.py", RISKY_BAD, "parse via eval (round 1)"),
            _patch_json("calc.py", RISKY_GOOD, "parse via int (round 2)"),
        ],
        review_summary="parses numeric strings safely",
    )


def _non_actionable_llm() -> FakeLLM:
    return _make_llm(
        actionable=False,
        category=IssueCategory.FEATURE,
        root_cause="not a bug",
        files=[],
        code=_patch_json("greeter.py", "", "n/a"),
        review_summary="n/a",
    )


@dataclass
class Scenario:
    """One showcase case: a fixture repo plus its deterministic FakeLLM."""

    name: str
    repo: str
    issue_id: str
    failing_test: str | None
    expected_merge: bool
    llm_factory: Callable[[], FakeLLM]
    note: str = ""

    def issue(self) -> Issue:
        """Load the Issue for this scenario from the fixture's ISSUE.md."""
        issue_file = Path(self.repo) / "ISSUE.md"
        text = issue_file.read_text() if issue_file.exists() else ""
        title = next(
            (line.lstrip("# ").strip() for line in text.splitlines() if line.strip()), self.name
        )
        return Issue(
            id=self.issue_id,
            title=title,
            description=text,
            repo_path=self.repo,
            failing_test=self.failing_test,
        )


SCENARIOS: list[Scenario] = [
    Scenario(
        name="discount",
        repo=str(FIXTURES / "buggy_app"),
        issue_id="DISCOUNT-1",
        failing_test="test_percentage_discount",
        expected_merge=True,
        llm_factory=make_demo_fake_llm,
        note="straightforward logic bug, clean one-shot fix",
    ),
    Scenario(
        name="none_guard",
        repo=str(FIXTURES / "none_guard"),
        issue_id="NONE-1",
        failing_test="test_normalize_none_returns_empty",
        expected_merge=True,
        llm_factory=_none_guard_llm,
        note="different bug type: crash on None input",
    ),
    Scenario(
        name="regression_trap",
        repo=str(FIXTURES / "regression_trap"),
        issue_id="STATS-1",
        failing_test="test_mean_empty_is_zero",
        expected_merge=True,
        llm_factory=_regression_trap_llm,
        note="round-1 patch regresses _total; Verifier catches it, round-2 is clean",
    ),
    Scenario(
        name="risky_fix",
        repo=str(FIXTURES / "risky_fix"),
        issue_id="CALC-1",
        failing_test="test_add_one_str",
        expected_merge=True,
        llm_factory=_risky_fix_llm,
        note="round-1 passes tests but uses eval; Security catches it, round-2 is safe",
    ),
    Scenario(
        name="non_actionable",
        repo=str(FIXTURES / "non_actionable"),
        issue_id="Q-1",
        failing_test=None,
        expected_merge=False,
        llm_factory=_non_actionable_llm,
        note="triage rejects a feature request; the pipeline stops early",
    ),
]


def get_scenario(name: str) -> Scenario:
    """Return the scenario with ``name`` or raise KeyError."""
    for scenario in SCENARIOS:
        if scenario.name == name:
            return scenario
    raise KeyError(name)
