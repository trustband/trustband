"""The Verifier agent — TrustBand's differentiator.

It does not ask an LLM whether a patch is good. It runs the target suite before
and after the patch in isolation, then judges on evidence: did the target
test(s) go green, did anything previously-green regress, is the whole suite
green? The output is a structured :class:`VerdictReport` that gates human
approval. ``judge`` is a pure function of the two runs, so the decision logic is
deterministically testable without spawning a subprocess.
"""

from __future__ import annotations

from trustband.contracts import (
    AssertionResult,
    Issue,
    Patch,
    SuiteResult,
    Verdict,
    VerdictReport,
)
from trustband.runner import run_pytest


def _matches(target: str, nodeid: str) -> bool:
    """True if a (possibly short) target test name refers to this node id."""
    return target == nodeid or nodeid.endswith(f"::{target}") or target in nodeid


def judge(
    issue: Issue,
    patch: Patch,
    baseline: SuiteResult,
    after: SuiteResult,
    target_tests: list[str] | None = None,
) -> VerdictReport:
    """Decide whether ``patch`` earns the merge, given baseline and post-patch runs."""
    base_pass = set(baseline.passed)
    base_red = set(baseline.failed) | set(baseline.errors)
    after_pass = set(after.passed)
    after_red = set(after.failed) | set(after.errors)

    newly_passing = sorted(base_red & after_pass)
    regressions = sorted(base_pass & after_red)
    still_failing = sorted(base_red & after_red)

    if target_tests:
        targets = list(target_tests)
    elif issue.failing_test:
        targets = [issue.failing_test]
    else:
        targets = sorted(base_red)

    def target_green(test: str) -> bool:
        passing = any(_matches(test, nid) for nid in after_pass)
        failing = any(_matches(test, nid) for nid in after_red)
        return passing and not failing

    targets_pass = bool(targets) and all(target_green(test) for test in targets)
    no_regressions = not regressions
    suite_green = after.all_green
    patch_nonempty = bool(patch.changes)

    assertions = [
        AssertionResult(
            name="target_tests_pass", passed=targets_pass, detail=f"targets={targets}"
        ),
        AssertionResult(
            name="no_regressions", passed=no_regressions, detail=f"regressions={regressions}"
        ),
        AssertionResult(
            name="suite_green", passed=suite_green, detail=f"failed={sorted(after_red)}"
        ),
        AssertionResult(
            name="patch_nonempty",
            passed=patch_nonempty,
            detail=f"files={[c.path for c in patch.changes]}",
        ),
    ]

    ok = targets_pass and no_regressions and suite_green and patch_nonempty
    verdict = Verdict.TRUSTWORTHY if ok else Verdict.REJECTED

    reasons: list[str] = []
    reasons.append(
        f"target test(s) pass: {targets}" if targets_pass
        else f"target test(s) NOT all passing: {targets}"
    )
    if regressions:
        reasons.append(f"regressions introduced (green -> red): {regressions}")
    if not suite_green:
        reasons.append(f"suite not green after patch: {sorted(after_red)}")
    if not patch_nonempty:
        reasons.append("patch is empty")

    return VerdictReport(
        issue_id=issue.id,
        verdict=verdict,
        target_tests=targets,
        newly_passing=newly_passing,
        regressions=regressions,
        still_failing=still_failing,
        touched_files=[change.path for change in patch.changes],
        assertions=assertions,
        reasons=reasons,
        baseline=baseline,
        after=after,
    )


def verify(issue: Issue, patch: Patch, target_tests: list[str] | None = None) -> VerdictReport:
    """Run baseline + post-patch suites on the issue's repo and judge the patch."""
    baseline = run_pytest(issue.repo_path)
    after = run_pytest(issue.repo_path, patch)
    return judge(issue, patch, baseline, after, target_tests)
