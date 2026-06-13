#!/usr/bin/env bash
# Demo: walk through the band's headline behaviors, then the metrics.
# Drives the 2-4 minute hackathon video. Fully offline and deterministic.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "############################################################"
echo "# TrustBand — don't just write code, earn the merge.       #"
echo "############################################################"
echo
echo "## 1. Happy path: a bug becomes a verified PR (1 revision)"
uv run trustband run --scenario discount
echo
echo "## 2. The Verifier catches a regression the target test misses (loops to a clean fix)"
uv run trustband run --scenario regression_trap
echo
echo "## 3. The Security agent catches an eval() that passes every test"
uv run trustband run --scenario risky_fix
echo
echo "## 4. Triage filters a non-actionable feature request"
uv run trustband run --scenario non_actionable
echo
echo "## 5. Effect metrics across all scenarios"
uv run trustband bench
echo
echo "## The PR TrustBand opened for the happy path:"
cat artifacts/DISCOUNT-1/PR.md
