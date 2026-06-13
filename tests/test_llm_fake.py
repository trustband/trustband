"""Phase 3.1 — FakeLLM replays by kind; extract_json tolerates fences."""

import pytest

from trustband.llm import FakeLLM, RealLLM, extract_json


def test_fake_llm_replays_by_kind():
    llm = FakeLLM({"plan": '{"x": 1}'}, default="{}")
    assert llm.complete("prompt", kind="plan") == '{"x": 1}'
    assert llm.complete("prompt", kind="unknown") == "{}"
    assert llm.calls[0] == ("plan", "prompt")


def test_extract_json_strips_fences():
    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('```\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('{"a": 1}') == '{"a": 1}'


def test_fake_llm_sequences_lists_by_call_order():
    llm = FakeLLM({"code": ["first", "second"]})
    assert llm.complete("p", kind="code") == "first"
    assert llm.complete("p", kind="code") == "second"
    assert llm.complete("p", kind="code") == "second"  # clamped to the last entry


def test_real_llm_not_wired_offline():
    with pytest.raises(NotImplementedError):
        RealLLM().complete("prompt", kind="plan")
