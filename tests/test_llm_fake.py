"""Phase 3.1 — FakeLLM replays by kind; extract_json tolerates fences."""

import pytest

from trustband.contracts import FixPlan
from trustband.llm import FakeLLM, extract_json, parse_with_retry


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


def test_parse_with_retry_repairs_bad_json():
    good = FixPlan(issue_id="X", root_cause="flat subtraction").model_dump_json()
    llm = FakeLLM({"plan": ["this is not json at all", good]})
    plan = parse_with_retry(llm, "prompt", "plan", FixPlan, retries=2)
    assert plan.root_cause == "flat subtraction"
    assert len(llm.calls) == 2  # one failure, then a repaired success


def test_parse_with_retry_raises_after_exhaustion():
    llm = FakeLLM({"plan": "still not json"})
    with pytest.raises(RuntimeError, match="valid FixPlan JSON"):
        parse_with_retry(llm, "prompt", "plan", FixPlan, retries=1)
