#!/usr/bin/env python3
"""End-to-end test suite for Warp agent"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from orchestrator import orchestrate, analyze_context
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src" / "tools"))
from support_triage import classify

def test_category_detection():
    """Test that categories are detected correctly"""
    tests = [
        ("Production is completely down with error 500", "bug"),
        ("I am angry about this wrong invoice charge", "billing"),
        ("How do I configure SSO for my team?", "how_to"),
        ("Please delete my personal data per GDPR", "data_privacy"),
        ("API webhook is returning 401 unauthorized", "integration"),
    ]

    passed = 0
    for text, expected_category in tests:
        result = classify(text)
        actual = result["category"]
        status = "✓" if actual == expected_category else "✗"
        print(f"{status} {text[:50]:50s} -> expected: {expected_category:15s} actual: {actual:15s}")
        if actual == expected_category:
            passed += 1

    return passed, len(tests)

def test_severity_detection():
    """Test that severity is detected correctly"""
    tests = [
        ("Production is down all users blocked", "critical"),
        ("Urgent issue with payment processing", "high"),
        ("Button label is slightly misaligned", "low"),
    ]

    passed = 0
    for text, expected_severity in tests:
        result = classify(text)
        actual = result["severity"]
        status = "✓" if actual == expected_severity else "✗"
        print(f"{status} {text[:50]:50s} -> expected: {expected_severity:10s} actual: {actual:10s}")
        if actual == expected_severity:
            passed += 1

    return passed, len(tests)

def test_sentiment_detection():
    """Test that sentiment is detected correctly"""
    tests = [
        ("I am frustrated and angry about this terrible service", "negative"),
        ("Thanks for the great help, you are awesome!", "positive"),
        ("I need help with my account settings", "neutral"),
    ]

    passed = 0
    for text, expected_sentiment in tests:
        result = classify(text)
        actual = result["sentiment"]
        status = "✓" if actual == expected_sentiment else "✗"
        print(f"{status} {text[:50]:50s} -> expected: {expected_sentiment:10s} actual: {actual:10s}")
        if actual == expected_sentiment:
            passed += 1

    return passed, len(tests)

def test_tool_routing():
    """Test that tools are routed correctly based on context"""
    tests = [
        ("triage this ticket", ["support_triage"]),
        ("search Zendesk for urgent tickets", ["zendesk"]),
        ("search knowledge base for refund policy", ["knowledge"]),
    ]

    passed = 0
    for text, expected_tools in tests:
        actual = analyze_context(text)
        # Check if all expected tools are in actual
        match = all(tool in actual for tool in expected_tools)
        status = "✓" if match else "✗"
        print(f"{status} {text[:50]:50s} -> expected: {expected_tools} actual: {actual}")
        if match:
            passed += 1

    return passed, len(tests)

def test_orchestration():
    """Test full orchestration without LLM"""
    print("\n=== Full Orchestration Test ===")
    result = orchestrate("triage: urgent billing issue with angry customer", use_llm=False, quiet=True)
    print(result[:500])
    return 1, 1  # Just check it doesn't crash

if __name__ == "__main__":
    print("=" * 80)
    print("Warp Agent End-to-End Test Suite")
    print("=" * 80)

    total_passed = 0
    total_tests = 0

    print("\n=== Category Detection ===")
    passed, tests = test_category_detection()
    total_passed += passed
    total_tests += tests

    print("\n=== Severity Detection ===")
    passed, tests = test_severity_detection()
    total_passed += passed
    total_tests += tests

    print("\n=== Sentiment Detection ===")
    passed, tests = test_sentiment_detection()
    total_passed += passed
    total_tests += tests

    print("\n=== Tool Routing ===")
    passed, tests = test_tool_routing()
    total_passed += passed
    total_tests += tests

    passed, tests = test_orchestration()
    total_passed += passed
    total_tests += tests

    print("\n" + "=" * 80)
    print(f"Results: {total_passed}/{total_tests} tests passed")
    print("=" * 80)

    sys.exit(0 if total_passed == total_tests else 1)
