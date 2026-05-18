import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals.rule import (
    build_eval_run_payload,
    evaluate_file,
    load_eval_cases,
    render_eval_run_markdown,
    parse_orchestrator_classification,
    render_ticket_goal,
    score_classification,
    write_eval_artifacts,
    write_eval_run_json,
    write_eval_run_markdown,
)
from ticket_model import ClassificationResult, ExpectedClassification, TicketInput, fallback_classification


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "ticket_eval_cases.json"


def test_render_ticket_goal_is_deterministic():
    ticket = TicketInput(
        id="T-123",
        subject="Production is down",
        body="All users are blocked.",
        source="synthetic",
        channel="email",
        metadata={"z": 1, "a": 2},
    )

    first = render_ticket_goal(ticket)
    second = render_ticket_goal(ticket)

    assert first == second
    assert "triage this support ticket" in first
    assert "Ticket ID: T-123" in first
    assert "Subject: Production is down" in first
    assert "All users are blocked." in first
    assert '{"a": 2, "z": 1}' in first


def test_parse_orchestrator_classification_current_no_llm_output():
    output = """Classification: bug / critical / neutral
Route: Technical Support L2
SLA: 1h
Tags: bug, critical, en, neutral
Human required: True

Draft reply:
Hi
"""

    actual = parse_orchestrator_classification(output)

    assert actual.category == "bug"
    assert actual.severity == "critical"
    assert actual.priority == "critical"
    assert actual.sentiment == "neutral"
    assert actual.language == "en"
    assert actual.route_to == "Technical Support L2"
    assert actual.sla_hours == 1
    assert actual.requires_human is True
    assert actual.confidence == 0.0
    assert actual.tags == ["bug", "critical", "en", "neutral"]


def test_fallback_classification_returns_canonical_default():
    fallback = fallback_classification()

    assert fallback.category == "general"
    assert fallback.severity == "low"
    assert fallback.priority == "low"
    assert fallback.route_to == "Customer Support L1"
    assert fallback.sla_hours == 72
    assert fallback.confidence == 0.0
    assert fallback.tags == []


def test_score_classification_passes_expected_fields():
    actual = ClassificationResult(
        category="billing",
        severity="medium",
        priority="medium",
        sentiment="negative",
        language="en",
        route_to="Billing / Finance Support",
        sla_hours=24,
        requires_human=True,
        confidence=0.0,
        tags=["billing", "en", "medium", "negative"],
    )
    expected = ExpectedClassification(
        category="billing",
        allowed_severities=["medium", "high"],
        route_to="Billing / Finance Support",
        requires_human=True,
        tags_contains=["billing", "negative"],
    )

    passed, failures, field_results = score_classification(actual, expected)

    assert passed is True
    assert failures == []
    assert field_results == {
        "category": True,
        "route_to": True,
        "requires_human": True,
    }
    assert "severity" not in field_results
    assert "tags_contains" not in field_results


def test_score_classification_reports_deterministic_failures():
    actual = ClassificationResult(
        category="bug",
        severity="critical",
        priority="critical",
        sentiment="neutral",
        language="en",
        route_to="Technical Support L2",
        sla_hours=1,
        requires_human=True,
        confidence=0.0,
        tags=["bug", "critical"],
    )
    expected = ExpectedClassification(
        category="billing",
        route_to="Billing / Finance Support",
        sla_hours=4,
        tags_contains=["billing"],
    )

    passed, failures, field_results = score_classification(actual, expected)

    assert passed is False
    assert failures == [
        "category expected billing got bug",
        "route_to expected Billing / Finance Support got Technical Support L2",
        "sla_hours expected 4 got 1",
        "tags_contains missing billing",
    ]
    assert field_results == {
        "category": False,
        "route_to": False,
        "sla_hours": False,
    }
    assert "tags_contains" not in field_results


def test_load_eval_cases_fixture():
    cases = load_eval_cases(FIXTURE_PATH)

    assert len(cases) == 22
    assert [case.case_id for case in cases[:2]] == [
        "critical_bug_outage",
        "billing_negative_invoice",
    ]
    assert cases[-1].case_id == "general_plan_comparison"


def test_evaluate_file_runs_no_llm_orchestrator_path():
    summary = evaluate_file(FIXTURE_PATH)

    assert summary["total"] == 22
    assert summary["passed"] + summary["failed"] == 22
    assert summary["ok"] is (summary["failed"] == 0)
    assert summary["pass_rate"] == summary["passed"] / summary["total"]
    assert summary["field_accuracy"]["category"]["tested"] == 22
    assert summary["field_accuracy"]["route_to"]["tested"] == 22
    assert all(result["metadata"]["orchestrator_output"] for result in summary["results"])
    assert summary["results"][0]["field_results"]["category"] is True
    assert summary["results"][0]["metadata"]["field_results"]["category"] is True


def test_build_eval_run_payload_adds_stable_run_metadata():
    summary = evaluate_file(FIXTURE_PATH)

    payload = build_eval_run_payload(
        FIXTURE_PATH,
        summary,
        generated_at="2026-01-02T03:04:05+00:00",
    )

    assert payload["schema_version"] == "warp.ticket_eval_run.v1"
    assert payload["run_id"] == "ticket-eval-20260102T030405Z"
    assert payload["generated_at"] == "2026-01-02T03:04:05+00:00"
    assert payload["fixture_path"] == str(FIXTURE_PATH)
    assert payload["mode"] == "rule"
    assert payload["source"] == "no-LLM orchestrator"
    assert payload["total"] == summary["total"]
    assert payload["field_accuracy"] == summary["field_accuracy"]
    assert payload["results"] == summary["results"]


def test_eval_run_json_and_markdown_writers(tmp_path):
    summary = evaluate_file(FIXTURE_PATH)
    payload = build_eval_run_payload(
        FIXTURE_PATH,
        summary,
        run_id="test-run",
        generated_at="2026-01-02T03:04:05+00:00",
    )

    json_path = write_eval_run_json(payload, tmp_path / "run.json")
    markdown_path = write_eval_run_markdown(payload, tmp_path / "run.md")

    saved = json.loads(json_path.read_text())
    markdown = markdown_path.read_text()
    assert saved["run_id"] == "test-run"
    assert saved["results"][0]["case_id"] == "critical_bug_outage"
    assert "# Ticket eval run test-run" in markdown
    assert "| Case | Expected category | Expected severity | Expected route |" in markdown
    assert "| critical_bug_outage | bug | critical | Technical Support L2 | 1h | yes |" in markdown


def test_write_eval_artifacts_writes_timestamped_files_and_latest_json(tmp_path):
    summary = evaluate_file(FIXTURE_PATH)
    payload = build_eval_run_payload(FIXTURE_PATH, summary, run_id="test-run")

    paths = write_eval_artifacts(payload, tmp_path)

    assert paths["json"] == tmp_path / "test-run.json"
    assert paths["markdown"] == tmp_path / "test-run.md"
    assert paths["latest_json"] == tmp_path / "latest.json"
    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert json.loads(paths["latest_json"].read_text())["run_id"] == "test-run"


def test_render_eval_run_markdown_includes_failures():
    payload = {
        "run_id": "failed-run",
        "generated_at": "2026-01-02T03:04:05+00:00",
        "fixture_path": "fixture.json",
        "mode": "rule",
        "source": "no-LLM orchestrator",
        "total": 1,
        "passed": 0,
        "failed": 1,
        "pass_rate": 0.0,
        "results": [
            {
                "case_id": "bad_case",
                "expected": {
                    "category": "billing",
                    "severity": "medium",
                    "route_to": "Billing / Finance Support",
                    "sla_hours": 24,
                    "requires_human": True,
                },
                "actual": {
                    "category": "bug",
                    "severity": "critical",
                    "route_to": "Technical Support L2",
                    "sla_hours": 1,
                    "requires_human": True,
                },
                "passed": False,
                "failures": ["category expected billing got bug"],
            }
        ],
    }

    markdown = render_eval_run_markdown(payload)

    assert "bad_case" in markdown
    assert "FAIL" in markdown
    assert "category expected billing got bug" in markdown
