# TrustBand benchmark

Offline, deterministic run across all bundled showcase scenarios (`uv run trustband bench`).

> **What this measures:** the orchestration and decision logic — the triage gate, the Verifier catching a regression, the Security agent blocking a risky patch, and the revision loop — on scenarios with **canned fixes (FakeLLM)**. The numbers are reproducible but do **not** measure a real model's coding ability. Run with `--llm real` to benchmark that.

## Summary
| metric | value |
|---|---|
| scenarios | 6 |
| correct outcomes | 6/6 (100%) |
| fixes shipped (merged) | 5 |
| bad patches caught by Verifier | 1 |
| regressions prevented | 1 |
| security issues caught | 1 |
| non-actionable filtered | 1 |
| avg revisions to merge | 1.4 |

## Per scenario
| scenario | expected | merged | correct | revisions | verifier_rej | regressions | security_blocks | note |
|---|---|---|---|---|---|---|---|---|
| discount | True | True | yes | 1 | 0 | 0 | 0 | straightforward logic bug, clean one-shot fix |
| none_guard | True | True | yes | 1 | 0 | 0 | 0 | different bug type: crash on None input |
| regression_trap | True | True | yes | 2 | 1 | 1 | 0 | round-1 patch regresses _total; Verifier catches it, round-2 is clean |
| risky_fix | True | True | yes | 2 | 0 | 0 | 1 | round-1 passes tests but uses eval; Security catches it, round-2 is safe |
| no_test | True | True | yes | 1 | 0 | 0 | 0 | no failing test exists; the Reproducer authors one, then the fix merges |
| non_actionable | False | False | yes | 0 | 0 | 0 | 0 | triage rejects a feature request; the pipeline stops early |
