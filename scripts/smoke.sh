#!/usr/bin/env bash
# Smoke test: from a clean checkout, dependencies install, the suite passes, and
# the offline pipeline produces a trustworthy PR. This is the Phase 5.1 check.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> uv sync"
uv sync

echo "==> ruff"
uv run ruff check .

echo "==> mypy"
uv run mypy src

echo "==> pytest"
uv run pytest -q

echo "==> offline pipeline on the bundled fixture"
uv run trustband run \
  --repo fixtures/buggy_app \
  --issue fixtures/buggy_app/ISSUE.md \
  --bus memory --llm fake

echo "==> benchmark across all scenarios"
uv run trustband bench

echo "==> smoke OK"
