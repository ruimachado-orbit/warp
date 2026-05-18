import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals import ai_labeler as ai_ticket_labeler
from evals.ai_labeler import compare_file, evaluate_file, label_ticket
from ticket_model import TicketInput

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "ticket_eval_cases.json"


def _fixture_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]


def _ticket_id_from_prompt(prompt: str) -> str:
    for case in _fixture_cases():
        ticket_id = case["ticket"]["id"]
        if f"Ticket ID: {ticket_id}" in prompt:
            return ticket_id
    raise AssertionError("prompt did not contain a known fixture ticket ID")


def _classification_for_ticket(ticket_id: str) -> dict:
    for case in _fixture_cases():
        if case["ticket"]["id"] != ticket_id:
            continue
        expected = case["expected"]
        return {
            "category": expected["category"],
            "severity": expected.get("severity") or "medium",
            "priority": expected.get("priority") or expected.get("severity") or "medium",
            "sentiment": expected["sentiment"],
            "language": expected.get("language") or "en",
            "route_to": expected["route_to"],
            "sla_hours": expected.get("sla_hours") or 24,
            "requires_human": expected["requires_human"],
            "confidence": 0.91 if ticket_id == "T-001" else 0.82,
            "tags": expected.get("tags_exact") or expected.get("tags_contains") or [],
        }
    raise AssertionError(f"unknown fixture ticket ID: {ticket_id}")


def _fake_gateway(prompt, providers, system, max_tokens, temperature, json_output):
    assert providers == ["openrouter"]
    assert json_output is True
    ticket_id = _ticket_id_from_prompt(prompt)
    return {
        "ok": True,
        "text": json.dumps(_classification_for_ticket(ticket_id)),
        "provider": providers[0],
        "model": "deepseek/deepseek-v4-flash",
        "request_id": f"req-{ticket_id}",
        "usage": {"total_tokens": 123},
        "api_key": "should-not-be-persisted",
    }


def test_label_ticket_uses_openrouter_and_parses_response(monkeypatch):
    calls = []

    def fake_call(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return {
            "ok": True,
            "text": json.dumps(_classification_for_ticket("T-001")),
            "provider": "openrouter",
            "model": "deepseek/deepseek-v4-flash",
        }

    monkeypatch.setattr(ai_ticket_labeler.llm_gateway, "call_with_fallback", fake_call)

    actual = label_ticket(TicketInput(id="T-001", subject="Production is down"))

    assert calls[0]["providers"] == ["openrouter"]
    assert calls[0]["json_output"] is True
    assert "Allowed category values" in calls[0]["prompt"]
    assert actual.category == "bug"
    assert actual.route_to == "Technical Support L2"
    assert actual.confidence == 0.91


def test_label_ticket_fails_clearly_on_provider_error(monkeypatch):
    monkeypatch.setattr(
        ai_ticket_labeler.llm_gateway,
        "call_with_fallback",
        lambda *args, **kwargs: {"ok": False, "error": "OPENROUTER_API_KEY not set"},
    )

    with pytest.raises(RuntimeError, match="LLM provider openrouter failed: OPENROUTER_API_KEY not set"):
        label_ticket(TicketInput(id="T-001"))


def test_label_ticket_fails_clearly_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        ai_ticket_labeler.llm_gateway,
        "call_with_fallback",
        lambda *args, **kwargs: {"ok": True, "text": "not json"},
    )

    with pytest.raises(ValueError, match="malformed LLM JSON response"):
        label_ticket(TicketInput(id="T-001"))


def test_label_ticket_fails_clearly_on_invalid_labels(monkeypatch):
    invalid = _classification_for_ticket("T-001")
    invalid["route_to"] = "Made Up Queue"
    monkeypatch.setattr(
        ai_ticket_labeler.llm_gateway,
        "call_with_fallback",
        lambda *args, **kwargs: {"ok": True, "text": json.dumps(invalid)},
    )

    with pytest.raises(ValueError, match="invalid LLM classification: route_to"):
        label_ticket(TicketInput(id="T-001"))


def test_ai_evaluate_file_returns_summary_and_metadata(monkeypatch):
    executor_workers = []

    def spy_executor(*args, **kwargs):
        executor_workers.append(kwargs.get("max_workers", args[0] if args else None))
        return RealThreadPoolExecutor(*args, **kwargs)

    monkeypatch.setattr(ai_ticket_labeler, "ThreadPoolExecutor", spy_executor)
    monkeypatch.setattr(ai_ticket_labeler.llm_gateway, "call_with_fallback", _fake_gateway)

    summary = evaluate_file(FIXTURE_PATH)

    assert executor_workers == [ai_ticket_labeler.DEFAULT_MAX_WORKERS]

    assert summary["ok"] is True
    assert summary["total"] == 22
    assert summary["passed"] == 22
    assert summary["failed"] == 0
    assert summary["mode"] == "ai"
    assert summary["source"] == "llm:openrouter"
    assert summary["field_accuracy"]["category"] == {"tested": 22, "correct": 22, "accuracy": 1.0}
    assert summary["field_accuracy"]["route_to"] == {"tested": 22, "correct": 22, "accuracy": 1.0}
    assert summary["results"][0]["field_results"]["category"] is True
    metadata = summary["results"][0]["metadata"]
    assert metadata["provider"] == "openrouter"
    assert metadata["model"] == "deepseek/deepseek-v4-flash"
    assert metadata["source"] == "llm:openrouter"
    assert "Ticket ID: T-001" in metadata["llm_prompt"]
    assert metadata["llm_system"] == ai_ticket_labeler.SYSTEM_PROMPT
    assert json.loads(metadata["llm_raw_text"])["category"] == "bug"
    assert metadata["llm_gateway"]["request_id"] == "req-T-001"
    assert metadata["llm_gateway"]["usage"] == {"total_tokens": 123}
    assert metadata["field_results"]["category"] is True
    assert metadata["field_results"]["route_to"] is True
    assert "text" not in metadata["llm_gateway"]
    assert "api_key" not in metadata["llm_gateway"]


def test_ai_evaluate_file_preserves_case_order_when_parallel_calls_complete_out_of_order(monkeypatch):
    second_completed = threading.Event()
    completion_order = []

    def fake_call(prompt, **kwargs):
        ticket_id = _ticket_id_from_prompt(prompt)
        if ticket_id == "T-001":
            assert second_completed.wait(timeout=1.0)
        else:
            completion_order.append(ticket_id)
            second_completed.set()
        if ticket_id == "T-001":
            completion_order.append(ticket_id)
        return {
            "ok": True,
            "text": json.dumps(_classification_for_ticket(ticket_id)),
            "provider": "openrouter",
            "model": "debug-model",
        }

    monkeypatch.setattr(ai_ticket_labeler.llm_gateway, "call_with_fallback", fake_call)

    summary = evaluate_file(FIXTURE_PATH)

    assert completion_order[0] != "T-001"
    assert completion_order.index("T-001") > 0
    assert [result["case_id"] for result in summary["results"]] == [
        case["case_id"] for case in _fixture_cases()
    ]


def test_ai_evaluate_file_records_labeler_failures(monkeypatch):
    monkeypatch.setattr(
        ai_ticket_labeler.llm_gateway,
        "call_with_fallback",
        lambda *args, **kwargs: {"ok": False, "error": "OPENROUTER_API_KEY not set"},
    )

    summary = evaluate_file(FIXTURE_PATH)

    assert summary["ok"] is False
    assert summary["failed"] == 22
    assert summary["field_accuracy"] == {}
    assert summary["results"][0]["field_results"] == {}
    assert summary["results"][0]["metadata"]["field_results"] == {}
    assert "ai_labeler_error: LLM provider openrouter failed" in summary["results"][0]["failures"][0]


def test_ai_evaluate_case_propagates_unexpected_errors(monkeypatch):
    def broken_labeler(*args, **kwargs):
        raise TypeError("unexpected bug")

    monkeypatch.setattr(ai_ticket_labeler, "_label_ticket_with_observability", broken_labeler)
    case = ai_ticket_labeler.rule.load_eval_cases(FIXTURE_PATH)[0]

    with pytest.raises(TypeError, match="unexpected bug"):
        ai_ticket_labeler.evaluate_case(case)


def test_ai_evaluate_file_preserves_observability_for_malformed_json(monkeypatch):
    def fake_call(prompt, **kwargs):
        return {
            "ok": True,
            "text": "not json from provider",
            "provider": "openrouter",
            "model": "debug-model",
            "request_id": "req-bad-json",
            "usage": {"total_tokens": 42},
            "api_key": "should-not-be-persisted",
            "nested": {"access_token": "secret", "safe": "kept"},
        }

    monkeypatch.setattr(ai_ticket_labeler.llm_gateway, "call_with_fallback", fake_call)

    summary = evaluate_file(FIXTURE_PATH)

    assert summary["ok"] is False
    first = summary["results"][0]
    assert "ai_labeler_error: malformed LLM JSON response" in first["failures"][0]
    metadata = first["metadata"]
    assert metadata["llm_raw_text"] == "not json from provider"
    assert "Ticket ID: T-001" in metadata["llm_prompt"]
    assert metadata["provider"] == "openrouter"
    assert metadata["model"] == "debug-model"
    assert metadata["source"] == "llm:openrouter"
    assert metadata["llm_gateway"]["request_id"] == "req-bad-json"
    assert metadata["llm_gateway"]["usage"] == {"total_tokens": 42}
    assert metadata["llm_gateway"]["nested"] == {"safe": "kept"}
    assert "api_key" not in metadata["llm_gateway"]
    assert "access_token" not in metadata["llm_gateway"]["nested"]


def test_ai_evaluate_file_preserves_observability_for_invalid_classification(monkeypatch):
    invalid = _classification_for_ticket("T-001")
    invalid["route_to"] = "Made Up Queue"

    def fake_call(prompt, **kwargs):
        return {
            "ok": True,
            "text": json.dumps(invalid),
            "provider": "openrouter",
            "model": "debug-model",
            "request_id": "req-invalid-labels",
            "secret": "should-not-be-persisted",
        }

    monkeypatch.setattr(ai_ticket_labeler.llm_gateway, "call_with_fallback", fake_call)

    summary = evaluate_file(FIXTURE_PATH)

    assert summary["ok"] is False
    first = summary["results"][0]
    assert "ai_labeler_error: invalid LLM classification: route_to" in first["failures"][0]
    metadata = first["metadata"]
    assert json.loads(metadata["llm_raw_text"])["route_to"] == "Made Up Queue"
    assert "Ticket ID: T-001" in metadata["llm_prompt"]
    assert metadata["provider"] == "openrouter"
    assert metadata["model"] == "debug-model"
    assert metadata["llm_gateway"]["request_id"] == "req-invalid-labels"
    assert "secret" not in metadata["llm_gateway"]


def test_compare_file_uses_parallel_rule_and_ai_lanes(monkeypatch):
    created_workers = []
    submitted = []

    class FakeFuture:
        def __init__(self, value):
            self.value = value

        def result(self):
            return self.value

    class FakeExecutor:
        def __init__(self, max_workers):
            created_workers.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            submitted.append((fn, args, kwargs))
            return FakeFuture(fn(*args, **kwargs))

    rule_summary = {
        "ok": True,
        "total": 1,
        "passed": 1,
        "failed": 0,
        "pass_rate": 1.0,
        "field_accuracy": {"category": {"tested": 1, "correct": 1, "accuracy": 1.0}},
        "results": [
            {
                "case_id": "case-1",
                "expected": {"category": "bug"},
                "actual": {"category": "bug"},
                "passed": True,
                "failures": [],
                "field_results": {"category": True},
            }
        ],
    }
    ai_summary = {
        **rule_summary,
        "provider": "provider-x",
        "mode": "ai",
        "source": "llm:provider-x",
    }

    monkeypatch.setattr(ai_ticket_labeler, "ThreadPoolExecutor", FakeExecutor)
    monkeypatch.setattr(ai_ticket_labeler.rule, "evaluate_file", lambda path: rule_summary)
    monkeypatch.setattr(ai_ticket_labeler, "evaluate_file", lambda path, *, provider: ai_summary)

    summary = compare_file(FIXTURE_PATH, provider="provider-x")

    assert created_workers == [2]
    assert submitted[0][0] is ai_ticket_labeler.rule.evaluate_file
    assert submitted[1][0] is ai_ticket_labeler.evaluate_file
    assert submitted[1][2] == {"provider": "provider-x"}
    assert summary["rule_field_accuracy"] == rule_summary["field_accuracy"]
    assert summary["ai_field_accuracy"] == ai_summary["field_accuracy"]
    assert summary["results"][0]["rule"]["field_results"] == {"category": True}


def test_compare_file_returns_rule_and_ai_results(monkeypatch):
    monkeypatch.setattr(ai_ticket_labeler.llm_gateway, "call_with_fallback", _fake_gateway)

    summary = compare_file(FIXTURE_PATH)

    assert summary["schema_version"] == "warp.ticket_eval_compare.v1"
    assert summary["ok"] is False
    assert summary["total"] == 22
    assert summary["rule_passed"] < 22
    assert summary["ai_passed"] == 22
    assert summary["ai_source"] == "llm:openrouter"
    assert summary["rule_field_accuracy"]["category"]["tested"] == 22
    assert summary["ai_field_accuracy"]["category"] == {"tested": 22, "correct": 22, "accuracy": 1.0}
    first = summary["results"][0]
    assert first["case_id"] == "critical_bug_outage"
    assert first["expected"]["category"] == "bug"
    assert first["rule_passed"] is True
    assert first["ai_passed"] is True
    assert first["rule"]["field_results"]["category"] is True
    assert first["ai"]["field_results"]["category"] is True
    assert first["ai"]["actual"]["route_to"] == "Technical Support L2"


def test_write_compare_json(tmp_path):
    payload = {"schema_version": "warp.ticket_eval_compare.v1", "results": []}

    path = ai_ticket_labeler.write_compare_json(payload, tmp_path / "compare.json")

    assert json.loads(path.read_text())["schema_version"] == "warp.ticket_eval_compare.v1"
