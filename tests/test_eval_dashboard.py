import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals.dashboard import load_eval_runs, render_dashboard_html, write_dashboard


def run_payload(run_id="run-1", generated_at="2026-01-02T03:04:05+00:00", passed=1):
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "fixture_path": "tests/fixtures/ticket_eval_cases.json",
        "mode": "rule",
        "source": "no-LLM orchestrator",
        "total": 2,
        "passed": passed,
        "failed": 2 - passed,
        "pass_rate": passed / 2,
        "field_accuracy": {"category": {"tested": 1, "correct": 0, "accuracy": 0.0}},
        "results": [
            {
                "case_id": "case<&>",
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
                    "requires_human": False,
                },
                "passed": False,
                "failures": ["category expected billing got bug", "parse_error: bad <line>"],
                "field_results": {"category": False},
                "metadata": {
                    "field_results": {"category": False},
                    "goal": "Subject: Refund <needed> & urgent\nBody: please review </script><img src=x onerror=alert(1)>",
                    "orchestrator_output": {"route_to": "Billing <Team>", "note": "use & verify"},
                },
            }
        ],
    }


def ai_run_payload():
    payload = run_payload(run_id="ai-run", generated_at="2026-01-03T00:00:00+00:00", passed=0)
    payload["mode"] = "ai"
    payload["source"] = "llm:openrouter"
    payload["provider"] = "openrouter"
    payload["results"][0]["case_id"] = "case-1"
    payload["results"][0]["metadata"] = {
        "mode": "ai",
        "source": "llm:openrouter",
        "provider": "openrouter",
    }
    return payload


def ticket_doc(case_id="case-1"):
    return {
        "schema_version": "warp.eval_ticket_store.v1",
        "case_id": case_id,
        "name": "Refund request",
        "description": "Customer asks for a duplicate charge refund.",
        "ticket": {
            "id": "T-1",
            "source": "synthetic",
            "channel": "email",
            "subject": "Refund <needed> & urgent",
            "body": "please review </script><img src=x onerror=alert(1)>",
            "metadata": {"synthetic": True},
        },
        "expected": {
            "category": "billing",
            "severity": "medium",
            "route_to": "Billing / Finance Support",
            "sla_hours": 24,
            "requires_human": True,
        },
        "evaluations": [
            {
                "run_id": "ai-run",
                "generated_at": "2026-01-03T00:00:00+00:00",
                "fixture_path": "tests/fixtures/ticket_eval_cases.json",
                "mode": "ai",
                "source": "llm:openrouter",
                "actual": {
                    "category": "bug",
                    "severity": "critical",
                    "route_to": "Technical Support L2",
                    "sla_hours": 1,
                    "requires_human": False,
                },
                "passed": False,
                "failures": ["category expected billing got bug"],
                "metadata": {
                    "mode": "ai",
                    "source": "llm:openrouter",
                    "provider": "openrouter",
                    "field_results": {"category": False},
                },
            }
        ],
        "comparisons": [],
    }


def comparison_ticket_doc():
    doc = ticket_doc("case-compare")
    doc["evaluations"] = []
    doc["comparisons"] = [
        {
            "generated_at": "2026-01-04T00:00:00+00:00",
            "fixture_path": "tests/fixtures/ticket_eval_cases.json",
            "provider": "openrouter",
            "rule": {
                "actual": {
                    "category": "billing",
                    "severity": "medium",
                    "route_to": "Billing / Finance Support",
                },
                "passed": True,
                "failures": [],
                "field_results": {"category": True},
            },
            "ai": {
                "actual": {
                    "category": "bug",
                    "severity": "critical",
                    "route_to": "Technical Support L2",
                },
                "passed": False,
                "failures": ["category expected billing got bug"],
                "field_results": {"category": False},
            },
            "rule_passed": True,
            "ai_passed": False,
            "agreement": False,
            "disagreement_fields": ["category", "severity", "route_to"],
        }
    ]
    return doc


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_eval_runs_skips_latest_and_deduplicates_run_ids(tmp_path):
    older = run_payload(run_id="same", generated_at="2026-01-01T00:00:00+00:00", passed=0)
    newer = run_payload(run_id="same", generated_at="2026-01-02T00:00:00+00:00", passed=1)
    latest_duplicate = run_payload(run_id="same", generated_at="2026-01-03T00:00:00+00:00", passed=2)
    other = run_payload(run_id="other", generated_at="2026-01-04T00:00:00+00:00", passed=2)

    write_json(tmp_path / "older.json", older)
    write_json(tmp_path / "newer.json", newer)
    write_json(tmp_path / "latest.json", latest_duplicate)
    write_json(tmp_path / "other.json", other)

    runs = load_eval_runs(tmp_path)

    assert [run["run_id"] for run in runs] == ["other", "same"]
    assert runs[1]["kind"] == "evaluation"
    assert runs[1]["passed"] == 1
    assert runs[1]["cases"][0]["ticket_text"].startswith("Subject: Refund")


def test_load_eval_runs_uses_latest_json_when_it_is_the_only_copy(tmp_path):
    latest_only = ai_run_payload()
    write_json(tmp_path / "latest.json", latest_only)

    runs = load_eval_runs(tmp_path)

    assert len(runs) == 1
    assert runs[0]["run_id"] == "ai-run"
    assert runs[0]["_source"] == "run_json"
    assert runs[0]["mode"] == "ai"
    assert runs[0]["provider"] == "openrouter"



def test_load_eval_runs_prefers_run_folder_ticket_docs(tmp_path):
    write_json(tmp_path / "ai-run.json", ai_run_payload())
    write_json(tmp_path / "ai-run" / "tickets" / "case-1.json", ticket_doc())

    runs = load_eval_runs(tmp_path)

    assert len(runs) == 1
    run = runs[0]
    assert run["run_id"] == "ai-run"
    assert run["_source"] == "merged"
    assert run["mode"] == "ai"
    assert run["source"] == "llm:openrouter"
    assert run["provider"] == "openrouter"
    assert run["total"] == 2  # top-level aggregate retained
    assert run["field_accuracy"]["category"] == {"tested": 1, "correct": 0, "accuracy": 0.0}
    case = run["cases"][0]
    assert case["name"] == "Refund request"
    assert "Subject: Refund <needed> & urgent" in case["ticket_text"]
    assert "please review </script><img" in case["ticket_text"]
    assert case["expected"]["category"] == "billing"
    assert case["actual"]["category"] == "bug"
    assert case["metadata"]["provider"] == "openrouter"


def test_load_eval_runs_aggregates_field_accuracy_from_ticket_docs_without_top_level_payload(tmp_path):
    write_json(tmp_path / "ai-run" / "tickets" / "case-1.json", ticket_doc())

    runs = load_eval_runs(tmp_path)

    assert len(runs) == 1
    assert runs[0]["_source"] == "run_folder"
    assert runs[0]["field_accuracy"]["category"] == {"tested": 1, "correct": 0, "accuracy": 0.0}


def test_load_eval_runs_falls_back_to_top_level_results_when_no_ticket_folder(tmp_path):
    write_json(tmp_path / "run.json", run_payload())

    runs = load_eval_runs(tmp_path)

    assert len(runs) == 1
    assert runs[0]["_source"] == "run_json"
    assert runs[0]["cases"][0]["expected"]["category"] == "billing"
    assert runs[0]["cases"][0]["actual"]["category"] == "bug"
    assert runs[0]["field_accuracy"]["category"] == {"tested": 1, "correct": 0, "accuracy": 0.0}
    assert runs[0]["cases"][0]["field_results"] == {"category": False}
    assert "Subject: Refund <needed>" in runs[0]["cases"][0]["ticket_text"]


def test_render_dashboard_html_includes_sections_and_escapes_values():
    html = render_dashboard_html([run_payload()])

    assert "Latest run summary" in html
    assert "Run history" in html
    assert "Failures by field/prefix" in html
    assert "Latest run cases" in html
    assert "Mode/source" in html
    assert "Provider" in html
    assert "1/2" in html
    assert "50%" in html
    assert "category" in html
    assert "parse_error" in html
    assert "case&lt;&amp;&gt;" in html
    assert "bad &lt;line&gt;" in html
    assert '<button type="button" class="case-button" data-case-index="0" aria-haspopup="dialog">case&lt;&amp;&gt;</button>' in html
    assert 'role="dialog"' in html
    assert 'id="case-details-data"' in html
    assert "Ticket" in html
    assert "Expected labels" in html
    assert "Actual labels / comparison lanes" in html
    assert "Evaluator output" in html
    assert "Evaluator metadata" in html
    assert "Subject: Refund \\u003cneeded\\u003e \\u0026 urgent" in html
    assert "\\u003c/script\\u003e\\u003cimg src=x onerror=alert(1)\\u003e" in html
    assert "Billing \\u003cTeam\\u003e" in html
    assert "case<&>" not in html
    assert "Refund <needed>" not in html
    assert "</script><img" not in html


def test_render_dashboard_html_includes_ticket_doc_details_for_ai_run(tmp_path):
    write_json(tmp_path / "ai-run.json", ai_run_payload())
    doc = ticket_doc()
    doc["evaluations"][0]["metadata"]["llm_raw_text"] = '{"category":"bug","note":"raw model text"}'
    write_json(tmp_path / "ai-run" / "tickets" / "case-1.json", doc)
    runs = load_eval_runs(tmp_path)

    html = render_dashboard_html(runs)

    assert "ai / llm:openrouter" in html
    assert "openrouter" in html
    assert "Refund request" in html
    assert "Subject: Refund \\u003cneeded\\u003e \\u0026 urgent" in html
    assert "please review \\u003c/script\\u003e\\u003cimg src=x onerror=alert(1)\\u003e" in html
    assert '\\"provider\\": \\"openrouter\\"' in html
    assert "Billing / Finance Support" in html
    assert "Technical Support L2" in html
    assert '{\\"category\\":\\"bug\\",\\"note\\":\\"raw model text\\"}' in html


def test_render_dashboard_html_uses_actual_labels_as_legacy_ai_output_fallback():
    html = render_dashboard_html([ai_run_payload()])

    assert '"evaluator_output": "{\\n  \\"category\\": \\"bug\\"' in html



def test_render_dashboard_html_includes_comparison_cases(tmp_path):
    write_json(
        tmp_path / "comparison-20260104T000000Z-openrouter" / "tickets" / "case-compare.json",
        comparison_ticket_doc(),
    )
    runs = load_eval_runs(tmp_path)

    html = render_dashboard_html(runs)

    assert len(runs) == 1
    assert runs[0]["kind"] == "comparison"
    assert runs[0]["mode"] == "compare"
    assert runs[0]["provider"] == "openrouter"
    assert runs[0]["rule_field_accuracy"]["category"] == {"tested": 1, "correct": 1, "accuracy": 1.0}
    assert runs[0]["ai_field_accuracy"]["category"] == {"tested": 1, "correct": 0, "accuracy": 0.0}
    assert runs[0]["cases"][0]["comparison"]["rule"]["field_results"] == {"category": True}
    assert runs[0]["cases"][0]["comparison"]["ai"]["field_results"] == {"category": False}
    assert "Latest comparison cases" in html
    assert "Rule result" in html
    assert "AI result" in html
    assert "rule vs ai:openrouter" in html
    assert "PASS billing / medium / Billing / Finance Support" in html
    assert "FAIL bug / critical / Technical Support L2" in html
    assert "disagreement:category" in html
    assert "category, severity, route_to" in html


def test_load_eval_runs_preserves_top_level_comparison_field_accuracy(tmp_path):
    payload = {
        "schema_version": "warp.ticket_eval_compare.v1",
        "generated_at": "2026-01-05T00:00:00+00:00",
        "fixture_path": "tests/fixtures/ticket_eval_cases.json",
        "provider": "openrouter",
        "rule_source": "no-LLM orchestrator",
        "ai_source": "llm:openrouter",
        "ok": True,
        "total": 1,
        "rule_passed": 1,
        "rule_failed": 0,
        "ai_passed": 1,
        "ai_failed": 0,
        "rule_pass_rate": 1.0,
        "ai_pass_rate": 1.0,
        "rule_field_accuracy": {"category": {"tested": 1, "correct": 1, "accuracy": 1.0}},
        "ai_field_accuracy": {"category": {"tested": 1, "correct": 0, "accuracy": 0.0}},
        "results": [],
    }
    write_json(tmp_path / "compare.json", payload)

    runs = load_eval_runs(tmp_path)

    assert len(runs) == 1
    assert runs[0]["kind"] == "comparison"
    assert runs[0]["rule_field_accuracy"] == payload["rule_field_accuracy"]
    assert runs[0]["ai_field_accuracy"] == payload["ai_field_accuracy"]


def test_write_dashboard_writes_static_html(tmp_path):
    write_json(tmp_path / "run.json", run_payload())
    output = tmp_path / "dashboard.html"

    path = write_dashboard(tmp_path, output)

    assert path == output
    assert output.exists()
    assert "Warp ticket eval dashboard" in output.read_text(encoding="utf-8")


def test_render_dashboard_html_handles_empty_runs():
    html = render_dashboard_html([])

    assert "No eval run JSON files found." in html
