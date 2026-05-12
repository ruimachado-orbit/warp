import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "tools"))
import support_triage


def test_critical_bug_routes_to_l2():
    result = support_triage.classify("Production is down and all users are blocked by an error")
    assert result["severity"] == "critical"
    assert result["category"] == "bug"
    assert result["route_to"] == "Technical Support L2"
    assert result["sla_hours"] == 1


def test_billing_negative():
    result = support_triage.classify("I am angry about this wrong invoice charge")
    assert result["category"] == "billing"
    assert result["sentiment"] == "negative"
    assert result["requires_human"] is True
