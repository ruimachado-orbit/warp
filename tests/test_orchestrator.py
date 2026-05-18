import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import orchestrator


def test_default_routes_to_triage_and_knowledge():
    tools = orchestrator.analyze_context("customer asks how to configure SSO")
    assert "support_triage" in tools


def test_zendesk_route():
    tools = orchestrator.analyze_context("search Zendesk for urgent tickets")
    assert "zendesk" in tools


def test_single_forced_llm_provider_error_is_not_hidden(monkeypatch):
    monkeypatch.setattr(orchestrator, "get", lambda key, default=None: ["codex_app_server"] if key == "llm.providers" else default)
    monkeypatch.setattr(
        orchestrator,
        "call_with_fallback",
        lambda *args, **kwargs: {
            "ok": False,
            "error": "All providers failed: codex_app_server: Unsupported Codex app-server transport: ws://127.0.0.1:3030",
            "warnings": [{"provider": "codex_app_server", "error": "Unsupported Codex app-server transport: ws://127.0.0.1:3030"}],
        },
    )

    response = orchestrator.llm_synthesize("triage this", [], quiet=True)

    assert response.startswith("LLM provider error:")
    assert "codex_app_server" in response
    assert "Unsupported Codex app-server transport" in response
