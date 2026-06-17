# Band SDK findings (Phase 0.2 → verified live 2026-06-17)

Status: **VERIFIED LIVE** — the full 7-agent pipeline ran end-to-end over a real
Band room with a real LLM and a real human approval. See "Verified live API" below.
The offline pipeline was built first behind the `AgentBus` abstraction, so live Band
access was never on the critical path.

## What we believe about Band (to be verified live)

From public sources (band.ai, docs.band.ai, launch coverage), as of June 2026:

- Band is the communication/interaction layer for multi-agent systems: a shared
  "room" with synchronized context, structured handoffs, agent discovery,
  cross-framework interop, and human-in-the-loop approval.
- The SDK is Python-first (TypeScript also mentioned). It ships adapters for
  Claude Code and Codex, and exposes room messaging + an approval flow
  (e.g. `/approve`, `/decline`).
- A free tier exists (account + API key from the agent dashboard).

## Verified live API (2026-06-17, `band` SDK v1.0.0)

Confirmed against a live `BAND_API_KEY` + agent UUID. `BandBus` (`src/trustband/band_bus.py`)
is built on exactly these:

- **Package**: `band` (import `band`; underlying `thenvoi_rest`). Client: `RestClient(api_key=..., base_url="https://app.band.ai")` — prod base URL is `https://app.band.ai` (the SDK default is the dev host).
- **Post a message**: `agent_api_messages.create_agent_chat_message(chat_id, message=ChatMessageRequest(content, mentions))`.
- **Read inbound**: `agent_api_messages.get_agent_next_message(chat_id).data` → `ChatMessage(content, id, sender_id, sender_type, ...)`; then `mark_agent_message_processed(chat_id, id)`. `list_agent_messages(chat_id)` lists *inbound* (not the agent's own posts).
- **Chats**: `agent_api_chats.create_agent_chat(chat=ChatRoomRequest())` (no-arg works), `list_agent_chats()`.
- **Participants**: `agent_api_participants.list_agent_chat_participants(chat_id)` and `add_agent_chat_participant(chat_id, participant=ParticipantRequest(participant_id, role="member"))`.
- **Peers**: `agent_api_peers.list_agent_peers()` — returns who the agent may interact with (the human owner shows up here, which is how we got a participant to add).

### Three server rules that only surface live (each cost one 4xx)

1. **Every message needs ≥1 mention** — `ChatMessageRequest.mentions` has `minItems: 1`; an empty list is a 422.
2. **`cannot_mention_self`** — an agent may not mention its own UUID; it must @ *another* participant. So `BandBus` lists participants and mentions the non-self ones (the human).
3. **Agents can't self-join an existing room** — the agent gets 404 on a room it is not already a participant of, and cannot add itself. Path that works without UI: the agent *creates* a chat, then adds a known **peer** (the human) as a participant, then posts mentioning them. (A human can alternatively add the agent to any room from the band.ai UI.)

### Live run evidence

`trustband run --bus band --band-room <id> --llm real` produced a real Band transcript:
triage → reproducer → planner → coder → verifier → security → reviewer → human gate,
all posted to the room; the human replied `approve` in band.ai; `BandBus._read_decision`
parsed it → merged. Verdict TRUSTWORTHY, 0 regressions. Artifact: `artifacts/BUG-1/PR.md`.

**Implemented locally**: `src/trustband/remote_agent.py` adds a Coder-compatible
remote peer seam. The orchestrator can send a structured remote task and consume
a returned `RemotePatch`, with tests proving the pipeline can run with the Coder
as a remote participant contract.

**Still open for live adapter wiring**: how the Claude Code / Codex adapters
register as *agent* peers in the user's Band workspace, then route their returned
patch into TrustBand's `RemotePatch` context key.

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
