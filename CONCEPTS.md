# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## TrustBand Pipeline

### TrustBand
An agent collaboration system that turns a software issue into a verified, review-gated PR artifact.

### AgentBus
The collaboration boundary that carries messages, shared context, typed handoffs, and approval requests between TrustBand agents.

### Verifier
The evidence gate that decides whether a patch earns merge trust by comparing baseline and post-patch test results.

### Reproducer
The agent role that proves a bug exists before planning or coding begins, including authoring a failing test when no suitable test exists.

### Remote Peer
An agent participant that runs outside the orchestrator process but returns the same typed artifact expected from the local agent role.

## Evidence Artifacts

### Patch
The structured code-change artifact produced by the Coder or Remote Peer and consumed by the Verifier, Security reviewer, PR renderer, and git materializer.

### VerdictReport
The Verifier's structured evidence report describing target test status, regressions, suite health, touched files, and verifier scoping decisions.

### ReviewReport
The reviewer artifact that aggregates Verifier and Security evidence into an approve or request-changes decision.

### Decision
The human or automated gate outcome that determines whether TrustBand writes the PR artifact.
