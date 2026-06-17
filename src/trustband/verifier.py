"""The Verifier agent — TrustBand's differentiator.

It does not ask an LLM whether a patch is good. It runs the target suite before
and after the patch in isolation, then judges on evidence: did the target
test(s) go green, did anything previously-green regress, is the whole suite
green? The output is a structured :class:`VerdictReport` that gates human
approval. ``judge`` is a pure function of the two runs, so the decision logic is
deterministically testable without spawning a subprocess.
"""

from __future__ import annotations

from pathlib import Path

from trustband.contracts import (
    AssertionResult,
    Issue,
    Patch,
    SuiteResult,
    Verdict,
    VerdictReport,
)
from trustband.runner import run_pytest

VerifierScope = str


def _matches(target: str, nodeid: str) -> bool:
    """True if a (possibly short) target test name refers to this node id.

    Matches an exact node id, a ``::<target>`` suffix, or an equal final segment —
    but not a loose substring, so ``test_add`` no longer matches ``test_addition``.
    """
    return target == nodeid or nodeid.endswith(f"::{target}") or nodeid.split("::")[-1] == target


def judge(
    issue: Issue,
    patch: Patch,
    baseline: SuiteResult,
    after: SuiteResult,
    target_tests: list[str] | None = None,
    *,
    scope_mode: VerifierScope = "full",
    selected_tests: list[str] | None = None,
    full_suite_run: bool = True,
    scope_reason: str = "full suite",
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
    patch_nonempty = bool(patch.touched_paths)

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
            detail=f"files={patch.touched_paths}",
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
        touched_files=patch.touched_paths,
        scope_mode=scope_mode,
        selected_tests=selected_tests or [],
        full_suite_run=full_suite_run,
        scope_reason=scope_reason,
        assertions=assertions,
        reasons=reasons,
        baseline=baseline,
        after=after,
    )


def _select_targets(target_tests: list[str] | None) -> list[str]:
    """Return pytest targets for affected-scope execution."""
    return list(target_tests or [])


def _needs_full_suite(
    patch: Patch,
    selected_tests: list[str],
    subset_after: SuiteResult,
) -> tuple[bool, str]:
    """Decide whether affected-scope evidence needs a full-suite fallback."""
    if not selected_tests:
        return True, "no affected tests selected"
    if not subset_after.all_green:
        return True, "selected tests did not pass"
    source_paths = [path for path in patch.touched_paths if not Path(path).name.startswith("test_")]
    if source_paths:
        return True, "source file change needs full regression check"
    return False, "selected tests passed"


def verify(
    issue: Issue,
    patch: Patch,
    target_tests: list[str] | None = None,
    scaffold: Patch | None = None,
    baseline: SuiteResult | None = None,
    verifier_scope: VerifierScope = "full",
) -> VerdictReport:
    """Run baseline + post-patch suites on the issue's repo and judge the patch.

    ``scaffold`` (e.g. an authored failing test) is applied to both runs. A
    precomputed ``baseline`` can be passed to avoid re-running it every revision.
    """
    if baseline is None:
        baseline = run_pytest(issue.repo_path, scaffold=scaffold)
    if verifier_scope == "affected":
        selected_tests = _select_targets(target_tests)
        subset_after = run_pytest(issue.repo_path, patch, scaffold=scaffold, targets=selected_tests)
        needs_full, reason = _needs_full_suite(patch, selected_tests, subset_after)
        if not needs_full:
            return judge(
                issue,
                patch,
                baseline,
                subset_after,
                target_tests,
                scope_mode=verifier_scope,
                selected_tests=selected_tests,
                full_suite_run=False,
                scope_reason=reason,
            )
        after = run_pytest(issue.repo_path, patch, scaffold=scaffold)
        return judge(
            issue,
            patch,
            baseline,
            after,
            target_tests,
            scope_mode=verifier_scope,
            selected_tests=selected_tests,
            full_suite_run=True,
            scope_reason=reason,
        )
    after = run_pytest(issue.repo_path, patch, scaffold=scaffold)
    return judge(
        issue,
        patch,
        baseline,
        after,
        target_tests,
        scope_mode=verifier_scope,
        selected_tests=[],
        full_suite_run=True,
        scope_reason="full suite requested",
    )
