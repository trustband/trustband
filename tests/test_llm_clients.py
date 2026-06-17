"""Mock-based unit tests for the live clients (no API keys, no network).

These cover the request shape, content extraction, retry behavior, and approval
parsing of OpenAILLM and BandBus — the code paths that the integration tests can
only exercise with real credentials.
"""

import time

import pytest

httpx = pytest.importorskip("httpx")

from trustband.bus import AgentMessage, ApprovalRequest  # noqa: E402
from trustband.contracts import FixPlan  # noqa: E402
from trustband.llm import OpenAILLM  # noqa: E402


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("POST", "https://x/v1/chat/completions"),
                response=httpx.Response(self.status_code),
            )

    def json(self):
        return self._payload


class _FakeHttpx:
    """Stands in for the httpx module inside OpenAILLM."""

    TransportError = httpx.TransportError
    HTTPStatusError = httpx.HTTPStatusError

    def __init__(self, responder):
        self._responder = responder
        self.calls: list[dict] = []

    def post(self, url, headers, json, timeout):
        self.calls.append({"url": url, "json": json})
        return self._responder(self.calls)


def _openai(monkeypatch, responder):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = OpenAILLM(model="m", base_url="https://x/v1")
    llm._httpx = _FakeHttpx(responder)
    return llm


def test_openai_extracts_content_and_request_shape(monkeypatch):
    payload = {"choices": [{"message": {"content": '{"ok":1}'}}]}
    llm = _openai(monkeypatch, lambda calls: _Resp(payload))
    out = llm.complete("hi", kind="plan")
    assert out == '{"ok":1}'
    call = llm._httpx.calls[0]
    assert call["url"] == "https://x/v1/chat/completions"
    assert call["json"]["model"] == "m"
    assert "max_completion_tokens" in call["json"]


def test_openai_retries_transport_error_then_succeeds(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)

    def responder(calls):
        if len(calls) == 1:
            raise httpx.ConnectError("transient blip")
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    llm = _openai(monkeypatch, responder)
    assert llm.complete("hi") == "ok"
    assert len(llm._httpx.calls) == 2  # retried once


def test_openai_empty_content_fails_fast(monkeypatch):
    llm = _openai(monkeypatch, lambda calls: _Resp({"choices": [{"message": {"content": None}}]}))
    with pytest.raises(RuntimeError, match="no content"):
        llm.complete("hi")
    assert len(llm._httpx.calls) == 1  # empty content is NOT retried into a storm


def test_openai_http_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    llm = _openai(monkeypatch, lambda calls: _Resp({}, status=401))
    with pytest.raises(RuntimeError, match="failed"):
        llm.complete("hi")
    assert len(llm._httpx.calls) == 1  # 4xx surfaces immediately


# --- BandBus (mocked Band REST client) ---

pytest.importorskip("band")
from trustband.band_bus import BandBus  # noqa: E402


class _BandResource:
    """Mocks band's agent_api_messages using the REAL response/message types."""

    def __init__(self):
        self.posted: list[tuple[str, str, list[str]]] = []  # (chat_id, content, mention_ids)
        self.queue: list[tuple[str, str]] = []  # (content, sender_type)
        self.processed: list[str] = []

    def create_agent_chat_message(self, chat_id, message):
        self.posted.append((chat_id, message.content, [m.id for m in message.mentions]))

    def get_agent_next_message(self, chat_id):
        from thenvoi_rest.agent_api_messages.types.get_agent_next_message_response import (
            GetAgentNextMessageResponse,
        )
        from thenvoi_rest.types.chat_message import ChatMessage

        if not self.queue:
            return type("Empty", (), {"data": None})()
        content, sender = self.queue.pop(0)
        msg = ChatMessage(
            content=content, id="m1", message_type="text", sender_id="u1", sender_type=sender
        )
        return GetAgentNextMessageResponse(data=msg)

    def mark_agent_message_processed(self, chat_id, message_id):
        self.processed.append(message_id)


class _Participants:
    """Room has the agent itself plus a human — BandBus must mention the human, not self."""

    def list_agent_chat_participants(self, chat_id):
        agent = type("P", (), {"id": "agent-uuid"})()
        human = type("P", (), {"id": "human-uuid"})()
        return type("R", (), {"data": [agent, human]})()


class _BandClient:
    def __init__(self):
        self.agent_api_messages = _BandResource()
        self.agent_api_participants = _Participants()


def _band(monkeypatch):
    monkeypatch.setenv("BAND_API_KEY", "test")
    monkeypatch.setenv("BAND_AGENT_ID", "agent-uuid")
    bus = BandBus(chat_id="room-1", approval_timeout=1, poll_interval=0)
    bus._client = _BandClient()
    return bus


def test_band_send_posts_to_room(monkeypatch):
    bus = _band(monkeypatch)
    bus.send(AgentMessage(sender="x", kind="note", text="hello"))
    chat_id, content, mention_ids = bus._client.agent_api_messages.posted[-1]
    assert "hello" in content  # the wire payload wraps the message envelope
    assert mention_ids == ["human-uuid"]  # Band requires mentioning another participant...
    assert "agent-uuid" not in mention_ids  # ...and rejects mentioning yourself
    assert bus.history()[-1].text == "hello"


def test_band_handoff_shares_context(monkeypatch):
    bus = _band(monkeypatch)
    bus.handoff("planner", "coder", FixPlan(issue_id="X", root_cause="rc"))
    assert bus.get_context("FixPlan")["root_cause"] == "rc"
    assert bus._client.agent_api_messages.posted  # context + handoff posted to room


def test_band_request_approval_parses_approve(monkeypatch):
    bus = _band(monkeypatch)
    bus._client.agent_api_messages.queue = [("approve please", "user")]
    decision = bus.request_approval(ApprovalRequest(issue_id="X", summary="merge?"))
    assert decision.approved is True
    assert bus._client.agent_api_messages.processed == ["m1"]  # message was marked processed


def test_band_request_approval_parses_decline(monkeypatch):
    bus = _band(monkeypatch)
    bus._client.agent_api_messages.queue = [("please decline this", "user")]
    decision = bus.request_approval(ApprovalRequest(issue_id="X", summary="merge?"))
    assert decision.approved is False


def test_band_request_approval_ignores_agent_own_messages(monkeypatch):
    bus = _band(monkeypatch)
    bus._approval_timeout = 0.2  # keep the timeout path fast
    # an "approve" posted by the agent/system must NOT count as the human gate decision
    bus._client.agent_api_messages.queue = [("approve!!", "agent")]
    decision = bus.request_approval(ApprovalRequest(issue_id="X", summary="merge?"))
    assert decision.approved is False  # ignored -> times out -> decline
