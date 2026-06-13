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

> Phase 4 (the `BandBus` and `RealLLM` implementations) is wired against the real
> Band SDK once the API is verified — see `docs/band-findings.md`. Until then the
> offline path above is the supported, working entry point.
