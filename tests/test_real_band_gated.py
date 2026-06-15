"""P0 — RealLLM and BandBus: clear errors without credentials; live runs are gated."""

import os

import pytest

from trustband.band_bus import BandBus
from trustband.llm import OpenAILLM, RealLLM


def test_real_llm_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        RealLLM()


def test_openai_llm_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAILLM()


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY")
def test_openai_llm_live_returns_content():
    from trustband.llm import extract_json

    raw = OpenAILLM().complete('Return {"ok": true} as JSON.', kind="triage")
    assert "ok" in extract_json(raw).lower()


def test_band_bus_requires_key(monkeypatch):
    monkeypatch.delenv("BAND_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="BAND_API_KEY"):
        BandBus(chat_id="room-1")


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_real_llm_live_returns_json():
    from trustband.llm import extract_json

    llm = RealLLM(max_tokens=256)
    raw = llm.complete('Return {"ok": true} as JSON.', kind="triage")
    assert "ok" in extract_json(raw).lower()


@pytest.mark.integration
@pytest.mark.skipif(
    not (os.environ.get("BAND_API_KEY") and os.environ.get("BAND_ROOM")),
    reason="needs BAND_API_KEY and BAND_ROOM",
)
def test_band_bus_round_trip():
    from trustband.bus import AgentMessage

    bus = BandBus(chat_id=os.environ["BAND_ROOM"])
    bus.send(AgentMessage(sender="test", kind="note", text="trustband live ping"))
    assert bus.history()[-1].text == "trustband live ping"
