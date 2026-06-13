#!/usr/bin/env bash
# Run the band across every showcase scenario and write the metrics report.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run trustband bench --out docs/benchmark.md
