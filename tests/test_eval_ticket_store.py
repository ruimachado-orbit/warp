import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals.store import (
    convert_artifact_file,
    convert_runs_dir,
    load_fixture_tickets_by_case_id,
    safe_case_filename,
    safe_filename,
    upsert_comparison_payload,
    upsert_eval_run_payload,
)


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "ticket_eval_cases.json"


def _run_payload() -> dict:
    return {
        "schema_version": "warp.ticket_eval_run.v1",
        "run_id": "run-1",
        "generated_at": "2026-01-02T03:04:05+00:00",
        "fixture_path": str(FIXTURE_PATH),
        "mode": "rule",
        "source": "no-LLM orchestrator",
        "ok": True,
        "total": 1,
        "passed": 1,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [
            {
                "case_id": "critical_bug_outage",
                "expected": {"category": "bug"},
                "actual": {"category": "bug", "route_to": "Technical Support L2"},
                "passed": True,
                "failures": [],
                "field_results": {"category": True},
                "metadata": {"note": "first"},
            }
        ],
    }


def _comparison_payload() -> dict:
    return {
        "schema_version": "warp.ticket_eval_compare.v1",
        "generated_at": "2026-01-03T03:04:05+00:00",
        "fixture_path": str(FIXTURE_PATH),
        "provider": "openrouter",
        "results": [
            {
                "case_id": "critical_bug_outage",
                "expected": {"category": "bug"},
                "rule": {
                    "actual": {"category": "bug", "route_to": "Technical Support L2"},
                    "passed": True,
                    "failures": [],
                    "field_results": {"category": True, "route_to": True},
                },
                "ai": {
                    "actual": {"category": "billing", "route_to": "Billing / Finance Support"},
                    "passed": False,
                    "failures": ["category expected bug got billing"],
                    "field_results": {"category": False, "route_to": False},
                },
                "rule_passed": True,
                "ai_passed": False,
            }
        ],
    }


def test_safe_filename_sanitizes_path_components():
    assert safe_filename("run/id with spaces") == "run-id-with-spaces"
    assert safe_filename("!!!", "fallback") == "fallback"


def test_safe_case_filename_sanitizes_case_ids():
    assert safe_case_filename("case/id with spaces") == "case-id-with-spaces.json"
    assert safe_case_filename("!!!") == "ticket-eval-case.json"


def test_load_fixture_tickets_by_case_id_enriches_from_fixture():
    fixtures = load_fixture_tickets_by_case_id(FIXTURE_PATH)

    assert fixtures["critical_bug_outage"]["ticket"]["id"] == "T-001"
    assert fixtures["critical_bug_outage"]["expected"]["route_to"] == "Technical Support L2"
    assert fixtures["critical_bug_outage"]["fixture_path"] == str(FIXTURE_PATH)


def test_upsert_eval_run_payload_writes_ticket_file_and_dedupes(tmp_path):
    payload = _run_payload()

    paths = upsert_eval_run_payload(payload, tmp_path, fixtures=FIXTURE_PATH)
    upsert_eval_run_payload(payload, tmp_path, fixtures=FIXTURE_PATH)

    assert paths == [tmp_path / "run-1" / "tickets" / "critical_bug_outage.json"]
    saved = json.loads(paths[0].read_text())
    assert saved["schema_version"] == "warp.eval_ticket_store.v1"
    assert saved["case_id"] == "critical_bug_outage"
    assert saved["ticket"]["subject"] == "Production is down"
    assert saved["expected"]["category"] == "bug"
    assert len(saved["evaluations"]) == 1
    assert saved["evaluations"][0]["run_id"] == "run-1"
    assert saved["evaluations"][0]["mode"] == "rule"
    assert saved["evaluations"][0]["metadata"] == {"note": "first", "field_results": {"category": True}}


def test_upsert_comparison_payload_writes_comparison_and_dedupes(tmp_path):
    payload = _comparison_payload()

    paths = upsert_comparison_payload(payload, tmp_path, fixtures=FIXTURE_PATH)
    upsert_comparison_payload(payload, tmp_path, fixtures=FIXTURE_PATH)

    assert paths == [tmp_path / "comparison-20260103T030405Z-openrouter" / "tickets" / "critical_bug_outage.json"]
    saved = json.loads(paths[0].read_text())
    assert len(saved["comparisons"]) == 1
    comparison = saved["comparisons"][0]
    assert comparison["provider"] == "openrouter"
    assert comparison["rule_passed"] is True
    assert comparison["ai_passed"] is False
    assert comparison["agreement"] is False
    assert comparison["rule"]["field_results"] == {"category": True, "route_to": True}
    assert comparison["ai"]["field_results"] == {"category": False, "route_to": False}
    assert "category" in comparison["disagreement_fields"]
    assert "route_to" in comparison["disagreement_fields"]


def test_convert_runs_dir_converts_json_artifacts_and_skips_duplicates(tmp_path):
    runs_dir = tmp_path / "runs"
    tickets_dir = tmp_path / "tickets"
    runs_dir.mkdir()
    (runs_dir / "run.json").write_text(json.dumps(_run_payload()), encoding="utf-8")
    (runs_dir / "latest.json").write_text(json.dumps(_run_payload()), encoding="utf-8")

    paths = convert_runs_dir(runs_dir, tickets_dir, fixtures=FIXTURE_PATH)

    assert paths == [tickets_dir / "run-1" / "tickets" / "critical_bug_outage.json"]
    saved = json.loads(paths[0].read_text())
    assert len(saved["evaluations"]) == 1


def test_convert_artifact_file_detects_comparison_payload(tmp_path):
    artifact = tmp_path / "compare.json"
    artifact.write_text(json.dumps(_comparison_payload()), encoding="utf-8")

    paths = convert_artifact_file(artifact, tmp_path / "tickets", fixtures=FIXTURE_PATH)

    assert paths == [tmp_path / "tickets" / "comparison-20260103T030405Z-openrouter" / "tickets" / "critical_bug_outage.json"]
    saved = json.loads(paths[0].read_text())
    assert saved["comparisons"][0]["provider"] == "openrouter"
