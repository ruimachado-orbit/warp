"""Synthetic ticket eval harness for Warp's current no-LLM orchestrator output."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import orchestrator
from ticket_model import (
    ClassificationResult,
    ExpectedClassification,
    TicketEvalCase,
    TicketEvalResult,
    TicketInput,
    fallback_classification,
    utc_now_iso,
)


EVAL_RUN_SCHEMA_VERSION = "warp.ticket_eval_run.v1"
DEFAULT_EVAL_MODE = "rule"
DEFAULT_EVAL_SOURCE = "no-LLM orchestrator"
DEFAULT_ARTIFACTS_DIR = "eval-runs"
SCALAR_SCORE_FIELDS = (
    "category",
    "severity",
    "priority",
    "sentiment",
    "language",
    "route_to",
    "sla_hours",
    "requires_human",
)


def render_ticket_goal(ticket: TicketInput) -> str:
    """Render a ticket into the existing plain-text orchestrator goal API."""
    metadata = json.dumps(ticket.metadata, ensure_ascii=False, sort_keys=True)
    lines = [
        "triage this support ticket",
        "",
        f"Ticket ID: {ticket.id}",
        f"Source: {ticket.source}",
        f"Channel: {ticket.channel or ''}",
        f"Subject: {ticket.subject}",
        "",
        "Body:",
        ticket.body,
        "",
        "Metadata:",
        metadata,
    ]
    return "\n".join(lines)


def _find_prefixed_line(lines: list[str], prefix: str) -> str:
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    raise ValueError(f"missing {prefix.rstrip(':')} line")


def parse_orchestrator_classification(output: str) -> ClassificationResult:
    """Parse the current no-LLM orchestrator text summary into a classification."""
    lines = [line.strip() for line in output.splitlines()]

    classification_value = _find_prefixed_line(lines, "Classification:")
    classification_parts = [part.strip() for part in classification_value.split("/")]
    if len(classification_parts) != 3 or not all(classification_parts):
        raise ValueError("malformed classification line")
    category, severity, sentiment = classification_parts

    route_to = _find_prefixed_line(lines, "Route:")

    sla_value = _find_prefixed_line(lines, "SLA:")
    sla_match = re.fullmatch(r"(\d+)h", sla_value)
    if not sla_match:
        raise ValueError("malformed SLA line")
    sla_hours = int(sla_match.group(1))

    tags_value = _find_prefixed_line(lines, "Tags:")
    tags = [tag.strip() for tag in tags_value.split(",") if tag.strip()] if tags_value else []

    human_value = _find_prefixed_line(lines, "Human required:").lower()
    if human_value not in {"true", "false"}:
        raise ValueError("malformed Human required line")
    requires_human = human_value == "true"

    language = "pt" if "pt" in tags else "en" if "en" in tags else "en"

    return ClassificationResult(
        category=category,
        severity=severity,
        priority=severity,
        sentiment=sentiment,
        language=language,
        route_to=route_to,
        sla_hours=sla_hours,
        requires_human=requires_human,
        confidence=0.0,
        tags=tags,
    )


def score_classification(
    actual: ClassificationResult,
    expected: ExpectedClassification,
) -> tuple[bool, list[str], dict[str, bool]]:
    """Score an actual classification against expected labels."""
    failures: list[str] = []
    field_results: dict[str, bool] = {}

    for field_name in SCALAR_SCORE_FIELDS:
        expected_value = getattr(expected, field_name)
        if expected_value is not None:
            actual_value = getattr(actual, field_name)
            field_passed = actual_value == expected_value
            field_results[field_name] = field_passed
            if not field_passed:
                failures.append(f"{field_name} expected {expected_value} got {actual_value}")

    if expected.allowed_categories and actual.category not in expected.allowed_categories:
        failures.append(
            f"category expected one of {expected.allowed_categories} got {actual.category}"
        )

    if expected.allowed_severities and actual.severity not in expected.allowed_severities:
        failures.append(
            f"severity expected one of {expected.allowed_severities} got {actual.severity}"
        )

    if expected.tags_exact is not None and sorted(actual.tags) != sorted(expected.tags_exact):
        failures.append(f"tags_exact expected {sorted(expected.tags_exact)} got {sorted(actual.tags)}")

    for tag in expected.tags_contains:
        if tag not in actual.tags:
            failures.append(f"tags_contains missing {tag}")

    if expected.min_confidence is not None and actual.confidence < expected.min_confidence:
        failures.append(
            f"min_confidence expected {expected.min_confidence} got {actual.confidence}"
        )

    return not failures, failures, field_results


def evaluate_case(case: TicketEvalCase) -> TicketEvalResult:
    """Evaluate one ticket case through orchestrator.orchestrate(..., use_llm=False)."""
    goal = render_ticket_goal(case.ticket)
    output = orchestrator.orchestrate(goal, use_llm=False, quiet=True)
    metadata: dict[str, Any] = {
        "goal": goal,
        "orchestrator_output": output,
    }

    try:
        actual = parse_orchestrator_classification(output)
    except ValueError as exc:
        return TicketEvalResult(
            case_id=case.case_id,
            actual=fallback_classification(),
            expected=case.expected,
            passed=False,
            failures=[f"parse_error: {exc}"],
            metadata={**metadata, "field_results": {}},
        )

    passed, failures, field_results = score_classification(actual, case.expected)
    metadata["field_results"] = field_results
    return TicketEvalResult(
        case_id=case.case_id,
        actual=actual,
        expected=case.expected,
        passed=passed,
        failures=failures,
        metadata=metadata,
    )


def load_eval_cases(path: str | Path) -> list[TicketEvalCase]:
    """Load ticket eval cases from JSON or JSONL."""
    fixture_path = Path(path)
    text = fixture_path.read_text(encoding="utf-8")

    if fixture_path.suffix == ".jsonl":
        cases = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw_case = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSONL line {line_number}: {exc}") from exc
            cases.append(TicketEvalCase.from_dict(raw_case))
        return cases

    data = json.loads(text)
    if isinstance(data, list):
        raw_cases = data
    elif isinstance(data, dict) and isinstance(data.get("cases"), list):
        raw_cases = data["cases"]
    else:
        raise ValueError("eval fixture must be a list or an object with a cases list")

    return [TicketEvalCase.from_dict(raw_case) for raw_case in raw_cases]


def aggregate_field_accuracy(results: list[TicketEvalResult]) -> dict[str, dict[str, int | float]]:
    """Aggregate scalar field-level accuracy across eval results."""
    totals = {field_name: {"tested": 0, "correct": 0} for field_name in SCALAR_SCORE_FIELDS}
    for result in results:
        field_results = result.metadata.get("field_results", {})
        if not isinstance(field_results, dict):
            continue
        for field_name in SCALAR_SCORE_FIELDS:
            if field_name not in field_results:
                continue
            totals[field_name]["tested"] += 1
            if bool(field_results[field_name]):
                totals[field_name]["correct"] += 1

    accuracy: dict[str, dict[str, int | float]] = {}
    for field_name in SCALAR_SCORE_FIELDS:
        tested = totals[field_name]["tested"]
        if tested == 0:
            continue
        correct = totals[field_name]["correct"]
        accuracy[field_name] = {
            "tested": tested,
            "correct": correct,
            "accuracy": correct / tested,
        }
    return accuracy


def eval_result_to_dict(result: TicketEvalResult) -> dict[str, Any]:
    """Serialize an eval result and expose field_results at result level."""
    data = result.to_dict()
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    data["field_results"] = metadata.get("field_results", {})
    return data


def evaluate_file(path: str | Path) -> dict[str, Any]:
    """Evaluate all ticket cases in a fixture file and return an aggregate summary."""
    cases = load_eval_cases(path)
    results = [evaluate_case(case) for case in cases]
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
        "field_accuracy": aggregate_field_accuracy(results),
        "results": [eval_result_to_dict(result) for result in results],
    }


def _timestamp_slug(timestamp: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "", timestamp.replace("+00:00", "Z"))


def build_eval_run_payload(
    fixture_path: str | Path,
    summary: dict[str, Any],
    *,
    mode: str = DEFAULT_EVAL_MODE,
    source: str = DEFAULT_EVAL_SOURCE,
    run_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a durable eval run payload around the existing summary shape."""
    generated_at = generated_at or utc_now_iso()
    run_id = run_id or f"ticket-eval-{_timestamp_slug(generated_at)}"
    return {
        "schema_version": EVAL_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "fixture_path": str(fixture_path),
        "mode": mode,
        "source": source,
        "ok": bool(summary["ok"]),
        "total": int(summary["total"]),
        "passed": int(summary["passed"]),
        "failed": int(summary["failed"]),
        "pass_rate": float(summary["pass_rate"]),
        "field_accuracy": summary.get("field_accuracy", {}),
        "results": summary["results"],
    }


def evaluate_run(
    path: str | Path,
    *,
    mode: str = DEFAULT_EVAL_MODE,
    source: str = DEFAULT_EVAL_SOURCE,
    run_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Evaluate a fixture file and return a persisted-run-ready payload."""
    summary = evaluate_file(path)
    return build_eval_run_payload(
        path,
        summary,
        mode=mode,
        source=source,
        run_id=run_id,
        generated_at=generated_at,
    )


def write_eval_run_json(payload: dict[str, Any], output_path: str | Path) -> Path:
    """Write an eval run payload as stable, pretty JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _markdown_escape(value: Any) -> str:
    text = "—" if value is None or value == "" else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def _format_bool(value: Any) -> str:
    if value is None:
        return "—"
    return "yes" if bool(value) else "no"


def _format_sla(value: Any) -> str:
    return "—" if value is None else f"{value}h"


def _format_expected(expected: dict[str, Any], field_name: str) -> Any:
    value = expected.get(field_name)
    if value is not None:
        return value
    if field_name == "category" and expected.get("allowed_categories"):
        return ", ".join(expected["allowed_categories"])
    if field_name == "severity" and expected.get("allowed_severities"):
        return ", ".join(expected["allowed_severities"])
    return None


def render_eval_run_markdown(payload: dict[str, Any]) -> str:
    """Render a concise Markdown summary for a persisted eval run."""
    lines = [
        f"# Ticket eval run {payload['run_id']}",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Fixture: `{payload['fixture_path']}`",
        f"- Mode/source: `{payload['mode']}` / `{payload['source']}`",
        f"- Result: {payload['passed']}/{payload['total']} passed ({payload['pass_rate']:.0%})",
        "",
        "| Case | Expected category | Expected severity | Expected route | Expected SLA | Expected human | Actual category | Actual severity | Actual route | Actual SLA | Actual human | Result | Failures |",
        "|---|---|---|---|---:|---|---|---|---|---:|---|---|---|",
    ]

    for result in payload["results"]:
        expected = result.get("expected", {})
        actual = result.get("actual", {})
        failures = result.get("failures") or []
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_escape(result.get("case_id")),
                    _markdown_escape(_format_expected(expected, "category")),
                    _markdown_escape(_format_expected(expected, "severity")),
                    _markdown_escape(expected.get("route_to")),
                    _markdown_escape(_format_sla(expected.get("sla_hours"))),
                    _markdown_escape(_format_bool(expected.get("requires_human"))),
                    _markdown_escape(actual.get("category")),
                    _markdown_escape(actual.get("severity")),
                    _markdown_escape(actual.get("route_to")),
                    _markdown_escape(_format_sla(actual.get("sla_hours"))),
                    _markdown_escape(_format_bool(actual.get("requires_human"))),
                    "PASS" if result.get("passed") else "FAIL",
                    _markdown_escape("; ".join(failures) if failures else "—"),
                ]
            )
            + " |"
        )

    return "\n".join(lines) + "\n"


def write_eval_run_markdown(payload: dict[str, Any], output_path: str | Path) -> Path:
    """Write a concise Markdown summary for an eval run payload."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_eval_run_markdown(payload), encoding="utf-8")
    return path


def write_eval_artifacts(
    payload: dict[str, Any],
    artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
    *,
    write_latest: bool = True,
) -> dict[str, Path]:
    """Write timestamped JSON and Markdown artifacts for an eval run."""
    directory = Path(artifacts_dir)
    directory.mkdir(parents=True, exist_ok=True)
    from .store import safe_filename

    filename = safe_filename(str(payload["run_id"]), "ticket-eval-run")
    json_path = write_eval_run_json(payload, directory / f"{filename}.json")
    markdown_path = write_eval_run_markdown(payload, directory / f"{filename}.md")
    paths = {"json": json_path, "markdown": markdown_path}

    if write_latest:
        latest_path = directory / "latest.json"
        shutil.copyfile(json_path, latest_path)
        paths["latest_json"] = latest_path

    return paths


__all__ = [
    "render_ticket_goal",
    "parse_orchestrator_classification",
    "score_classification",
    "aggregate_field_accuracy",
    "eval_result_to_dict",
    "evaluate_case",
    "load_eval_cases",
    "evaluate_file",
    "build_eval_run_payload",
    "evaluate_run",
    "write_eval_run_json",
    "render_eval_run_markdown",
    "write_eval_run_markdown",
    "write_eval_artifacts",
]
