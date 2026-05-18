import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals import synthetic as synthetic_ticket_generator


def valid_payload(count=2):
    return {
        "cases": [
            {
                "case_id": "billing_invoice_dispute",
                "name": "Billing invoice dispute",
                "description": "Customer disputes an unexpected invoice charge.",
                "ticket": {
                    "id": "SYN-001",
                    "subject": "Unexpected charge on invoice",
                    "body": "We were charged twice this month and need someone to review the invoice.",
                    "source": "synthetic",
                    "channel": "email",
                    "language": "en",
                    "metadata": {"synthetic": True},
                },
                "expected": {
                    "category": "billing",
                    "severity": "medium",
                    "priority": "medium",
                    "sentiment": "negative",
                    "language": "en",
                    "route_to": "Billing / Finance Support",
                    "sla_hours": 24,
                    "requires_human": True,
                    "tags_contains": ["billing"],
                },
            },
            {
                "case_id": "integration_webhook_failure",
                "name": "Webhook integration failure",
                "description": "Customer needs help with failed webhook deliveries.",
                "ticket": {
                    "id": "SYN-002",
                    "subject": "Webhook deliveries failing",
                    "body": "Our CRM integration stopped receiving webhook events after rotating credentials.",
                    "source": "synthetic",
                    "channel": "email",
                    "language": "en",
                    "metadata": {"synthetic": True},
                },
                "expected": {
                    "category": "integration",
                    "severity": "high",
                    "priority": "high",
                    "sentiment": "neutral",
                    "language": "en",
                    "route_to": "Integrations Support",
                    "sla_hours": 4,
                    "requires_human": True,
                    "tags_contains": ["integration"],
                },
            },
        ][:count]
    }


def test_generate_cases_calls_llm_gateway_and_validates(monkeypatch):
    calls = []

    def fake_call_with_fallback(prompt, providers, system, max_tokens, temperature, json_output):
        calls.append(
            {
                "prompt": prompt,
                "providers": providers,
                "system": system,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "json_output": json_output,
            }
        )
        return {"ok": True, "text": json.dumps(valid_payload()), "provider": "codex_app_server"}

    monkeypatch.setattr(
        synthetic_ticket_generator.llm_gateway,
        "call_with_fallback",
        fake_call_with_fallback,
    )

    cases = synthetic_ticket_generator.generate_cases(count=2, provider="codex_app_server")

    assert [case.case_id for case in cases] == [
        "billing_invoice_dispute",
        "integration_webhook_failure",
    ]
    assert calls[0]["providers"] == ["codex_app_server"]
    assert calls[0]["json_output"] is True
    assert "Generate exactly 2" in calls[0]["prompt"]


def test_serialize_and_write_fixture_uses_cases_wrapper(tmp_path):
    cases = synthetic_ticket_generator.validate_cases_payload(valid_payload(), expected_count=2)
    output_path = tmp_path / "ticket_eval_cases.json"

    synthetic_ticket_generator.write_fixture(cases, output_path)

    text = output_path.read_text(encoding="utf-8")
    assert text.startswith('{\n  "cases": [')
    assert text.endswith("\n")
    data = json.loads(text)
    assert [case["case_id"] for case in data["cases"]] == [
        "billing_invoice_dispute",
        "integration_webhook_failure",
    ]


def test_generate_cases_fails_clearly_on_provider_error(monkeypatch):
    def fake_call_with_fallback(*args, **kwargs):
        return {"ok": False, "error": "provider unavailable", "text": ""}

    monkeypatch.setattr(
        synthetic_ticket_generator.llm_gateway,
        "call_with_fallback",
        fake_call_with_fallback,
    )

    try:
        synthetic_ticket_generator.generate_cases(count=1)
    except RuntimeError as exc:
        assert "provider unavailable" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_validate_cases_payload_rejects_invalid_enum():
    payload = valid_payload(count=1)
    payload["cases"][0]["expected"]["category"] = "refund"

    try:
        synthetic_ticket_generator.validate_cases_payload(payload, expected_count=1)
    except ValueError as exc:
        assert "case 1 is invalid" in str(exc)
        assert "category" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_validate_cases_payload_rejects_wrong_count():
    try:
        synthetic_ticket_generator.validate_cases_payload(valid_payload(count=1), expected_count=2)
    except ValueError as exc:
        assert "generated 1 cases, expected 2" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def valid_incident_payload():
    return {
        "schema_version": "warp.incident_cluster_eval.v1",
        "name": "Incident clustering eval fixture",
        "description": "One incident plus one singleton.",
        "tickets": [
            {
                "ticket_id": "IC-OAUTH-001",
                "subject": "GitHub OAuth loops",
                "body": "Approving GitHub OAuth sends me back to the login screen.",
                "channel": "email",
                "created_at": "2026-05-18T10:00:00Z",
                "expected_incident_id": "github_oauth_loop",
                "signals": ["github", "oauth", "loop"],
            },
            {
                "ticket_id": "IC-OAUTH-002",
                "subject": "Cannot connect GitHub",
                "body": "The GitHub callback returns but the integration is still disconnected.",
                "channel": "email",
                "created_at": "2026-05-18T10:01:00Z",
                "expected_incident_id": "github_oauth_loop",
                "signals": ["github", "oauth", "loop"],
            },
            {
                "ticket_id": "IC-SINGLE-001",
                "subject": "Need VAT invoice",
                "body": "Please reissue our invoice with the correct VAT number.",
                "channel": "email",
                "created_at": "2026-05-18T10:02:00Z",
                "expected_incident_id": "vat_invoice_request",
                "signals": ["billing", "vat", "invoice"],
            },
        ],
        "expected_clusters": [
            {
                "incident_id": "github_oauth_loop",
                "kind": "incident",
                "summary": "GitHub OAuth loops after authorization.",
                "signals": ["github", "oauth", "loop"],
                "ticket_ids": ["IC-OAUTH-001", "IC-OAUTH-002"],
            },
            {
                "incident_id": "vat_invoice_request",
                "kind": "singleton",
                "summary": "Standalone VAT invoice request.",
                "signals": ["billing", "vat", "invoice"],
                "ticket_ids": ["IC-SINGLE-001"],
            },
        ],
        "evaluation_notes": {
            "primary_metric": "pairwise clustering precision/recall/F1 over ticket_id pairs",
            "positive_pairs": "tickets sharing the same expected_incident_id",
            "negative_pairs": "tickets with different expected_incident_id values",
            "singleton_policy": "singleton tickets should remain alone unless intentionally linked",
        },
    }


def test_generate_incident_fixture_calls_llm_gateway_and_validates(monkeypatch):
    calls = []

    def fake_call_with_fallback(prompt, providers, system, max_tokens, temperature, json_output):
        calls.append(
            {
                "prompt": prompt,
                "providers": providers,
                "system": system,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "json_output": json_output,
            }
        )
        return {"ok": True, "text": json.dumps(valid_incident_payload())}

    monkeypatch.setattr(
        synthetic_ticket_generator.llm_gateway,
        "call_with_fallback",
        fake_call_with_fallback,
    )

    payload = synthetic_ticket_generator.generate_incident_fixture(
        incident_count=1,
        tickets_per_incident=2,
        singleton_count=1,
        provider="codex_app_server",
    )

    assert len(payload["tickets"]) == 3
    assert len(payload["expected_clusters"]) == 2
    assert calls[0]["providers"] == ["codex_app_server"]
    assert calls[0]["system"] == synthetic_ticket_generator.INCIDENT_SYSTEM_PROMPT
    assert calls[0]["max_tokens"] == 16000
    assert calls[0]["json_output"] is True
    assert "1 multi-ticket incidents" in calls[0]["prompt"]
    assert "2 tickets per multi-ticket incident" in calls[0]["prompt"]
    assert "1 unrelated singleton tickets" in calls[0]["prompt"]


def test_serialize_and_write_incident_fixture(tmp_path):
    payload = synthetic_ticket_generator.validate_incident_payload(
        valid_incident_payload(),
        expected_incident_count=1,
        expected_tickets_per_incident=2,
        expected_singleton_count=1,
    )
    output_path = tmp_path / "incident_cluster_eval_cases.json"

    synthetic_ticket_generator.write_incident_fixture(payload, output_path)

    text = output_path.read_text(encoding="utf-8")
    assert text.startswith('{\n  "schema_version": "warp.incident_cluster_eval.v1"')
    assert text.endswith("\n")
    data = json.loads(text)
    assert [cluster["incident_id"] for cluster in data["expected_clusters"]] == [
        "github_oauth_loop",
        "vat_invoice_request",
    ]


def test_validate_incident_payload_rejects_duplicate_ticket_id():
    payload = valid_incident_payload()
    payload["tickets"][1]["ticket_id"] = "IC-OAUTH-001"

    try:
        synthetic_ticket_generator.validate_incident_payload(
            payload,
            expected_incident_count=1,
            expected_tickets_per_incident=2,
            expected_singleton_count=1,
        )
    except ValueError as exc:
        assert "duplicate ticket_id: IC-OAUTH-001" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_validate_incident_payload_rejects_wrong_cluster_size():
    payload = valid_incident_payload()
    payload["expected_clusters"][0]["ticket_ids"] = ["IC-OAUTH-001"]

    try:
        synthetic_ticket_generator.validate_incident_payload(
            payload,
            expected_incident_count=1,
            expected_tickets_per_incident=2,
            expected_singleton_count=1,
        )
    except ValueError as exc:
        assert "incident cluster github_oauth_loop has 1 tickets, expected 2" in str(exc)
    else:
        raise AssertionError("expected ValueError")
