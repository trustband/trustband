"""Phase 6.4 — the benchmark runs all scenarios and reports correct metrics."""

from trustband.benchmark import render_report, run_benchmark
from trustband.scenarios import SCENARIOS


def test_benchmark_outcomes_all_correct(tmp_path):
    report = run_benchmark(artifacts_dir=str(tmp_path / "bench"))
    assert report.total == len(SCENARIOS)
    assert report.correct == report.total  # every scenario reached its expected outcome
    assert report.merged == 5  # 5 actionable bugs fixed; non_actionable filtered
    assert report.bad_patches_caught >= 1  # regression_trap
    assert report.regressions_prevented >= 1
    assert report.security_issues_caught >= 1  # risky_fix
    assert report.nonactionable_filtered >= 1


def test_render_report_contains_tables(tmp_path):
    report = run_benchmark(artifacts_dir=str(tmp_path / "bench"))
    markdown = render_report(report)
    assert "# TrustBand benchmark" in markdown
    assert "## Summary" in markdown
    assert "regression_trap" in markdown
