"""Evaluation-related CLI commands for Warp.

Kept separate from the general CLI entrypoint so eval workflows can evolve
without polluting `src/cli.py`.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table


def register_eval_commands(app: typer.Typer, console: Console) -> None:
    """Register evaluation commands on the main Warp Typer app."""
    @app.command("eval-ai")
    def eval_ai_command(
        path: str,
        provider: str = typer.Option(
            "openrouter",
            "--provider",
            "-p",
            help="LLM gateway provider to use for AI labels.",
        ),
        output: str | None = typer.Option(
            None,
            "--output",
            "-o",
            help="Write the AI eval run JSON artifact to this path.",
        ),
        markdown: str | None = typer.Option(
            None,
            "--markdown",
            "-m",
            help="Write a Markdown AI eval summary to this path.",
        ),
        artifacts_dir: str | None = typer.Option(
            None,
            "--artifacts-dir",
            help="Write timestamped JSON/Markdown artifacts and latest.json in this directory.",
        ),
        tickets_dir: str | None = typer.Option(
            None,
            "--tickets-dir",
            help="Write/update one JSON artifact per eval case under this run-store directory.",
        ),
    ):
        """Run ticket eval cases through the AI ticket labeler."""
        artifact_paths: list[Path] = []
        try:
            from .ai_labeler import evaluate_file
            from .rule import (
                build_eval_run_payload,
                write_eval_artifacts,
                write_eval_run_json,
                write_eval_run_markdown,
            )
            from .store import upsert_eval_run_payload

            summary = evaluate_file(path, provider=provider)
            if output or markdown or artifacts_dir or tickets_dir:
                payload = build_eval_run_payload(
                    path,
                    summary,
                    mode="ai",
                    source=f"llm:{provider}",
                )
                if output:
                    artifact_paths.append(write_eval_run_json(payload, output))
                if markdown:
                    artifact_paths.append(write_eval_run_markdown(payload, markdown))
                if artifacts_dir:
                    artifact_paths.extend(write_eval_artifacts(payload, artifacts_dir).values())
                if tickets_dir:
                    artifact_paths.extend(upsert_eval_run_payload(payload, tickets_dir, fixtures=path))
        except Exception as exc:
            console.print(f"[red]AI eval error: {exc}[/red]")
            raise typer.Exit(code=2) from exc

        table = Table(title="AI ticket eval")
        table.add_column("Provider", style="cyan")
        table.add_column("Total", justify="right")
        table.add_column("Passed", justify="right", style="green")
        table.add_column("Failed", justify="right", style="red")
        table.add_column("Pass rate", justify="right")
        table.add_row(
            provider,
            str(summary["total"]),
            str(summary["passed"]),
            str(summary["failed"]),
            f"{summary['pass_rate']:.0%}",
        )
        console.print(table)

        for artifact_path in artifact_paths:
            console.print(f"[green]Wrote artifact:[/green] {artifact_path}")

        for result in summary["results"]:
            if not result["passed"]:
                console.print(f"[red]{result['case_id']} failed[/red]")
                for failure in result["failures"]:
                    console.print(f"  - {failure}")

        if not summary["ok"]:
            raise typer.Exit(code=1)


    @app.command("eval-compare")
    def eval_compare_command(
        path: str,
        provider: str = typer.Option(
            "openrouter",
            "--provider",
            "-p",
            help="LLM gateway provider to use for AI labels.",
        ),
        output: str | None = typer.Option(
            None,
            "--output",
            "-o",
            help="Write the comparison JSON artifact to this path.",
        ),
        tickets_dir: str | None = typer.Option(
            None,
            "--tickets-dir",
            help="Write/update one JSON artifact per compared case under this run-store directory.",
        ),
    ):
        """Compare rule-based eval results with AI labeler eval results."""
        artifact_paths: list[Path] = []
        try:
            from .ai_labeler import compare_file, write_compare_json
            from .store import upsert_comparison_payload

            summary = compare_file(path, provider=provider)
            if output:
                artifact_paths.append(write_compare_json(summary, output))
            if tickets_dir:
                artifact_paths.extend(upsert_comparison_payload(summary, tickets_dir, fixtures=path))
        except Exception as exc:
            console.print(f"[red]Eval compare error: {exc}[/red]")
            raise typer.Exit(code=2) from exc

        table = Table(title="Ticket eval comparison")
        table.add_column("Provider", style="cyan")
        table.add_column("Total", justify="right")
        table.add_column("Rule passed", justify="right", style="green")
        table.add_column("Rule failed", justify="right", style="red")
        table.add_column("AI passed", justify="right", style="green")
        table.add_column("AI failed", justify="right", style="red")
        table.add_row(
            provider,
            str(summary["total"]),
            str(summary["rule_passed"]),
            str(summary["rule_failed"]),
            str(summary["ai_passed"]),
            str(summary["ai_failed"]),
        )
        console.print(table)

        for artifact_path in artifact_paths:
            console.print(f"[green]Wrote artifact:[/green] {artifact_path}")

        for result in summary["results"]:
            if not result["rule_passed"] or not result["ai_passed"]:
                console.print(
                    f"[red]{result['case_id']}[/red] rule={'PASS' if result['rule_passed'] else 'FAIL'} ai={'PASS' if result['ai_passed'] else 'FAIL'}"
                )
                for failure in result["rule"].get("failures", []):
                    console.print(f"  - rule: {failure}")
                for failure in result["ai"].get("failures", []):
                    console.print(f"  - ai: {failure}")

        if not summary["ok"]:
            raise typer.Exit(code=1)


    @app.command("eval-cluster-incidents")
    def eval_cluster_incidents_command(
        path: str,
        provider: str = typer.Option(
            "openrouter",
            "--provider",
            "-p",
            help="LLM gateway provider to use for incident clustering.",
        ),
        model: str = typer.Option(
            "deepseek/deepseek-v4-flash",
            "--model",
            help="Model to use for incident clustering.",
        ),
        output: str | None = typer.Option(
            None,
            "--output",
            "-o",
            help="Write the incident clustering eval JSON artifact to this path.",
        ),
    ):
        """Cluster incident tickets with AI and score against expected clusters."""
        artifact_paths: list[Path] = []
        try:
            from .incident_clusterer import evaluate_file, write_eval_json

            summary = evaluate_file(path, provider=provider, model=model)
            if output:
                artifact_paths.append(write_eval_json(summary, output))
        except Exception as exc:
            console.print(f"[red]Incident cluster eval error: {exc}[/red]")
            raise typer.Exit(code=2) from exc

        metrics = summary["metrics"]
        table = Table(title="Incident cluster eval")
        table.add_column("Provider", style="cyan")
        table.add_column("Model", style="cyan")
        table.add_column("Tickets", justify="right")
        table.add_column("Expected clusters", justify="right")
        table.add_column("Predicted clusters", justify="right")
        table.add_column("Precision", justify="right")
        table.add_column("Recall", justify="right")
        table.add_column("F1", justify="right")
        table.add_row(
            provider,
            model,
            str(summary["total_tickets"]),
            str(summary["expected_cluster_count"]),
            str(summary["predicted_cluster_count"]),
            f"{metrics['pairwise_precision']:.0%}",
            f"{metrics['pairwise_recall']:.0%}",
            f"{metrics['pairwise_f1']:.0%}",
        )
        console.print(table)

        for artifact_path in artifact_paths:
            console.print(f"[green]Wrote artifact:[/green] {artifact_path}")

        if not summary["ok"]:
            raise typer.Exit(code=1)


    @app.command("eval-dashboard")
    def eval_dashboard_command(
        runs_dir: str = typer.Option(
            "eval-runs",
            "--runs-dir",
            help="Directory containing eval run JSON files and run-scoped ticket folders.",
        ),
        output: str = typer.Option(
            "eval-runs/dashboard.html",
            "--output",
            "-o",
            help="Write the static HTML dashboard to this path.",
        ),
    ):
        """Generate a static HTML dashboard for persisted ticket eval runs and ticket artifacts."""
        try:
            from .dashboard import write_dashboard

            dashboard_path = write_dashboard(runs_dir, output)
        except Exception as exc:
            console.print(f"[red]Eval dashboard error: {exc}[/red]")
            raise typer.Exit(code=2) from exc

        console.print(f"[green]Wrote dashboard:[/green] {dashboard_path}")


    @app.command("eval-store")
    def eval_store_command(
        runs_dir: str = typer.Option(
            "eval-runs",
            "--runs-dir",
            help="Directory containing persisted eval run or comparison JSON files.",
        ),
        fixtures: str | None = typer.Option(
            "tests/fixtures",
            "--fixtures",
            help="Fixture file or directory used to enrich ticket artifacts with ticket objects.",
        ),
        tickets_dir: str = typer.Option(
            "eval-runs",
            "--tickets-dir",
            help="Run-store directory; each eval run gets a folder with one JSON file per ticket.",
        ),
    ):
        """Convert eval run artifacts into run folders with one JSON file per ticket."""
        try:
            from .store import convert_runs_dir

            paths = convert_runs_dir(runs_dir, tickets_dir, fixtures=fixtures)
        except Exception as exc:
            console.print(f"[red]Eval store error: {exc}[/red]")
            raise typer.Exit(code=2) from exc

        console.print(f"[green]Wrote ticket artifacts:[/green] {len(paths)}")
        for artifact_path in paths:
            console.print(f"[green]Wrote artifact:[/green] {artifact_path}")


    @app.command("eval")
    def eval_command(
        path: str,
        output: str | None = typer.Option(
            None,
            "--output",
            "-o",
            help="Write the eval run JSON artifact to this path.",
        ),
        markdown: str | None = typer.Option(
            None,
            "--markdown",
            "-m",
            help="Write a Markdown eval summary to this path.",
        ),
        artifacts_dir: str | None = typer.Option(
            None,
            "--artifacts-dir",
            help="Write timestamped JSON/Markdown artifacts and latest.json in this directory.",
        ),
        tickets_dir: str | None = typer.Option(
            None,
            "--tickets-dir",
            help="Write/update one JSON artifact per eval case under this run-store directory.",
        ),
    ):
        """Run synthetic ticket eval cases from a JSON or JSONL fixture file."""
        artifact_paths: list[Path] = []
        try:
            from .rule import (
                build_eval_run_payload,
                evaluate_file,
                write_eval_artifacts,
                write_eval_run_json,
                write_eval_run_markdown,
            )
            from .store import upsert_eval_run_payload

            summary = evaluate_file(path)
            if output or markdown or artifacts_dir or tickets_dir:
                payload = build_eval_run_payload(path, summary)
                if output:
                    artifact_paths.append(write_eval_run_json(payload, output))
                if markdown:
                    artifact_paths.append(write_eval_run_markdown(payload, markdown))
                if artifacts_dir:
                    artifact_paths.extend(write_eval_artifacts(payload, artifacts_dir).values())
                if tickets_dir:
                    artifact_paths.extend(upsert_eval_run_payload(payload, tickets_dir, fixtures=path))
        except Exception as exc:
            console.print(f"[red]Eval error: {exc}[/red]")
            raise typer.Exit(code=2) from exc

        table = Table(title="Ticket eval")
        table.add_column("Total", justify="right")
        table.add_column("Passed", justify="right", style="green")
        table.add_column("Failed", justify="right", style="red")
        table.add_column("Pass rate", justify="right")
        table.add_row(
            str(summary["total"]),
            str(summary["passed"]),
            str(summary["failed"]),
            f"{summary['pass_rate']:.0%}",
        )
        console.print(table)

        for artifact_path in artifact_paths:
            console.print(f"[green]Wrote artifact:[/green] {artifact_path}")

        for result in summary["results"]:
            if not result["passed"]:
                console.print(f"[red]{result['case_id']} failed[/red]")
                for failure in result["failures"]:
                    console.print(f"  - {failure}")

        if not summary["ok"]:
            raise typer.Exit(code=1)
