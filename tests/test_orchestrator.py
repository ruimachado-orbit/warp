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
