"""Packaged Warp command-line interface."""

import sys
try:
    import typer
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("⚠️  Missing CLI dependencies. Install with:")
    print("pip install typer rich")
    sys.exit(1)

from llm_gateway import status as llm_status
from orchestrator import orchestrate
from evals.cli import register_eval_commands

app = typer.Typer(
    help="Autonomous customer support operations agent for triage, classification, routing, drafting, knowledge lookup, SLA management, and helpdesk automation."
)
console = Console()
register_eval_commands(app, console)


@app.command()
def chat():
    """Interactive chat with Warp."""
    console.print(Panel.fit(
        "[bold cyan]Warp[/bold cyan]\n\n"
        "Autonomous customer support operations agent for triage, classification, routing, drafting, knowledge lookup, SLA management, and helpdesk automation.\n\n"
        "Type 'exit' to quit.",
        border_style="cyan"
    ))

    while True:
        try:
            query = console.input("\n[bold cyan]You:[/bold cyan] ")
            if query.lower() in ("exit", "quit", "q"):
                console.print("[yellow]Goodbye![/yellow]")
                break

            if not query.strip():
                continue

            console.print()
            response = orchestrate(query, quiet=True)
            console.print(f"[bold green]Warp:[/bold green] {response}\n")

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Goodbye![/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@app.command()
def status():
    """Show integration status."""
    st = llm_status()

    console.print("\n[bold]LLM Providers:[/bold]\n")
    table = Table()
    table.add_column("Provider", style="cyan")
    table.add_column("Status", style="white")

    for provider_id, info in st["providers"].items():
        status_icon = "✓" if info["configured"] else "✗"
        status_style = "green" if info["configured"] else "red"
        table.add_row(info["name"], f"[{status_style}]{status_icon}[/{status_style}]")

    console.print(table)
    console.print()


@app.command()
def query(text: str):
    """Run a single query."""
    response = orchestrate(text)
    console.print(response)


def main():
    """Run the Warp CLI."""
    app()


if __name__ == "__main__":
    main()
