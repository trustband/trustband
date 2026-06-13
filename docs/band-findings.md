# Band SDK findings (Phase 0.2)

Status: **deferred to Phase 4** — the offline pipeline is built first behind the
`AgentBus` abstraction, so live Band access is not on the critical path.

## What we believe about Band (to be verified live)

From public sources (band.ai, docs.band.ai, launch coverage), as of June 2026:

- Band is the communication/interaction layer for multi-agent systems: a shared
  "room" with synchronized context, structured handoffs, agent discovery,
  cross-framework interop, and human-in-the-loop approval.
- The SDK is Python-first (TypeScript also mentioned). It ships adapters for
  Claude Code and Codex, and exposes room messaging + an approval flow
  (e.g. `/approve`, `/decline`).
- A free tier exists (account + API key from the agent dashboard).

**Unverified specifics** (do NOT hard-code until confirmed against a live key):
exact PyPI package name, the room/message/handoff/approval API surface, and how
the Claude Code / Codex adapters register as peers.

## Why this does not block us

`AgentBus` (`src/trustband/bus.py`) isolates every Band-specific call behind four
methods. The entire offline pipeline — and all 26 tests — run on `InMemoryBus`
with zero Band dependency. `BandBus` is a drop-in implementation of the same
interface.

## Day-1 live spike (needs `BAND_API_KEY`)

1. Register at band.ai, create an agent, copy the API key into
   `~/.config/secrets/api-keys.env`.
2. Install the SDK; record the real package name + version here.
3. Build `spike/band_hello.py`: open a room, register two agents, round-trip one
   message. Record the real API in this file.
4. Map the verified API onto `AgentBus` to implement `BandBus`.
5. Map the approval flow onto `request_approval` for human-in-the-loop.
