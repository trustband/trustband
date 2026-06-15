# Setup

## Offline (no API keys)

The offline pipeline is fully deterministic and free. It runs the bundled
`fixtures/buggy_app` through the whole band using an in-memory bus and a canned
`FakeLLM`.

```bash
uv sync
uv run pytest -q
uv run trustband run \
  --repo fixtures/buggy_app \
  --issue fixtures/buggy_app/ISSUE.md \
  --bus memory --llm fake
```

A successful run prints the Band room transcript and writes `artifacts/BUG-1/PR.md`.

Convenience scripts:

```bash
bash scripts/smoke.sh   # install + tests + offline pipeline (CI-friendly)
bash scripts/demo.sh    # red test -> verified fix -> PR (for the demo video)
```

## Live mode (Band + real LLM) — Phase 4

Live mode needs credentials. Store them in `~/.config/secrets/api-keys.env`
(chmod 600), one `export NAME="value"` per line — never commit real keys.

| Variable | Needed for | Where to get it |
|---|---|---|
| `BAND_API_KEY` | `--bus band` | register at https://www.band.ai/ (free tier available) |
| `ANTHROPIC_API_KEY` | `--llm real` (Claude) | https://console.anthropic.com/ |
| `OPENAI_API_KEY` | `--llm real` (Codex/GPT) | https://platform.openai.com/ |

```bash
# once the keys are present in the environment:
uv run trustband run \
  --repo <your-repo> \
  --issue <issue.md> \
  --bus band --llm real
```

> **Status:** `RealLLM`, `OpenAILLM`, and `BandBus` are implemented. The
> OpenAI-compatible real-LLM path is **verified live** — a real model fixed the
> bundled `discount` bug end to end through the band (including the revision loop).
> Use `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `TRUSTBAND_MODEL` for an
> OpenAI-compatible endpoint, or `ANTHROPIC_API_KEY` for Claude. Full details and
> all CLI flags: [docs/USAGE.md](./docs/USAGE.md) §8.
