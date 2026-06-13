[中文](./README.md)

# TrustBand

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)
![Built on Band](https://img.shields.io/badge/Built%20on-Band-7c3aed.svg)

> A band of agents collaborating on [Band](https://www.band.ai/) that turns a bug/issue into a fix PR you can trust enough to merge.
>
> **Don't just write code — earn the merge.**

## What it solves

Making an AI write code is no longer the hard part; trusting it enough to merge is. TrustBand orchestrates specialized agents in a shared Band room — planning, coding, **verifying**, reviewing, and human approval — and produces a PR backed by deterministic evidence.

The differentiator is the **Verifier agent**: instead of an LLM grading itself, it runs real execution-path tests, regression checks, and trajectory assertions, then decides on evidence whether the fix has earned the merge.

## Agents

| Agent | Responsibility | Output |
|---|---|---|
| Planner | Read the issue + repo context, locate the root cause | `FixPlan` |
| Coder | Produce a patch from the plan (can wrap Claude Code / Codex) | `Patch` |
| **Verifier** | Real-path tests + regression + trajectory assertions | `VerdictReport` |
| Reviewer | Critical review, can request changes | `ReviewReport` |
| Human gate | Approve / decline after seeing the evidence | `Decision` |

All handoffs, structured context exchange, and human approval flow through Band (`--bus band`); an in-memory fake bus runs the same pipeline offline (`--bus memory`).

## Quickstart (offline, free, deterministic)

```bash
uv sync
uv run pytest -q
uv run trustband run --repo fixtures/buggy_app --issue fixtures/buggy_app/ISSUE.md --bus memory --llm fake
```

Offline mode needs no API keys. For live Band / real LLMs, see [SETUP.md](./SETUP.md).

## Status

Under active development (Band of Agents Hackathon, June 2026). Architecture diagram and demo land in Phase 5.
