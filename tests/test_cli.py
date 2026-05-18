import ast
import sys
from pathlib import Path

from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cli

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


def test_packaging_declares_warp_console_entrypoint_and_modules():
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

    assert "warp=cli:main" in kwargs["entry_points"]["console_scripts"]
    assert {"cli", "config", "llm_gateway", "orchestrator"}.issubset(kwargs["py_modules"])
