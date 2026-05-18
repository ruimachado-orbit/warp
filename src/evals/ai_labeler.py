"""AI ticket labeler and eval comparison lane using Warp's LLM gateway."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any

import llm_gateway
from . import rule
from ticket_model import (
    CATEGORY_VALUES,
    SENTIMENT_VALUES,
    SEVERITY_VALUES,
    ClassificationResult,
    TicketEvalCase,
    TicketEvalResult,
    TicketInput,
    fallback_classification,
    utc_now_iso,
)

DEFAULT_PROVIDER = "openrouter"
DEFAULT_MAX_WORKERS = 5
AI_EVAL_MODE = "ai"
COMPARE_SCHEMA_VERSION = "warp.ticket_eval_compare.v1"


class AILabelerObservabilityError(ValueError):
    """AI labeler parse/validation error carrying raw provider observability."""

    def __init__(self, message: str, observability: dict[str, Any]) -> None:
        super().__init__(message)
        self.observability = observability


ROUTE_VALUES = {
    "Billing / Finance Support",
    "Technical Support L2",
    "Identity & Account Support",
    "Customer Education / L1 Support",
    "Product Feedback Queue",
    "Privacy / Legal Ops",
    "Integrations Support",
    "Customer Support L1",
}

SYSTEM_PROMPT = """You label customer support tickets for Warp.
Return valid JSON only. Do not include markdown fences, commentary, or extra text."""


def _format_allowed(values: set[str]) -> str:
    return ", ".join(sorted(values))


def build_label_prompt(ticket: TicketInput) -> str:
    """Build the JSON-only prompt for labeling one ticket."""
    metadata = json.dumps(ticket.metadata, ensure_ascii=False, sort_keys=True)
    routes = "; ".join(sorted(ROUTE_VALUES))
    return f"""Classify this support ticket and return one JSON object only.

JSON fields (`metadata` is optional):
{{
  "category": "one allowed category",
  "severity": "one allowed severity",
  "priority": "one allowed priority",
  "sentiment": "one allowed sentiment",
  "language": "BCP-47 language code such as en or pt",
  "route_to": "one exact route name",
  "sla_hours": 24,
  "requires_human": true,
  "confidence": 0.85,
  "tags": ["short", "lowercase", "tags"],
  "metadata": {{}}
}}

Allowed category values: {_format_allowed(CATEGORY_VALUES)}
Allowed severity values: {_format_allowed(SEVERITY_VALUES)}
Allowed priority values: {_format_allowed(SEVERITY_VALUES)}
Allowed sentiment values: {_format_allowed(SENTIMENT_VALUES)}
Use exact route_to values from this list only: {routes}.
Do not invent enum values or route names.

Ticket ID: {ticket.id}
Source: {ticket.source}
Channel: {ticket.channel or ""}
Requester ID: {ticket.requester_id or ""}
Account ID: {ticket.account_id or ""}
Created at: {ticket.created_at or ""}
Ticket language hint: {ticket.language or ""}
Subject: {ticket.subject}

Body:
{ticket.body}

Metadata:
{metadata}"""


def _parse_llm_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed LLM JSON response: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("malformed LLM JSON response: expected a JSON object")
    return data


def _validate_ai_classification(data: dict[str, Any]) -> ClassificationResult:
    try:
        actual = ClassificationResult.from_dict(data)
    except Exception as exc:
        raise ValueError(f"invalid LLM classification: {exc}") from exc
    if actual.route_to not in ROUTE_VALUES:
        raise ValueError(
            f"invalid LLM classification: route_to must be one of {sorted(ROUTE_VALUES)}, got {actual.route_to}"
        )
    return actual


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in {"key", "api_key", "apikey", "token", "authorization", "password", "secret"}
        or lowered.endswith(("_key", "_token", "_secret"))
        or lowered.startswith(("authorization", "password", "secret"))
    )


def _sanitize_gateway_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_gateway_value(item)
            for key, item in value.items()
            if not _is_sensitive_key(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_gateway_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _gateway_observability(result: dict[str, Any]) -> dict[str, Any]:
    """Return useful gateway metadata without duplicating raw text or secrets."""
    return {
        str(key): _sanitize_gateway_value(value)
        for key, value in result.items()
        if key != "text" and not _is_sensitive_key(str(key))
    }


def _label_ticket_with_observability(
    ticket: TicketInput, provider: str = DEFAULT_PROVIDER
) -> tuple[ClassificationResult, dict[str, Any]]:
    """Label one ticket and return parsed labels plus raw LLM observability metadata."""
    prompt = build_label_prompt(ticket)
    result = llm_gateway.call_with_fallback(
        prompt,
        providers=[provider],
        system=SYSTEM_PROMPT,
        max_tokens=2000,
        temperature=0.0,
        json_output=True,
    )
    if not result.get("ok"):
        raise RuntimeError(
            f"LLM provider {provider} failed: {result.get('error') or 'unknown error'}"
        )

    raw_text = str(result.get("text") or "")
    resolved_provider = result.get("provider") or provider
    observability = {
        "provider": resolved_provider,
        "model": result.get("model"),
        "source": f"llm:{resolved_provider}",
        "llm_prompt": prompt,
        "llm_system": SYSTEM_PROMPT,
        "llm_raw_text": raw_text,
        "llm_gateway": _gateway_observability(result),
    }
    try:
        data = _parse_llm_json(raw_text)
        actual = _validate_ai_classification(data)
    except ValueError as exc:
        raise AILabelerObservabilityError(str(exc), observability) from exc
    return actual, observability


def label_ticket(ticket: TicketInput, provider: str = DEFAULT_PROVIDER) -> ClassificationResult:
    """Label one ticket with the configured LLM gateway provider."""
    actual, _metadata = _label_ticket_with_observability(ticket, provider=provider)
    return actual


def evaluate_case(case: TicketEvalCase, provider: str = DEFAULT_PROVIDER) -> TicketEvalResult:
    """Evaluate one ticket case with the AI labeler."""
    metadata: dict[str, Any] = {
        "mode": AI_EVAL_MODE,
        "source": f"llm:{provider}",
        "provider": provider,
    }
    try:
        actual, observability = _label_ticket_with_observability(case.ticket, provider=provider)
        metadata.update({key: value for key, value in observability.items() if value is not None})
    except AILabelerObservabilityError as exc:
        metadata.update({key: value for key, value in exc.observability.items() if value is not None})
        return TicketEvalResult(
            case_id=case.case_id,
            actual=fallback_classification(),
            expected=case.expected,
            passed=False,
            failures=[f"ai_labeler_error: {exc}"],
            metadata={**metadata, "field_results": {}},
        )
    except RuntimeError as exc:
        return TicketEvalResult(
            case_id=case.case_id,
            actual=fallback_classification(),
            expected=case.expected,
            passed=False,
            failures=[f"ai_labeler_error: {exc}"],
            metadata={**metadata, "field_results": {}},
        )

    passed, failures, field_results = rule.score_classification(actual, case.expected)
    metadata["field_results"] = field_results
    return TicketEvalResult(
        case_id=case.case_id,
        actual=actual,
        expected=case.expected,
        passed=passed,
        failures=failures,
        metadata=metadata,
    )


def evaluate_file(path: str | Path, provider: str = DEFAULT_PROVIDER) -> dict[str, Any]:
    """Evaluate all ticket cases in a fixture file with AI labels."""
    cases = rule.load_eval_cases(path)
    with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as executor:
        results = list(executor.map(partial(evaluate_case, provider=provider), cases))
    passed = sum(1 for result in results if result.passed)
    total = len(results)
    failed = total - passed
    pass_rate = passed / total if total else 0.0
    return {
        "ok": failed == 0,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "provider": provider,
        "mode": AI_EVAL_MODE,
        "source": f"llm:{provider}",
        "field_accuracy": rule.aggregate_field_accuracy(results),
        "results": [rule.eval_result_to_dict(result) for result in results],
    }


def evaluate_run(
    path: str | Path,
    *,
    provider: str = DEFAULT_PROVIDER,
    run_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Evaluate a fixture with AI labels and return a persisted-run-ready payload."""
    summary = evaluate_file(path, provider=provider)
    return rule.build_eval_run_payload(
        path,
        summary,
        mode=AI_EVAL_MODE,
        source=f"llm:{provider}",
        run_id=run_id,
        generated_at=generated_at,
    )


def compare_file(path: str | Path, provider: str = DEFAULT_PROVIDER) -> dict[str, Any]:
    """Run rule and AI eval for the same fixture and return a serializable comparison."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        rule_future = executor.submit(rule.evaluate_file, path)
        ai_future = executor.submit(evaluate_file, path, provider=provider)
        rule_summary = rule_future.result()
        ai_summary = ai_future.result()
    ai_by_case = {result["case_id"]: result for result in ai_summary["results"]}

    results: list[dict[str, Any]] = []
    for rule_result in rule_summary["results"]:
        case_id = rule_result["case_id"]
        ai_result = ai_by_case.get(case_id)
        rule_metadata = rule_result.get("metadata") or {}
        ai_metadata = ai_result.get("metadata") if ai_result else {}
        if not isinstance(rule_metadata, dict):
            rule_metadata = {}
        if not isinstance(ai_metadata, dict):
            ai_metadata = {}
        results.append(
            {
                "case_id": case_id,
                "expected": rule_result.get("expected"),
                "rule": {
                    "actual": rule_result.get("actual"),
                    "passed": bool(rule_result.get("passed")),
                    "failures": rule_result.get("failures", []),
                    "field_results": rule_result.get("field_results", rule_metadata.get("field_results", {})),
                },
                "ai": {
                    "actual": ai_result.get("actual") if ai_result else None,
                    "passed": bool(ai_result.get("passed")) if ai_result else False,
                    "failures": ai_result.get("failures", ["missing AI result"]) if ai_result else ["missing AI result"],
                    "field_results": ai_result.get("field_results", ai_metadata.get("field_results", {})) if ai_result else {},
                },
                "rule_passed": bool(rule_result.get("passed")),
                "ai_passed": bool(ai_result.get("passed")) if ai_result else False,
            }
        )

    return {
        "schema_version": COMPARE_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "fixture_path": str(path),
        "provider": provider,
        "rule_source": rule.DEFAULT_EVAL_SOURCE,
        "ai_source": f"llm:{provider}",
        "ok": bool(rule_summary["ok"] and ai_summary["ok"]),
        "total": int(rule_summary["total"]),
        "rule_passed": int(rule_summary["passed"]),
        "rule_failed": int(rule_summary["failed"]),
        "ai_passed": int(ai_summary["passed"]),
        "ai_failed": int(ai_summary["failed"]),
        "rule_pass_rate": float(rule_summary["pass_rate"]),
        "ai_pass_rate": float(ai_summary["pass_rate"]),
        "rule_field_accuracy": rule_summary.get("field_accuracy", {}),
        "ai_field_accuracy": ai_summary.get("field_accuracy", {}),
        "results": results,
    }


def write_compare_json(payload: dict[str, Any], output_path: str | Path) -> Path:
    """Write a comparison payload as stable, pretty JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


__all__ = [
    "DEFAULT_PROVIDER",
    "AI_EVAL_MODE",
    "ROUTE_VALUES",
    "build_label_prompt",
    "label_ticket",
    "evaluate_case",
    "evaluate_file",
    "evaluate_run",
    "compare_file",
    "write_compare_json",
]
