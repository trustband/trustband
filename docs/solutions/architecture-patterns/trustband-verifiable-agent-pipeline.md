---
title: "TrustBand verifiable agent pipeline"
date: 2026-06-17
category: docs/solutions/architecture-patterns
module: TrustBand
problem_type: architecture_pattern
component: assistant
severity: medium
applies_when:
  - Building agent workflows that must produce mergeable code rather than only suggestions
  - Extending a demo agent pipeline into a CI-consumable tool
  - Adding cross-process agent participation without breaking offline determinism
tags: [agent-pipeline, verifier, cli-json, remote-peer, benchmark]
---

# TrustBand verifiable agent pipeline

## Context

TrustBand started as a deterministic multi-agent demonstration: seven in-process agents produced typed artifacts, the Verifier checked test evidence, Security blocked risky patches, and Band mirrored the transcript with human approval. The roadmap implementation converted that demonstration into a stronger product surface without losing the offline path.

The key constraint was trust preservation. New capabilities such as edit patches, affected-test scoping, remote coder participation, JSON output, and real-model benchmark mode all had to keep the same evidence chain: reproduce, plan, patch, verify, scan, review, approve, and emit a PR artifact.

## Guidance

Keep the pipeline contracts stable and add capabilities around those contracts.

- `Patch` supports full-file replacements, search/replace edits, and deletes, but every execution path uses the same patch applicator.
- `ReproReport` includes quality evidence for authored tests, so a model cannot pass a trivially true or import-error test as a reproduction.
- `VerdictReport` records verifier scoping evidence, including selected tests, full-suite fallback, and fallback reason.
- CLI JSON output is produced from explicit output models, not by scraping the human transcript.
- Remote coding is introduced as a Coder-compatible seam, so local deterministic runs and remote Band peer runs share the same orchestrator contract.
- Benchmarks separate deterministic FakeLLM orchestration metrics from opt-in real-model quality metrics.

## Why This Matters

Agent pipelines become untrustworthy when new integration surfaces bypass the evidence path. A remote peer that returns untyped text, an affected-test mode that skips full-suite fallback, or a JSON mode that parses stdout formatting all weaken the merge decision.

The durable pattern is to make every new capability produce or consume typed evidence. The Verifier remains the merge gate, Security remains a separate deterministic check, and human approval receives a PR artifact backed by those reports.

## When to Apply

- Use this pattern when an agent system must ship code, not only summarize or suggest code.
- Use it when adding remote agents to a previously in-process workflow.
- Use it when exposing a human-readable CLI as a machine-readable CI step.
- Use it when optimizing test runtime but the product claim depends on catching regressions.

## Examples

Patch handling moved from per-callsite file writes into one shared applicator. That means the runner, git materialization, and PR diff renderer all agree on how full-file, edit, and delete changes behave.

Verifier scoping is conservative. `--verifier-scope affected` may run selected target tests first, but source-file changes fall back to the full suite before the patch can be marked trustworthy.

Remote coder support is a seam, not a rewrite. The orchestrator can call a local Coder or a `RemoteCoder`; both return the same `Patch` contract and enter the same Verifier/Security/Reviewer loop.

## Related

- `docs/plans/2026-06-17-001-feat-trustband-capability-roadmap-plan.md`
- `docs/architecture.md`
- `docs/band-findings.md`
