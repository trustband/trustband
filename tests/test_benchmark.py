"""Phase 6.4 — the benchmark runs all scenarios and reports correct metrics."""

import json

from trustband.benchmark import render_report, run_benchmark
from trustband.cli import main
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


def test_benchmark_continues_after_scenario_error(tmp_path):
    def broken_llm(_scenario):
        raise RuntimeError("model unavailable")

    report = run_benchmark(
        scenarios=SCENARIOS[:2],
        artifacts_dir=str(tmp_path / "bench"),
        mode="real",
        model="m",
        llm_factory=broken_llm,
    )

    assert report.total == 2
    assert report.correct == 0
    assert all(outcome.status == "error" for outcome in report.outcomes)
    assert "model unavailable" in report.outcomes[0].failure_reason


def test_benchmark_real_mode_accepts_injected_llm(tmp_path):
    def scenario_llm(scenario):
        return scenario.llm_factory()

    report = run_benchmark(
        scenarios=SCENARIOS[:1],
        artifacts_dir=str(tmp_path / "bench"),
        mode="real",
        model="stub-model",
        llm_factory=scenario_llm,
    )

    assert report.mode == "real"
    assert report.model == "stub-model"
    assert report.correct == 1


def test_cli_bench_json_outputs_machine_readable_report(capsys):
    code = main(["bench", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["mode"] == "fake"
    assert payload["total"] == len(SCENARIOS)
    assert payload["correct"] == len(SCENARIOS)
    assert "TrustBand benchmark" not in out


def test_cli_bench_json_with_out_keeps_stdout_clean(tmp_path, capsys):
    out_file = tmp_path / "benchmark.md"
    code = main(["bench", "--json", "--out", str(out_file)])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["mode"] == "fake"
    assert out_file.exists()
