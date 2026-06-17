"""Minimal Band connectivity check (Phase 0.2 'hello room' spike).

Run this once a real ``BAND_API_KEY`` is set, to verify the SDK + credentials in
isolation before driving the full pipeline over ``--bus band``:

    set -a; source ~/.config/secrets/api-keys.env; set +a   # loads BAND_API_KEY + BAND_ROOM
    uv run python spike/band_hello.py

It posts one message to the room in ``$BAND_ROOM`` and reports the result. The
room id is read from the environment, never hard-coded into the repo.
"""

from __future__ import annotations

import os

from trustband.band_bus import BandBus
from trustband.bus import AgentMessage


def main() -> int:
    """Post a ping to the configured Band room and report what happened."""
    room = os.environ.get("BAND_ROOM")
    if not room:
        raise SystemExit("set BAND_ROOM to the Band chat/room id (and BAND_API_KEY)")
    bus = BandBus(chat_id=room)  # reads BAND_API_KEY from the environment
    bus.send(AgentMessage(sender="band-hello", kind="note", text="TrustBand connectivity check"))
    print(f"posted 1 message to room {room}; transcript holds {len(bus.history())} message(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
