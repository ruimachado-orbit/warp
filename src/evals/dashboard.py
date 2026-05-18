"""Static HTML dashboard renderer for persisted ticket eval runs."""

from __future__ import annotations

import json
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any

from .store import run_folder_name


DEFAULT_RUNS_DIR = "eval-runs"
DEFAULT_DASHBOARD_OUTPUT = "eval-runs/dashboard.html"
FIELD_ACCURACY_FIELDS = (
    "category",
    "severity",
    "priority",
    "sentiment",
    "language",
    "route_to",
    "sla_hours",
    "requires_human",
)


def _as_text(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _html(value: Any) -> str:
    return escape(_as_text(value), quote=True)


def _format_rate(value: Any) -> str:
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return "—"


def _format_sla(value: Any) -> str:
    return "—" if value is None or value == "" else f"{value}h"


def _format_expected(expected: dict[str, Any], field_name: str) -> Any:
    value = expected.get(field_name)
    if value is not None:
        return value
    if field_name == "category" and expected.get("allowed_categories"):
        return ", ".join(str(item) for item in expected["allowed_categories"])
    if field_name == "severity" and expected.get("allowed_severities"):
        return ", ".join(str(item) for item in expected["allowed_severities"])
    return None


def _detail_text(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, sort_keys=True)


def _json_for_script(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _failure_prefix(failure: str) -> str:
    text = failure.strip()
    if not text:
        return "unknown"
    if ":" in text:
        return text.split(":", 1)[0].strip() or "unknown"
    return text.split(None, 1)[0]


def _load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON payload must be an object: {path}")
    data["_path"] = str(path)
    return data


def _provider_from_source_or_metadata(source: Any, metadata: dict[str, Any] | None = None) -> str | None:
    metadata = metadata or {}
    provider = metadata.get("provider")
    if provider:
        return str(provider)
    source_text = str(source or "")
    if source_text.startswith("llm:") and len(source_text) > 4:
        return source_text.split(":", 1)[1]
    return None


def _mixed_or_value(values: list[Any]) -> Any:
    cleaned = [value for value in values if value not in (None, "")]
    if not cleaned:
        return None
    first = cleaned[0]
    if all(value == first for value in cleaned):
        return first
    return "mixed"


def _ticket_to_text(ticket: dict[str, Any] | None, fallback_goal: Any = None) -> str:
    """Render a stored ticket object into a readable text block."""
    if isinstance(ticket, dict) and ticket:
        lines: list[str] = []
        fields = [
            ("Ticket ID", ticket.get("id")),
            ("Source", ticket.get("source")),
            ("Channel", ticket.get("channel")),
            ("Requester ID", ticket.get("requester_id")),
            ("Account ID", ticket.get("account_id")),
            ("Created at", ticket.get("created_at")),
            ("Language", ticket.get("language")),
            ("Subject", ticket.get("subject")),
        ]
        for label, value in fields:
            if value not in (None, ""):
                lines.append(f"{label}: {value}")

        body = ticket.get("body")
        if body not in (None, ""):
            if lines:
                lines.append("")
            lines.extend(["Body:", str(body)])

        metadata = ticket.get("metadata")
        if metadata:
            if lines:
                lines.append("")
            lines.extend(["Metadata:", json.dumps(metadata, ensure_ascii=False, sort_keys=True)])

        if lines:
            return "\n".join(lines)

    if fallback_goal not in (None, ""):
        return str(fallback_goal)
    return "—"


def _evaluation_output(metadata: dict[str, Any]) -> Any:
    for key in ("orchestrator_output", "llm_raw_text", "llm_output", "output"):
        if metadata.get(key) not in (None, ""):
            return metadata[key]
    return None


def _case_id_from_doc(ticket_doc: dict[str, Any], fallback: Any = None) -> str:
    return str(ticket_doc.get("case_id") or fallback or "")


def _normalize_case_from_ticket_eval(
    ticket_doc: dict[str, Any], evaluation: dict[str, Any]
) -> dict[str, Any]:
    metadata = evaluation.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {"metadata": metadata}
    source = evaluation.get("source")
    return {
        "case_id": _case_id_from_doc(ticket_doc),
        "name": ticket_doc.get("name"),
        "description": ticket_doc.get("description"),
        "ticket": ticket_doc.get("ticket") if isinstance(ticket_doc.get("ticket"), dict) else None,
        "ticket_text": _ticket_to_text(ticket_doc.get("ticket"), metadata.get("goal")),
        "expected": ticket_doc.get("expected") or evaluation.get("expected") or {},
        "actual": evaluation.get("actual") or {},
        "passed": bool(evaluation.get("passed")),
        "failures": evaluation.get("failures") or [],
        "field_results": evaluation.get("field_results", metadata.get("field_results", {})),
        "metadata": metadata,
        "generated_at": evaluation.get("generated_at"),
        "mode": evaluation.get("mode"),
        "source": source,
        "provider": _provider_from_source_or_metadata(source, metadata),
        "evaluator_output": _evaluation_output(metadata) or evaluation.get("actual"),
        "_path": ticket_doc.get("_path"),
    }


def _normalize_case_from_run_result(
    result: dict[str, Any], run: dict[str, Any]
) -> dict[str, Any]:
    metadata = result.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {"metadata": metadata}
    source = run.get("source") or metadata.get("source")
    return {
        "case_id": str(result.get("case_id") or ""),
        "name": result.get("name"),
        "description": result.get("description"),
        "ticket": None,
        "ticket_text": _ticket_to_text(None, metadata.get("goal")),
        "expected": result.get("expected") or {},
        "actual": result.get("actual") or {},
        "passed": bool(result.get("passed")),
        "failures": result.get("failures") or [],
        "field_results": result.get("field_results", metadata.get("field_results", {})),
        "metadata": metadata,
        "generated_at": run.get("generated_at"),
        "mode": run.get("mode") or metadata.get("mode"),
        "source": source,
        "provider": run.get("provider") or _provider_from_source_or_metadata(source, metadata),
        "evaluator_output": _evaluation_output(metadata) or result.get("actual"),
        "_path": run.get("_path"),
    }


def _lane_summary(lane: dict[str, Any] | None) -> str:
    if not isinstance(lane, dict):
        return "—"
    status = "PASS" if lane.get("passed") else "FAIL"
    actual = lane.get("actual") or {}
    if not isinstance(actual, dict):
        return status
    parts = [
        str(actual.get("category") or "—"),
        str(actual.get("severity") or "—"),
        str(actual.get("route_to") or "—"),
    ]
    return f"{status} {' / '.join(parts)}"


def _comparison_failures(comparison: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for lane_name in ("rule", "ai"):
        lane = comparison.get(lane_name) or {}
        if isinstance(lane, dict):
            failures.extend(f"{lane_name}: {item}" for item in lane.get("failures") or [])
    failures.extend(
        f"disagreement:{field}" for field in comparison.get("disagreement_fields") or []
    )
    return failures


def _normalize_case_from_ticket_comparison(
    ticket_doc: dict[str, Any], comparison: dict[str, Any]
) -> dict[str, Any]:
    normalized_comparison = {
        "provider": comparison.get("provider"),
        "rule": comparison.get("rule") or {},
        "ai": comparison.get("ai") or {},
        "rule_passed": bool(comparison.get("rule_passed")),
        "ai_passed": bool(comparison.get("ai_passed")),
        "agreement": bool(comparison.get("agreement")),
        "disagreement_fields": comparison.get("disagreement_fields") or [],
    }
    failures = _comparison_failures(normalized_comparison)
    return {
        "case_id": _case_id_from_doc(ticket_doc),
        "name": ticket_doc.get("name"),
        "description": ticket_doc.get("description"),
        "ticket": ticket_doc.get("ticket") if isinstance(ticket_doc.get("ticket"), dict) else None,
        "ticket_text": _ticket_to_text(ticket_doc.get("ticket")),
        "expected": ticket_doc.get("expected") or comparison.get("expected") or {},
        "actual": {},
        "passed": bool(
            normalized_comparison["rule_passed"]
            and normalized_comparison["ai_passed"]
            and normalized_comparison["agreement"]
        ),
        "failures": failures,
        "metadata": {
            "provider": comparison.get("provider"),
            "generated_at": comparison.get("generated_at"),
            "fixture_path": comparison.get("fixture_path"),
        },
        "generated_at": comparison.get("generated_at"),
        "mode": "compare",
        "source": None,
        "provider": comparison.get("provider"),
        "evaluator_output": None,
        "comparison": normalized_comparison,
        "_path": ticket_doc.get("_path"),
    }


def _normalize_case_from_comparison_result(
    result: dict[str, Any], run: dict[str, Any]
) -> dict[str, Any]:
    comparison = {
        "provider": run.get("provider"),
        "rule": result.get("rule") or {},
        "ai": result.get("ai") or {},
        "rule_passed": bool(result.get("rule_passed")),
        "ai_passed": bool(result.get("ai_passed")),
        "agreement": bool(result.get("agreement", True)),
        "disagreement_fields": result.get("disagreement_fields") or [],
    }
    if "agreement" not in result:
        rule_actual = (comparison["rule"] or {}).get("actual") if isinstance(comparison["rule"], dict) else None
        ai_actual = (comparison["ai"] or {}).get("actual") if isinstance(comparison["ai"], dict) else None
        comparison["agreement"] = rule_actual == ai_actual
    if not comparison["disagreement_fields"] and not comparison["agreement"]:
        comparison["disagreement_fields"] = ["actual"]
    failures = _comparison_failures(comparison)
    return {
        "case_id": str(result.get("case_id") or ""),
        "name": result.get("name"),
        "description": result.get("description"),
        "ticket": None,
        "ticket_text": "—",
        "expected": result.get("expected") or {},
        "actual": {},
        "passed": bool(comparison["rule_passed"] and comparison["ai_passed"] and comparison["agreement"]),
        "failures": failures,
        "metadata": {
            "provider": run.get("provider"),
            "generated_at": run.get("generated_at"),
            "fixture_path": run.get("fixture_path"),
            "rule_source": run.get("rule_source"),
            "ai_source": run.get("ai_source"),
        },
        "generated_at": run.get("generated_at"),
        "mode": "compare",
        "source": _comparison_source(run),
        "provider": run.get("provider"),
        "evaluator_output": None,
        "comparison": comparison,
        "_path": run.get("_path"),
    }


def _aggregates(cases: list[dict[str, Any]]) -> tuple[int, int, int, float]:
    total = len(cases)
    passed = sum(1 for case in cases if case.get("passed"))
    failed = total - passed
    pass_rate = passed / total if total else 0.0
    return total, passed, failed, pass_rate


def _aggregate_field_accuracy(field_results_items: list[Any]) -> dict[str, dict[str, int | float]]:
    totals = {field_name: {"tested": 0, "correct": 0} for field_name in FIELD_ACCURACY_FIELDS}
    for field_results in field_results_items:
        if not isinstance(field_results, dict):
            continue
        for field_name in FIELD_ACCURACY_FIELDS:
            if field_name not in field_results:
                continue
            totals[field_name]["tested"] += 1
            if bool(field_results[field_name]):
                totals[field_name]["correct"] += 1

    accuracy: dict[str, dict[str, int | float]] = {}
    for field_name in FIELD_ACCURACY_FIELDS:
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


def _normalize_eval_group(
    folder_name: str | None,
    items: list[tuple[dict[str, Any], dict[str, Any]]],
    top_level_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cases = [_normalize_case_from_ticket_eval(doc, evaluation) for doc, evaluation in items]
    first_eval = items[0][1] if items else {}
    run_id = str(first_eval.get("run_id") or (top_level_run or {}).get("run_id") or folder_name or "")
    total, passed, failed, pass_rate = _aggregates(cases)
    payload = top_level_run or {}
    field_accuracy = payload.get("field_accuracy") or _aggregate_field_accuracy(
        [case.get("field_results") for case in cases]
    )
    return {
        "kind": "evaluation",
        "run_id": run_id,
        "folder_name": folder_name,
        "generated_at": payload.get("generated_at") or _mixed_or_value([case.get("generated_at") for case in cases]),
        "fixture_path": payload.get("fixture_path") or _mixed_or_value([first_eval.get("fixture_path")]),
        "mode": payload.get("mode") or _mixed_or_value([case.get("mode") for case in cases]),
        "source": payload.get("source") or _mixed_or_value([case.get("source") for case in cases]),
        "provider": payload.get("provider") or _mixed_or_value([case.get("provider") for case in cases]),
        "total": int(payload.get("total", total)),
        "passed": int(payload.get("passed", passed)),
        "failed": int(payload.get("failed", failed)),
        "pass_rate": float(payload.get("pass_rate", pass_rate)),
        "field_accuracy": field_accuracy,
        "cases": cases,
        "results": cases,
        "_path": payload.get("_path"),
        "_source": "merged" if top_level_run else "run_folder",
    }


def _comparison_source(run: dict[str, Any]) -> str:
    rule_source = run.get("rule_source") or "rule"
    ai_source = run.get("ai_source") or (f"ai:{run.get('provider')}" if run.get("provider") else "ai")
    return f"{rule_source} vs {ai_source}"


def _normalize_comparison_group(
    folder_name: str | None,
    items: list[tuple[dict[str, Any], dict[str, Any]]],
    top_level_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cases = [_normalize_case_from_ticket_comparison(doc, comparison) for doc, comparison in items]
    first_comparison = items[0][1] if items else {}
    total, passed, failed, pass_rate = _aggregates(cases)
    payload = top_level_run or {}
    provider = payload.get("provider") or first_comparison.get("provider")
    generated_at = payload.get("generated_at") or first_comparison.get("generated_at")
    source = _comparison_source(payload) if payload else f"rule vs ai:{provider or 'unknown'}"
    rule_field_accuracy = payload.get("rule_field_accuracy") or _aggregate_field_accuracy(
        [((case.get("comparison") or {}).get("rule") or {}).get("field_results") for case in cases]
    )
    ai_field_accuracy = payload.get("ai_field_accuracy") or _aggregate_field_accuracy(
        [((case.get("comparison") or {}).get("ai") or {}).get("field_results") for case in cases]
    )
    return {
        "kind": "comparison",
        "run_id": str(payload.get("run_id") or folder_name or f"comparison-{generated_at or ''}"),
        "folder_name": folder_name,
        "generated_at": generated_at,
        "fixture_path": payload.get("fixture_path") or first_comparison.get("fixture_path"),
        "mode": "compare",
        "source": source,
        "provider": provider,
        "total": int(payload.get("total", total)),
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "rule_field_accuracy": rule_field_accuracy,
        "ai_field_accuracy": ai_field_accuracy,
        "cases": cases,
        "results": cases,
        "_path": payload.get("_path"),
        "_source": "merged" if top_level_run else "run_folder",
    }


def _is_comparison_payload(payload: dict[str, Any]) -> bool:
    return str(payload.get("schema_version") or "") == "warp.ticket_eval_compare.v1" or "ai_source" in payload


def _normalize_run_payload(run: dict[str, Any]) -> dict[str, Any]:
    if _is_comparison_payload(run):
        cases = [_normalize_case_from_comparison_result(result, run) for result in run.get("results", [])]
        total, passed, failed, pass_rate = _aggregates(cases)
        rule_field_accuracy = run.get("rule_field_accuracy") or _aggregate_field_accuracy(
            [((case.get("comparison") or {}).get("rule") or {}).get("field_results") for case in cases]
        )
        ai_field_accuracy = run.get("ai_field_accuracy") or _aggregate_field_accuracy(
            [((case.get("comparison") or {}).get("ai") or {}).get("field_results") for case in cases]
        )
        return {
            "kind": "comparison",
            "run_id": str(run.get("run_id") or run_folder_name(run)),
            "folder_name": None,
            "generated_at": run.get("generated_at"),
            "fixture_path": run.get("fixture_path"),
            "mode": "compare",
            "source": _comparison_source(run),
            "provider": run.get("provider"),
            "total": int(run.get("total", total)),
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
            "rule_field_accuracy": rule_field_accuracy,
            "ai_field_accuracy": ai_field_accuracy,
            "cases": cases,
            "results": cases,
            "_path": run.get("_path"),
            "_source": "run_json",
        }

    cases = [_normalize_case_from_run_result(result, run) for result in run.get("results", [])]
    total, passed, failed, pass_rate = _aggregates(cases)
    field_accuracy = run.get("field_accuracy") or _aggregate_field_accuracy(
        [case.get("field_results") for case in cases]
    )
    return {
        "kind": "evaluation",
        "run_id": str(run.get("run_id") or run_folder_name(run)),
        "folder_name": None,
        "generated_at": run.get("generated_at"),
        "fixture_path": run.get("fixture_path"),
        "mode": run.get("mode"),
        "source": run.get("source"),
        "provider": run.get("provider") or _provider_from_source_or_metadata(run.get("source")),
        "total": int(run.get("total", total)),
        "passed": int(run.get("passed", passed)),
        "failed": int(run.get("failed", failed)),
        "pass_rate": float(run.get("pass_rate", pass_rate)),
        "field_accuracy": field_accuracy,
        "cases": cases,
        "results": cases,
        "_path": run.get("_path"),
        "_source": "run_json",
    }


def _payload_identity(payload: dict[str, Any]) -> tuple[str, str]:
    if _is_comparison_payload(payload):
        return ("comparison", "|".join(_comparison_key_from_payload(payload)))
    run_id = payload.get("run_id")
    if run_id:
        return ("run", str(run_id))
    return ("folder", run_folder_name(payload))


def _load_top_level_payloads(directory: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    latest_payload: dict[str, Any] | None = None
    for path in sorted(directory.glob("*.json")):
        try:
            payload = load_eval_run(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if path.name == "latest.json":
            latest_payload = payload
        else:
            payloads.append(payload)

    # `latest.json` is usually a duplicate convenience pointer. Keep skipping it
    # when a timestamped artifact for the same run exists, but use it as a
    # fallback when it is the only copy available.
    if latest_payload is not None:
        latest_identity = _payload_identity(latest_payload)
        existing_identities = {_payload_identity(payload) for payload in payloads}
        if latest_identity not in existing_identities:
            payloads.append(latest_payload)
    return payloads


def _load_ticket_docs(run_folder: Path) -> list[dict[str, Any]]:
    tickets_dir = run_folder / "tickets"
    if not tickets_dir.is_dir():
        return []
    docs: list[dict[str, Any]] = []
    for path in sorted(tickets_dir.glob("*.json")):
        try:
            docs.append(_load_json_object(path))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return docs


def _comparison_key_from_payload(payload: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(payload.get("generated_at") or ""),
        str(payload.get("provider") or ""),
        str(payload.get("fixture_path") or ""),
    )


def _comparison_key_from_entry(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("generated_at") or ""),
        str(entry.get("provider") or ""),
        str(entry.get("fixture_path") or ""),
    )


def _run_sort_key(run: dict[str, Any]) -> tuple[str, str]:
    return (str(run.get("generated_at") or ""), str(run.get("run_id") or run.get("folder_name") or ""))


def load_eval_run(path: str | Path) -> dict[str, Any]:
    """Load one persisted eval run JSON file."""
    run_path = Path(path)
    data = _load_json_object(run_path)
    data.setdefault("results", [])
    return data


def load_eval_runs(runs_dir: str | Path = DEFAULT_RUNS_DIR) -> list[dict[str, Any]]:
    """Load dashboard runs, preferring run-scoped ticket artifacts over run JSON."""
    directory = Path(runs_dir)
    if not directory.exists():
        return []

    top_level_payloads = _load_top_level_payloads(directory)
    top_by_run_id: dict[str, dict[str, Any]] = {}
    top_by_folder: dict[str, dict[str, Any]] = {}
    top_comparison_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for payload in top_level_payloads:
        try:
            top_by_folder[run_folder_name(payload)] = payload
        except Exception:
            pass
        if _is_comparison_payload(payload):
            top_comparison_by_key[_comparison_key_from_payload(payload)] = payload
        run_id = payload.get("run_id")
        if run_id:
            existing = top_by_run_id.get(str(run_id))
            if existing is None or str(payload.get("generated_at", "")) >= str(existing.get("generated_at", "")):
                top_by_run_id[str(run_id)] = payload
    runs: list[dict[str, Any]] = []
    represented_run_ids: set[str] = set()
    represented_comparison_keys: set[tuple[str, str, str]] = set()
    represented_folders: set[str] = set()

    for run_folder in sorted(path for path in directory.iterdir() if path.is_dir()):
        docs = _load_ticket_docs(run_folder)
        if not docs:
            continue
        folder_name = run_folder.name
        represented_folders.add(folder_name)

        eval_groups: dict[tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        comparison_groups: dict[tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        for doc in docs:
            for evaluation in doc.get("evaluations") or []:
                if not isinstance(evaluation, dict):
                    continue
                key = (
                    str(evaluation.get("run_id") or folder_name),
                    str(evaluation.get("mode") or ""),
                    str(evaluation.get("source") or ""),
                )
                eval_groups.setdefault(key, []).append((doc, evaluation))
            for comparison in doc.get("comparisons") or []:
                if not isinstance(comparison, dict):
                    continue
                key = _comparison_key_from_entry(comparison)
                comparison_groups.setdefault(key, []).append((doc, comparison))

        for (run_id, _mode, _source), items in eval_groups.items():
            top_level_run = top_by_run_id.get(run_id) or top_by_folder.get(folder_name)
            runs.append(_normalize_eval_group(folder_name, items, top_level_run))
            represented_run_ids.add(run_id)

        for key, items in comparison_groups.items():
            top_level_run = top_comparison_by_key.get(key) or top_by_folder.get(folder_name)
            runs.append(_normalize_comparison_group(folder_name, items, top_level_run))
            represented_comparison_keys.add(key)

    for payload in top_level_payloads:
        folder_name = run_folder_name(payload)
        if _is_comparison_payload(payload):
            key = _comparison_key_from_payload(payload)
            if key in represented_comparison_keys or folder_name in represented_folders:
                continue
        else:
            run_id = str(payload.get("run_id") or "")
            if run_id and run_id in represented_run_ids:
                continue
            if folder_name in represented_folders:
                continue
        runs.append(_normalize_run_payload(payload))

    # Keep only the richest copy of exact duplicate lanes. Do not collapse
    # distinct mode/source/provider groups that happen to share a run_id.
    by_run_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    anonymous_runs: list[dict[str, Any]] = []
    richness = {"run_json": 0, "run_folder": 1, "merged": 2}
    for run in runs:
        run_id = str(run.get("run_id") or "")
        if not run_id:
            anonymous_runs.append(run)
            continue
        run_key = (
            str(run.get("kind") or ""),
            run_id,
            str(run.get("mode") or ""),
            str(run.get("source") or ""),
            str(run.get("provider") or ""),
        )
        existing = by_run_key.get(run_key)
        if existing is None:
            by_run_key[run_key] = run
            continue
        current_rank = richness.get(str(run.get("_source")), 0)
        existing_rank = richness.get(str(existing.get("_source")), 0)
        if current_rank > existing_rank or (
            current_rank == existing_rank and _run_sort_key(run) >= _run_sort_key(existing)
        ):
            by_run_key[run_key] = run

    normalized_runs = list(by_run_key.values()) + anonymous_runs
    normalized_runs.sort(key=_run_sort_key, reverse=True)
    return normalized_runs


def _ensure_dashboard_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept normalized runs or legacy raw run payloads for render compatibility."""
    normalized = []
    for run in runs:
        if "cases" in run and "kind" in run:
            normalized.append(run)
        else:
            normalized.append(_normalize_run_payload(run))
    normalized.sort(key=_run_sort_key, reverse=True)
    return normalized


def _mode_source_label(run: dict[str, Any]) -> str:
    mode = _as_text(run.get("mode"))
    source = _as_text(run.get("source"))
    return f"{mode} / {source}" if source != "—" else mode


def _render_summary(latest: dict[str, Any]) -> str:
    return f"""
    <section class=\"cards\" aria-label=\"Latest run summary\">
      <div class=\"card\"><span>Latest run</span><strong>{_html(latest.get('run_id') or latest.get('folder_name'))}</strong></div>
      <div class=\"card\"><span>Generated</span><strong>{_html(latest.get('generated_at'))}</strong></div>
      <div class=\"card\"><span>Kind</span><strong>{_html(latest.get('kind'))}</strong></div>
      <div class=\"card\"><span>Mode/source</span><strong>{_html(_mode_source_label(latest))}</strong></div>
      <div class=\"card\"><span>Provider</span><strong>{_html(latest.get('provider'))}</strong></div>
      <div class=\"card\"><span>Passed</span><strong>{_html(latest.get('passed'))}/{_html(latest.get('total'))}</strong></div>
      <div class=\"card\"><span>Pass rate</span><strong>{_html(_format_rate(latest.get('pass_rate')))}</strong></div>
      <div class=\"card\"><span>Failed</span><strong>{_html(latest.get('failed'))}</strong></div>
    </section>
    """


def _render_history(runs: list[dict[str, Any]]) -> str:
    rows = []
    for run in runs:
        rows.append(
            "<tr>"
            f"<td>{_html(run.get('generated_at'))}</td>"
            f"<td>{_html(run.get('kind'))}</td>"
            f"<td>{_html(run.get('fixture_path'))}</td>"
            f"<td>{_html(_mode_source_label(run))}</td>"
            f"<td>{_html(run.get('provider'))}</td>"
            f"<td class=\"num\">{_html(run.get('passed'))}/{_html(run.get('total'))}</td>"
            f"<td class=\"num\">{_html(_format_rate(run.get('pass_rate')))}</td>"
            f"<td>{_html(run.get('run_id') or run.get('folder_name'))}</td>"
            "</tr>"
        )
    return """
    <section>
      <h2>Run history</h2>
      <table>
        <thead><tr><th>Generated</th><th>Kind</th><th>Fixture</th><th>Mode/source</th><th>Provider</th><th>Passed/total</th><th>Pass rate</th><th>Run/folder ID</th></tr></thead>
        <tbody>
    """ + "\n".join(rows) + """
        </tbody>
      </table>
    </section>
    """


def _render_failures(runs: list[dict[str, Any]]) -> str:
    counts: Counter[str] = Counter()
    for run in runs:
        for case in run.get("cases", []):
            for failure in case.get("failures") or []:
                counts[_failure_prefix(str(failure))] += 1

    if not counts:
        body = '<p class="muted">No failures found in persisted runs.</p>'
    else:
        rows = [
            f"<tr><td>{_html(prefix)}</td><td class=\"num\">{count}</td></tr>"
            for prefix, count in counts.most_common()
        ]
        body = """
      <table>
        <thead><tr><th>Failure field/prefix</th><th>Count</th></tr></thead>
        <tbody>
        """ + "\n".join(rows) + """
        </tbody>
      </table>
        """

    return f"""
    <section>
      <h2>Failures by field/prefix</h2>
      {body}
    </section>
    """


def _render_eval_case_table(latest: dict[str, Any]) -> str:
    rows = []
    for index, case in enumerate(latest.get("cases", [])):
        expected = case.get("expected") or {}
        actual = case.get("actual") or {}
        failures = "; ".join(str(item) for item in (case.get("failures") or []))
        status = "PASS" if case.get("passed") else "FAIL"
        status_class = "pass" if case.get("passed") else "fail"
        rows.append(
            "<tr>"
            f"<td><button type=\"button\" class=\"case-button\" data-case-index=\"{index}\" aria-haspopup=\"dialog\">{_html(case.get('case_id'))}</button></td>"
            f"<td>{_html(case.get('name'))}</td>"
            f"<td>{_html(_format_expected(expected, 'category'))}<br><span>{_html(actual.get('category'))}</span></td>"
            f"<td>{_html(_format_expected(expected, 'severity'))}<br><span>{_html(actual.get('severity'))}</span></td>"
            f"<td>{_html(expected.get('route_to'))}<br><span>{_html(actual.get('route_to'))}</span></td>"
            f"<td>{_html(_format_sla(expected.get('sla_hours')))}<br><span>{_html(_format_sla(actual.get('sla_hours')))}</span></td>"
            f"<td>{_html(expected.get('requires_human'))}<br><span>{_html(actual.get('requires_human'))}</span></td>"
            f"<td class=\"{status_class}\">{status}</td>"
            f"<td>{_html(failures)}</td>"
            "</tr>"
        )

    return """
    <section>
      <h2>Latest run cases</h2>
      <p class=\"muted\">Each expected value is shown above the actual value. Select a case to view ticket text, labels, evaluator output, and metadata.</p>
      <table>
        <thead><tr><th>Case</th><th>Name</th><th>Category</th><th>Severity</th><th>Route</th><th>SLA</th><th>Human</th><th>Result</th><th>Failures</th></tr></thead>
        <tbody>
    """ + "\n".join(rows) + """
        </tbody>
      </table>
    </section>
    """


def _render_comparison_case_table(latest: dict[str, Any]) -> str:
    rows = []
    for index, case in enumerate(latest.get("cases", [])):
        comparison = case.get("comparison") or {}
        disagreement_fields = ", ".join(str(item) for item in comparison.get("disagreement_fields") or [])
        failures = "; ".join(str(item) for item in (case.get("failures") or []))
        agreement = "yes" if comparison.get("agreement") else "no"
        status_class = "pass" if case.get("passed") else "fail"
        rows.append(
            "<tr>"
            f"<td><button type=\"button\" class=\"case-button\" data-case-index=\"{index}\" aria-haspopup=\"dialog\">{_html(case.get('case_id'))}</button></td>"
            f"<td>{_html(case.get('name'))}</td>"
            f"<td class=\"{'pass' if comparison.get('rule_passed') else 'fail'}\">{_html(_lane_summary(comparison.get('rule')))}</td>"
            f"<td class=\"{'pass' if comparison.get('ai_passed') else 'fail'}\">{_html(_lane_summary(comparison.get('ai')))}</td>"
            f"<td class=\"{status_class}\">{agreement}</td>"
            f"<td>{_html(disagreement_fields)}</td>"
            f"<td>{_html(failures)}</td>"
            "</tr>"
        )

    return """
    <section>
      <h2>Latest comparison cases</h2>
      <p class=\"muted\">Rule and AI lanes are shown side-by-side. Select a case to inspect ticket text, expected labels, comparison lanes, failures, and metadata.</p>
      <table>
        <thead><tr><th>Case</th><th>Name</th><th>Rule result</th><th>AI result</th><th>Agreement</th><th>Disagreement fields</th><th>Failures</th></tr></thead>
        <tbody>
    """ + "\n".join(rows) + """
        </tbody>
      </table>
    </section>
    """


def _render_case_table(latest: dict[str, Any]) -> str:
    if latest.get("kind") == "comparison":
        return _render_comparison_case_table(latest)
    return _render_eval_case_table(latest)


def _case_details(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for case in cases:
        comparison = case.get("comparison")
        actual_or_comparison: Any = case.get("actual")
        if comparison:
            actual_or_comparison = {
                "rule": comparison.get("rule"),
                "ai": comparison.get("ai"),
                "rule_passed": comparison.get("rule_passed"),
                "ai_passed": comparison.get("ai_passed"),
                "agreement": comparison.get("agreement"),
                "disagreement_fields": comparison.get("disagreement_fields"),
            }
        failures = case.get("failures") or []
        details.append(
            {
                "case_id": _as_text(case.get("case_id")),
                "name": _as_text(case.get("name")),
                "description": _as_text(case.get("description")),
                "ticket_text": _detail_text(case.get("ticket_text")),
                "expected": _detail_text(case.get("expected")),
                "actual": _detail_text(actual_or_comparison),
                "comparison": _detail_text(comparison) if comparison else "—",
                "failures": "\n".join(str(item) for item in failures) if failures else "—",
                "evaluator_output": _detail_text(case.get("evaluator_output")),
                "metadata": _detail_text(case.get("metadata")),
            }
        )
    return details


def render_dashboard_html(runs: list[dict[str, Any]]) -> str:
    """Render a self-contained static HTML dashboard for eval runs."""
    title = "Warp ticket eval dashboard"
    case_details_json = "[]"
    normalized_runs = _ensure_dashboard_runs(runs)
    if not normalized_runs:
        content = "<p>No eval run JSON files found.</p>"
    else:
        latest = normalized_runs[0]
        case_details_json = _json_for_script(_case_details(latest.get("cases", [])))
        content = "\n".join(
            [
                _render_summary(latest),
                _render_history(normalized_runs),
                _render_failures(normalized_runs),
                _render_case_table(latest),
            ]
        )

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; --border: #d0d7de; --muted: #57606a; --bg: #f6f8fa; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; line-height: 1.45; }}
    h1, h2 {{ margin-bottom: 0.5rem; }}
    section {{ margin-top: 2rem; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; }}
    .card {{ border: 1px solid var(--border); border-radius: 10px; padding: 1rem; background: var(--bg); }}
    .card span, .muted, td span {{ color: var(--muted); }}
    .card strong {{ display: block; margin-top: 0.35rem; font-size: 1.2rem; overflow-wrap: anywhere; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.92rem; }}
    th, td {{ border: 1px solid var(--border); padding: 0.5rem 0.65rem; text-align: left; vertical-align: top; }}
    th {{ background: var(--bg); }}
    .num {{ text-align: right; white-space: nowrap; }}
    .pass {{ color: #1a7f37; font-weight: 700; }}
    .fail {{ color: #cf222e; font-weight: 700; }}
    .case-button {{ appearance: none; border: 0; padding: 0; background: transparent; color: #0969da; cursor: pointer; font: inherit; text-decoration: underline; }}
    .case-button:hover, .case-button:focus {{ text-decoration-thickness: 2px; }}
    .modal-backdrop[hidden] {{ display: none; }}
    .modal-backdrop {{ position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 1rem; background: rgba(31, 35, 40, 0.55); }}
    .case-modal {{ width: min(900px, 100%); max-height: min(85vh, 900px); overflow: auto; border: 1px solid var(--border); border-radius: 12px; background: Canvas; color: CanvasText; box-shadow: 0 16px 48px rgba(31, 35, 40, 0.35); }}
    .modal-header {{ position: sticky; top: 0; display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1rem; border-bottom: 1px solid var(--border); background: Canvas; }}
    .modal-header h2 {{ margin: 0; overflow-wrap: anywhere; }}
    .modal-close {{ border: 1px solid var(--border); border-radius: 8px; padding: 0.35rem 0.65rem; background: var(--bg); color: inherit; cursor: pointer; font: inherit; }}
    .modal-body {{ padding: 1rem; }}
    .modal-body h3 {{ margin: 1rem 0 0.35rem; }}
    .modal-body h3:first-child {{ margin-top: 0; }}
    .modal-body pre {{ margin: 0; padding: 0.75rem; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }}
    @media (max-width: 700px) {{ body {{ margin: 1rem; }} table {{ display: block; overflow-x: auto; }} }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    {content}
  </main>
  <div id=\"case-modal-backdrop\" class=\"modal-backdrop\" hidden>
    <section class=\"case-modal\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"case-modal-title\">
      <div class=\"modal-header\">
        <h2 id=\"case-modal-title\">Case details</h2>
        <button type=\"button\" class=\"modal-close\" id=\"case-modal-close\">Close</button>
      </div>
      <div class=\"modal-body\">
        <h3>Ticket</h3>
        <pre id=\"case-modal-ticket\"></pre>
        <h3>Expected labels</h3>
        <pre id=\"case-modal-expected\"></pre>
        <h3>Actual labels / comparison lanes</h3>
        <pre id=\"case-modal-actual\"></pre>
        <h3>Failures</h3>
        <pre id=\"case-modal-failures\"></pre>
        <h3>Evaluator output</h3>
        <pre id=\"case-modal-output\"></pre>
        <h3>Evaluator metadata</h3>
        <pre id=\"case-modal-metadata\"></pre>
      </div>
    </section>
  </div>
  <script type=\"application/json\" id=\"case-details-data\">{case_details_json}</script>
  <script>
    (function () {{
      const dataElement = document.getElementById('case-details-data');
      const cases = dataElement ? JSON.parse(dataElement.textContent || '[]') : [];
      const backdrop = document.getElementById('case-modal-backdrop');
      const dialog = backdrop ? backdrop.querySelector('[role="dialog"]') : null;
      const closeButton = document.getElementById('case-modal-close');
      const title = document.getElementById('case-modal-title');
      const ticket = document.getElementById('case-modal-ticket');
      const expected = document.getElementById('case-modal-expected');
      const actual = document.getElementById('case-modal-actual');
      const output = document.getElementById('case-modal-output');
      const metadata = document.getElementById('case-modal-metadata');
      const failures = document.getElementById('case-modal-failures');
      let lastFocused = null;

      function openCase(index) {{
        const detail = cases[index];
        if (!detail || !backdrop || !title || !ticket || !expected || !actual || !output || !metadata || !failures) return;
        lastFocused = document.activeElement;
        title.textContent = 'Case ' + detail.case_id;
        ticket.textContent = detail.ticket_text || '—';
        expected.textContent = detail.expected || '—';
        actual.textContent = detail.actual || detail.comparison || '—';
        failures.textContent = detail.failures || '—';
        output.textContent = detail.evaluator_output || '—';
        metadata.textContent = detail.metadata || '—';
        backdrop.hidden = false;
        closeButton && closeButton.focus();
      }}

      function closeModal() {{
        if (!backdrop || backdrop.hidden) return;
        backdrop.hidden = true;
        if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
      }}

      document.querySelectorAll('.case-button').forEach(function (button) {{
        button.addEventListener('click', function () {{
          openCase(Number(button.dataset.caseIndex));
        }});
      }});

      closeButton && closeButton.addEventListener('click', closeModal);
      backdrop && backdrop.addEventListener('click', function (event) {{
        if (event.target === backdrop) closeModal();
      }});
      document.addEventListener('keydown', function (event) {{
        if (event.key === 'Escape') closeModal();
        if (event.key !== 'Tab' || !backdrop || backdrop.hidden || !dialog) return;
        const focusable = dialog.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {{
          event.preventDefault();
          last.focus();
        }} else if (!event.shiftKey && document.activeElement === last) {{
          event.preventDefault();
          first.focus();
        }}
      }});
    }})();
  </script>
</body>
</html>
"""


def write_dashboard(
    runs_dir: str | Path = DEFAULT_RUNS_DIR,
    output: str | Path = DEFAULT_DASHBOARD_OUTPUT,
) -> Path:
    """Load eval runs and write a static HTML dashboard."""
    runs = load_eval_runs(runs_dir)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_dashboard_html(runs), encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for generating the static eval dashboard."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate a static ticket eval dashboard.")
    parser.add_argument(
        "--runs-dir",
        default=DEFAULT_RUNS_DIR,
        help="Directory containing eval run JSON files and run-scoped ticket folders.",
    )
    parser.add_argument("--output", default=DEFAULT_DASHBOARD_OUTPUT, help="HTML output path.")
    args = parser.parse_args(argv)

    path = write_dashboard(args.runs_dir, args.output)
    print(f"Wrote dashboard: {path}")
    return 0


__all__ = [
    "DEFAULT_RUNS_DIR",
    "DEFAULT_DASHBOARD_OUTPUT",
    "load_eval_run",
    "load_eval_runs",
    "render_dashboard_html",
    "write_dashboard",
    "main",
]
