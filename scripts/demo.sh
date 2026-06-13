#!/usr/bin/env bash
# Demo: show the bug is real (red), let TrustBand produce a *verified* fix, then
# print the evidence-backed PR. Drives the 2-4 minute hackathon video.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "############################################################"
echo "# TrustBand demo — don't just write code, earn the merge.  #"
echo "############################################################"
echo
echo "## 1. The bug is real: the target test fails today"
uv run pytest fixtures/buggy_app -q || true
echo
echo "## 2. The band collaborates on Band to produce a *verified* fix"
uv run trustband run \
  --repo fixtures/buggy_app \
  --issue fixtures/buggy_app/ISSUE.md \
  --bus memory --llm fake
echo
echo "## 3. The PR TrustBand opened (evidence-backed)"
cat artifacts/BUG-1/PR.md
