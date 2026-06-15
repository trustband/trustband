# Submission checklist — Band of Agents Hackathon

Deadline: **2026-06-19**.

## Hard requirements
- [x] ≥3 specialized agents — 7 here: Triage, Reproducer, Planner, Coder, Verifier, Security, Reviewer (+ human gate)
- [x] Structured context exchange (8 typed Pydantic artifacts handed off in the room)
- [x] Human-in-the-loop approval gate
- [x] Revision loop (Verifier/Security push back → Coder revises)
- [ ] Band is the *active* layer (live `BandBus`, Phase 4 — needs `BAND_API_KEY`)

## Repo
- [x] Public GitHub repository
- [x] MIT `LICENSE`
- [x] Bilingual README (`README.md` / `README_EN.md`) with badges
- [x] `SETUP.md` with offline + live instructions
- [x] Architecture diagram (`docs/architecture.md`)
- [x] CI on every push: ruff + mypy + pytest + benchmark (`.github/workflows/ci.yml`)
- [x] Green suite + clean lint + types + 93% coverage (`bash scripts/smoke.sh`)

## Demo
- [x] Reproducible demo script (`scripts/demo.sh`)
- [x] Sample PR artifact committed (`docs/sample-PR.md`)
- [x] Effect-metrics report (`docs/benchmark.md`, `scripts/benchmark.sh`)
- [x] Showcase scenarios (clean fix, crash-on-None, regression trap, risky eval, no-test→authored, non-actionable)
- [ ] 2–4 minute demo video (problem → live demo → Band's role → trustworthy verdict)
- [ ] Video uploaded (YouTube/Vimeo) and linked in README

## Submit
- [ ] lablab.ai submission form completed
