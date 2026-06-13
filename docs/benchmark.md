# TrustBand benchmark

Offline, deterministic run across all bundled showcase scenarios (`uv run trustband bench`).

## Summary
| metric | value |
|---|---|
| scenarios | 5 |
| correct outcomes | 5/5 (100%) |
| fixes shipped (merged) | 4 |
| bad patches caught by Verifier | 1 |
| regressions prevented | 1 |
| security issues caught | 1 |
| non-actionable filtered | 1 |
| avg revisions to merge | 1.5 |

## Per scenario
| scenario | expected | merged | correct | revisions | verifier_rej | regressions | security_blocks | note |
|---|---|---|---|---|---|---|---|---|
| discount | True | True | yes | 1 | 0 | 0 | 0 | straightforward logic bug, clean one-shot fix |
| none_guard | True | True | yes | 1 | 0 | 0 | 0 | different bug type: crash on None input |
| regression_trap | True | True | yes | 2 | 1 | 1 | 0 | round-1 patch regresses _total; Verifier catches it, round-2 is clean |
| risky_fix | True | True | yes | 2 | 0 | 0 | 1 | round-1 passes tests but uses eval; Security catches it, round-2 is safe |
| non_actionable | False | False | yes | 0 | 0 | 0 | 0 | triage rejects a feature request; the pipeline stops early |
