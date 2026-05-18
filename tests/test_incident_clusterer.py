import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evals import incident_clusterer

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "incident_cluster_eval_cases.json"


def _perfect_cluster_output(fixture: dict) -> dict:
    return {
        "schema_version": incident_clusterer.OUTPUT_SCHEMA_VERSION,
        "prompt_version": incident_clusterer.PROMPT_VERSION,
        "clusters": [
            {
                "incident_id": cluster["incident_id"],
                "kind": cluster["kind"],
                "summary": cluster["summary"],
                "ticket_ids": cluster["ticket_ids"],
                "confidence": 0.9,
                "signals": cluster["signals"],
            }
            for cluster in fixture["expected_clusters"]
        ],
    }


def test_build_cluster_prompt_contains_only_ticket_payload():
    fixture = incident_clusterer.load_incident_fixture(FIXTURE_PATH)

    prompt = incident_clusterer.build_cluster_prompt(fixture["tickets"][:2])

    assert prompt.startswith("Input ticket IDs:")
    assert "Tickets:" in prompt
    assert "T-014" in prompt
    assert "billing tab" in prompt
    assert "expected_incident_id" not in prompt
    assert "singleton_billing_page_loading" not in prompt
    assert "github_oauth_redirect_loop" not in prompt
    assert "page_load" not in prompt
    assert "redirect_loop" not in prompt
    assert "Task:" not in prompt
    assert "Return one JSON object" not in prompt
    assert "Rules:" not in prompt
    assert incident_clusterer.OUTPUT_SCHEMA_VERSION not in prompt
    assert incident_clusterer.PROMPT_VERSION not in prompt


def test_system_prompt_contains_cluster_contract():
    system_prompt = incident_clusterer.SYSTEM_PROMPT

    assert incident_clusterer.OUTPUT_SCHEMA_VERSION in system_prompt
    assert incident_clusterer.PROMPT_VERSION in system_prompt
    assert "Role and task:" in system_prompt
    assert "Grouping rules:" in system_prompt
    assert "Return one JSON object with this exact shape:" in system_prompt
    assert "Validation rules:" in system_prompt
    assert "Include every input ticket exactly once" in system_prompt
    assert "Do not include unknown ticket IDs" in system_prompt
    assert "Use kind=\"incident\" for clusters with 2 or more tickets" in system_prompt
    assert "Use kind=\"singleton\" for clusters with exactly 1 ticket" in system_prompt
    assert "unique stable snake_case" in system_prompt
    assert "Confidence must be between 0 and 1" in system_prompt
    assert "Signals must be short explanatory strings" in system_prompt
    assert "Return valid JSON only" in system_prompt


def test_validate_cluster_output_requires_exact_ticket_coverage():
    fixture = incident_clusterer.load_incident_fixture(FIXTURE_PATH)
    output = _perfect_cluster_output(fixture)
    output["clusters"][0]["ticket_ids"] = output["clusters"][0]["ticket_ids"][:-1]

    with pytest.raises(ValueError, match="clusters missing input ticket IDs"):
        incident_clusterer.validate_cluster_output(
            output,
            {ticket["ticket_id"] for ticket in fixture["tickets"]},
        )


def test_score_clusters_pairwise_metrics_for_split_cluster():
    expected = [
        {"ticket_ids": ["A", "B", "C"]},
        {"ticket_ids": ["D"]},
    ]
    predicted = [
        {"ticket_ids": ["A", "B"]},
        {"ticket_ids": ["C"]},
        {"ticket_ids": ["D"]},
    ]

    metrics = incident_clusterer.score_clusters(predicted, expected)

    assert metrics["pairwise_true_positive"] == 1
    assert metrics["pairwise_false_positive"] == 0
    assert metrics["pairwise_false_negative"] == 2
    assert metrics["pairwise_precision"] == 1.0
    assert metrics["pairwise_recall"] == 1 / 3
    assert metrics["pairwise_f1"] == 0.5


def test_evaluate_file_calls_openrouter_deepseek_and_scores(monkeypatch):
    fixture = incident_clusterer.load_incident_fixture(FIXTURE_PATH)
    calls = []

    def fake_call_with_fallback(prompt, providers, system, max_tokens, temperature, json_output, model=None, json_schema=None):
        calls.append(
            {
                "prompt": prompt,
                "providers": providers,
                "system": system,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "json_output": json_output,
                "model": model,
                "json_schema": json_schema,
            }
        )
        return {
            "ok": True,
            "text": json.dumps(_perfect_cluster_output(fixture)),
            "provider": "openrouter",
            "model": "deepseek/deepseek-v4-flash",
            "request_id": "req-cluster",
            "api_key": "should-not-persist",
        }

    monkeypatch.setattr(incident_clusterer.llm_gateway, "call_with_fallback", fake_call_with_fallback)

    summary = incident_clusterer.evaluate_file(FIXTURE_PATH)

    assert calls == [
        {
            "prompt": calls[0]["prompt"],
            "providers": ["openrouter"],
            "system": incident_clusterer.SYSTEM_PROMPT,
            "max_tokens": 8192,
            "temperature": 0.0,
            "json_output": True,
            "model": "deepseek/deepseek-v4-flash",
            "json_schema": incident_clusterer.OUTPUT_JSON_SCHEMA,
        }
    ]
    assert calls[0]["prompt"].startswith("Input ticket IDs:")
    assert "Tickets:" in calls[0]["prompt"]
    assert "Return one JSON object" not in calls[0]["prompt"]
    assert incident_clusterer.OUTPUT_SCHEMA_VERSION not in calls[0]["prompt"]
    assert summary["schema_version"] == "warp.incident_cluster_eval_result.v1"
    assert summary["total_tickets"] == 30
    assert summary["expected_cluster_count"] == 15
    assert summary["predicted_cluster_count"] == 15
    assert summary["ok"] is True
    assert summary["metrics"]["pairwise_f1"] == 1.0
    assert summary["metadata"]["provider"] == "openrouter"
    assert summary["metadata"]["model"] == "deepseek/deepseek-v4-flash"
    assert summary["metadata"]["llm_gateway"]["request_id"] == "req-cluster"
    assert "api_key" not in summary["metadata"]["llm_gateway"]


def test_cluster_tickets_raises_observability_error_for_malformed_json(monkeypatch):
    fixture = incident_clusterer.load_incident_fixture(FIXTURE_PATH)

    monkeypatch.setattr(
        incident_clusterer.llm_gateway,
        "call_with_fallback",
        lambda *args, **kwargs: {
            "ok": True,
            "text": "not json",
            "provider": "openrouter",
            "model": "deepseek/deepseek-v4-flash",
        },
    )

    with pytest.raises(incident_clusterer.IncidentClustererObservabilityError) as exc:
        incident_clusterer.cluster_tickets(fixture["tickets"])

    assert "malformed LLM JSON response" in str(exc.value)
    assert exc.value.observability["llm_raw_text"] == "not json"


def test_write_eval_json(tmp_path):
    payload = {"schema_version": incident_clusterer.EVAL_SCHEMA_VERSION, "metrics": {}}

    path = incident_clusterer.write_eval_json(payload, tmp_path / "cluster.json")

    assert json.loads(path.read_text())["schema_version"] == incident_clusterer.EVAL_SCHEMA_VERSION
