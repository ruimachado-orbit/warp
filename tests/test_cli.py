import ast
import json
import sys
from pathlib import Path

from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cli
from evals import ai_labeler as ai_ticket_labeler
from evals import dashboard as eval_dashboard
from evals import incident_clusterer
from evals import rule as ticket_eval
from evals import store as eval_ticket_store

runner = CliRunner()


def test_packaged_cli_entrypoint_is_importable():
    assert callable(cli.main)


def test_query_command_uses_orchestrator(monkeypatch):
    def fake_orchestrate(text, quiet=False):
        assert text == "hello"
        assert quiet is False
        return "orchestrated response"

    monkeypatch.setattr(cli, "orchestrate", fake_orchestrate)

    result = runner.invoke(cli.app, ["query", "hello"])

    assert result.exit_code == 0
    assert "orchestrated response" in result.output


def test_status_command_uses_llm_status(monkeypatch):
    monkeypatch.setattr(
        cli,
        "llm_status",
        lambda: {"providers": {"openai": {"name": "OpenAI", "configured": True}}},
    )

    result = runner.invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "LLM Providers" in result.output
    assert "OpenAI" in result.output


def test_eval_command_returns_zero_when_fixture_passes(monkeypatch):
    monkeypatch.setattr(
        ticket_eval,
        "evaluate_file",
        lambda path: {
            "ok": True,
            "total": 2,
            "passed": 2,
            "failed": 0,
            "pass_rate": 1.0,
            "results": [],
        },
    )

    result = runner.invoke(cli.app, ["eval", "fixture.json"])

    assert result.exit_code == 0
    assert "Ticket eval" in result.output
    assert "Total" in result.output
    assert "Passed" in result.output
    assert "Failed" in result.output
    assert "100%" in result.output


def test_eval_command_returns_one_when_fixture_fails(monkeypatch):
    monkeypatch.setattr(
        ticket_eval,
        "evaluate_file",
        lambda path: {
            "ok": False,
            "total": 1,
            "passed": 0,
            "failed": 1,
            "pass_rate": 0.0,
            "results": [
                {
                    "case_id": "bad_case",
                    "passed": False,
                    "failures": ["category expected billing got bug"],
                }
            ],
        },
    )

    result = runner.invoke(cli.app, ["eval", "fixture.json"])

    assert result.exit_code == 1
    assert "bad_case failed" in result.output
    assert "category expected billing got bug" in result.output


def test_eval_command_writes_json_and_markdown_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ticket_eval,
        "evaluate_file",
        lambda path: {
            "ok": True,
            "total": 1,
            "passed": 1,
            "failed": 0,
            "pass_rate": 1.0,
            "results": [
                {
                    "case_id": "good_case",
                    "expected": {
                        "category": "billing",
                        "severity": "medium",
                        "route_to": "Billing / Finance Support",
                        "sla_hours": 24,
                        "requires_human": True,
                    },
                    "actual": {
                        "category": "billing",
                        "severity": "medium",
                        "route_to": "Billing / Finance Support",
                        "sla_hours": 24,
                        "requires_human": True,
                    },
                    "passed": True,
                    "failures": [],
                }
            ],
        },
    )
    json_path = tmp_path / "run.json"
    markdown_path = tmp_path / "run.md"

    result = runner.invoke(
        cli.app,
        [
            "eval",
            "fixture.json",
            "--output",
            str(json_path),
            "--markdown",
            str(markdown_path),
        ],
    )

    assert result.exit_code == 0
    assert "Wrote artifact" in result.output
    assert json.loads(json_path.read_text())["fixture_path"] == "fixture.json"
    assert "good_case" in markdown_path.read_text()


def test_eval_command_writes_artifacts_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ticket_eval,
        "evaluate_file",
        lambda path: {
            "ok": True,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "pass_rate": 0.0,
            "results": [],
        },
    )

    result = runner.invoke(
        cli.app,
        ["eval", "fixture.json", "--artifacts-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Wrote artifact" in result.output
    assert (tmp_path / "latest.json").exists()
    assert list(tmp_path.glob("ticket-eval-*.json"))
    assert list(tmp_path.glob("ticket-eval-*.md"))


def test_eval_ai_command_returns_zero_and_writes_artifacts(monkeypatch, tmp_path):
    def fake_evaluate_file(path, provider="openrouter"):
        assert path == "fixture.json"
        assert provider == "openrouter"
        return {
            "ok": True,
            "total": 1,
            "passed": 1,
            "failed": 0,
            "pass_rate": 1.0,
            "results": [
                {
                    "case_id": "good_case",
                    "expected": {"category": "billing"},
                    "actual": {"category": "billing"},
                    "passed": True,
                    "failures": [],
                }
            ],
        }

    monkeypatch.setattr(ai_ticket_labeler, "evaluate_file", fake_evaluate_file)
    json_path = tmp_path / "ai-run.json"
    markdown_path = tmp_path / "ai-run.md"

    result = runner.invoke(
        cli.app,
        [
            "eval-ai",
            "fixture.json",
            "--provider",
            "openrouter",
            "--output",
            str(json_path),
            "--markdown",
            str(markdown_path),
        ],
    )

    assert result.exit_code == 0
    assert "AI ticket eval" in result.output
    assert "Wrote artifact" in result.output
    saved = json.loads(json_path.read_text())
    assert saved["mode"] == "ai"
    assert saved["source"] == "llm:openrouter"
    assert "good_case" in markdown_path.read_text()


def test_eval_ai_command_returns_one_when_ai_eval_fails(monkeypatch):
    monkeypatch.setattr(
        ai_ticket_labeler,
        "evaluate_file",
        lambda path, provider="openrouter": {
            "ok": False,
            "total": 1,
            "passed": 0,
            "failed": 1,
            "pass_rate": 0.0,
            "results": [
                {
                    "case_id": "bad_ai_case",
                    "passed": False,
                    "failures": ["ai_labeler_error: LLM provider openrouter failed"],
                }
            ],
        },
    )

    result = runner.invoke(cli.app, ["eval-ai", "fixture.json"])

    assert result.exit_code == 1
    assert "bad_ai_case failed" in result.output
    assert "LLM provider openrouter failed" in result.output


def test_eval_compare_command_writes_json(monkeypatch, tmp_path):
    def fake_compare_file(path, provider="openrouter"):
        assert path == "fixture.json"
        assert provider == "openrouter"
        return {
            "schema_version": "warp.ticket_eval_compare.v1",
            "ok": True,
            "total": 1,
            "rule_passed": 1,
            "rule_failed": 0,
            "ai_passed": 1,
            "ai_failed": 0,
            "results": [],
        }

    monkeypatch.setattr(ai_ticket_labeler, "compare_file", fake_compare_file)
    output = tmp_path / "compare.json"

    result = runner.invoke(
        cli.app,
        ["eval-compare", "fixture.json", "--provider", "openrouter", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert "Ticket eval comparison" in result.output
    assert "Wrote artifact" in result.output
    assert json.loads(output.read_text())["schema_version"] == "warp.ticket_eval_compare.v1"


def test_eval_cluster_incidents_command_writes_json(monkeypatch, tmp_path):
    def fake_evaluate_file(path, provider="openrouter", model="deepseek/deepseek-v4-flash"):
        assert path == "fixture.json"
        assert provider == "openrouter"
        assert model == "deepseek/deepseek-v4-flash"
        return {
            "schema_version": "warp.incident_cluster_eval_result.v1",
            "ok": True,
            "total_tickets": 3,
            "expected_cluster_count": 2,
            "predicted_cluster_count": 2,
            "metrics": {
                "pairwise_precision": 1.0,
                "pairwise_recall": 1.0,
                "pairwise_f1": 1.0,
            },
            "predicted_clusters": [],
        }

    monkeypatch.setattr(incident_clusterer, "evaluate_file", fake_evaluate_file)
    output = tmp_path / "clusters.json"

    result = runner.invoke(
        cli.app,
        ["eval-cluster-incidents", "fixture.json", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert "Incident cluster eval" in result.output
    assert "Wrote artifact" in result.output
    assert json.loads(output.read_text())["schema_version"] == "warp.incident_cluster_eval_result.v1"


def test_eval_cluster_incidents_command_returns_one_when_f1_is_not_perfect(monkeypatch):
    monkeypatch.setattr(
        incident_clusterer,
        "evaluate_file",
        lambda path, provider="openrouter", model="deepseek/deepseek-v4-flash": {
            "ok": False,
            "total_tickets": 3,
            "expected_cluster_count": 2,
            "predicted_cluster_count": 1,
            "metrics": {
                "pairwise_precision": 0.5,
                "pairwise_recall": 1.0,
                "pairwise_f1": 2 / 3,
            },
        },
    )

    result = runner.invoke(cli.app, ["eval-cluster-incidents", "fixture.json"])

    assert result.exit_code == 1
    assert "Incident cluster eval" in result.output
    assert "67%" in result.output


def test_eval_compare_command_returns_one_when_any_lane_fails(monkeypatch):
    monkeypatch.setattr(
        ai_ticket_labeler,
        "compare_file",
        lambda path, provider="openrouter": {
            "ok": False,
            "total": 1,
            "rule_passed": 1,
            "rule_failed": 0,
            "ai_passed": 0,
            "ai_failed": 1,
            "results": [
                {
                    "case_id": "bad_ai_case",
                    "rule_passed": True,
                    "ai_passed": False,
                    "rule": {"failures": []},
                    "ai": {"failures": ["ai_labeler_error: bad json"]},
                }
            ],
        },
    )

    result = runner.invoke(cli.app, ["eval-compare", "fixture.json"])

    assert result.exit_code == 1
    assert "bad_ai_case" in result.output
    assert "ai_labeler_error: bad json" in result.output


def test_eval_command_writes_ticket_store(monkeypatch, tmp_path):
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "good_case",
                        "ticket": {"id": "T-1", "subject": "Hello", "source": "synthetic"},
                        "expected": {"category": "billing"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ticket_eval,
        "evaluate_file",
        lambda path: {
            "ok": True,
            "total": 1,
            "passed": 1,
            "failed": 0,
            "pass_rate": 1.0,
            "results": [
                {
                    "case_id": "good_case",
                    "expected": {"category": "billing"},
                    "actual": {"category": "billing"},
                    "passed": True,
                    "failures": [],
                }
            ],
        },
    )
    tickets_dir = tmp_path / "tickets"

    result = runner.invoke(
        cli.app,
        ["eval", str(fixture_path), "--tickets-dir", str(tickets_dir)],
    )

    assert result.exit_code == 0
    run_dirs = [p for p in tickets_dir.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    saved = json.loads((run_dirs[0] / "tickets" / "good_case.json").read_text())
    assert saved["ticket"]["subject"] == "Hello"
    assert saved["evaluations"][0]["mode"] == "rule"



def test_eval_dashboard_command_writes_html(monkeypatch, tmp_path):
    output = tmp_path / "dashboard.html"

    def fake_write_dashboard(runs_dir, output_path):
        assert runs_dir == "runs"
        assert output_path == str(output)
        output.write_text("<html></html>", encoding="utf-8")
        return output

    monkeypatch.setattr(eval_dashboard, "write_dashboard", fake_write_dashboard)

    result = runner.invoke(
        cli.app,
        ["eval-dashboard", "--runs-dir", "runs", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert "Wrote dashboard" in result.output
    assert output.exists()


def test_eval_store_command_converts_run_artifacts(tmp_path):
    runs_dir = tmp_path / "runs"
    tickets_dir = tmp_path / "tickets"
    fixtures_dir = tmp_path / "fixtures"
    runs_dir.mkdir()
    fixtures_dir.mkdir()
    fixture_path = fixtures_dir / "cases.json"
    fixture_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "cli_case",
                        "ticket": {"id": "T-1", "subject": "CLI ticket", "source": "synthetic"},
                        "expected": {"category": "billing"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (runs_dir / "run.json").write_text(
        json.dumps(
            {
                "schema_version": "warp.ticket_eval_run.v1",
                "run_id": "cli-run",
                "generated_at": "2026-01-02T03:04:05+00:00",
                "fixture_path": str(fixture_path),
                "mode": "rule",
                "source": "no-LLM orchestrator",
                "results": [
                    {
                        "case_id": "cli_case",
                        "expected": {"category": "billing"},
                        "actual": {"category": "billing"},
                        "passed": True,
                        "failures": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        cli.app,
        [
            "eval-store",
            "--runs-dir",
            str(runs_dir),
            "--fixtures",
            str(fixtures_dir),
            "--tickets-dir",
            str(tickets_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Wrote ticket artifacts" in result.output
    saved = json.loads((tickets_dir / "cli-run" / "tickets" / "cli_case.json").read_text())
    assert saved["ticket"]["subject"] == "CLI ticket"
    assert saved["evaluations"][0]["run_id"] == "cli-run"



def test_packaging_declares_warp_console_entrypoint_modules_and_packages():
    setup_tree = ast.parse((ROOT / "setup.py").read_text())
    setup_call = next(
        node
        for node in ast.walk(setup_tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup"
    )
    kwargs = {
        keyword.arg: ast.literal_eval(keyword.value)
        for keyword in setup_call.keywords
        if keyword.arg in {"entry_points", "py_modules"}
    }
    package_keyword = next(
        keyword for keyword in setup_call.keywords if keyword.arg == "packages"
    )

    assert "warp=cli:main" in kwargs["entry_points"]["console_scripts"]
    assert {
        "cli",
        "config",
        "llm_gateway",
        "orchestrator",
        "ticket_model",
    }.issubset(kwargs["py_modules"])
    assert isinstance(package_keyword.value, ast.Call)
    assert getattr(package_keyword.value.func, "id", None) == "find_packages"
