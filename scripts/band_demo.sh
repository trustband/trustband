#!/usr/bin/env bash
# Live Band demo: drive the band over a REAL Band room.
# Needs BAND_API_KEY (+ OPENAI_API_KEY/OPENAI_BASE_URL for --llm real). Credentials and the
# room id come from ~/.config/secrets/api-keys.env (BAND_ROOM holds the id; kept out of the repo).
# Ready to run the moment a BAND_API_KEY is added — nothing else to change.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source ~/.config/secrets/api-keys.env; set +a
: "${BAND_API_KEY:?set BAND_API_KEY in ~/.config/secrets/api-keys.env (from the band.ai agent page)}"
: "${BAND_ROOM:?set BAND_ROOM in ~/.config/secrets/api-keys.env}"

# Optional: verify connectivity in isolation first.
uv run python spike/band_hello.py

TRUSTBAND_MODEL="${TRUSTBAND_MODEL:-gpt-5.4-high}" uv run trustband run \
  --repo fixtures/buggy_app --issue fixtures/buggy_app/ISSUE.md \
  --bus band --band-room "$BAND_ROOM" --llm real
