"""Ticket-centric JSON artifact store for evaluation history."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ticket_model import utc_now_iso

from . import rule


TICKET_STORE_SCHEMA_VERSION = "warp.eval_ticket_store.v1"
DEFAULT_TICKETS_DIR = "eval-runs"


def safe_filename(value: str, fallback: str = "ticket-eval-run") -> str:
    """Return a safe, stable filename or path component."""
    sanitized = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value)).strip("-._")
    return sanitized or fallback


def safe_case_filename(case_id: str) -> str:
    """Return a safe, stable JSON filename for a case id."""
    return f"{safe_filename(case_id, 'ticket-eval-case')}.json"


def safe_run_dirname(run_id: str) -> str:
    """Return a safe, stable directory name for an eval run id."""
    return safe_filename(run_id, "ticket-eval-run")


def _timestamp_slug(timestamp: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "", str(timestamp).replace("+00:00", "Z")) or "unknown-time"


def run_folder_name(payload: dict[str, Any]) -> str:
    """Return the run folder name for an eval or comparison payload."""
    run_id = payload.get("run_id")
    if run_id:
        return safe_run_dirname(str(run_id))
    if str(payload.get("schema_version") or "") == "warp.ticket_eval_compare.v1" or "ai_source" in payload:
        provider = safe_filename(str(payload.get("provider") or "comparison"), "comparison")
        return safe_run_dirname(f"comparison-{_timestamp_slug(str(payload.get('generated_at') or ''))}-{provider}")
    return safe_run_dirname(f"ticket-eval-{_timestamp_slug(str(payload.get('generated_at') or ''))}")


def ticket_file_path(tickets_dir: str | Path, case_id: str, run_id: str | None = None) -> Path:
    """Return the store path for a case id, optionally inside a run folder."""
    root = Path(tickets_dir)
    if run_id:
        return root / safe_run_dirname(run_id) / "tickets" / safe_case_filename(case_id)
    return root / safe_case_filename(case_id)


def run_ticket_file_path(tickets_dir: str | Path, payload: dict[str, Any], case_id: str) -> Path:
    """Return the per-ticket path inside the payload's run folder."""
    return Path(tickets_dir) / run_folder_name(payload) / "tickets" / safe_case_filename(case_id)


def _read_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _write_ticket(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _load_existing_ticket(path: Path, case_id: str) -> dict[str, Any]:
    if path.exists():
        data = _read_json(path)
        data.setdefault("schema_version", TICKET_STORE_SCHEMA_VERSION)
        data.setdefault("case_id", case_id)
        data.setdefault("evaluations", [])
        data.setdefault("comparisons", [])
        return data
    return {
        "schema_version": TICKET_STORE_SCHEMA_VERSION,
        "case_id": case_id,
        "updated_at": utc_now_iso(),
        "evaluations": [],
        "comparisons": [],
    }


def _fixture_files(fixtures: str | Path | None) -> list[Path]:
    if fixtures is None:
        return []
    path = Path(fixtures)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(
            candidate
            for candidate in path.iterdir()
            if candidate.is_file() and candidate.suffix in {".json", ".jsonl"}
        )
    return []


def load_fixture_tickets_by_case_id(fixtures: str | Path | None) -> dict[str, dict[str, Any]]:
    """Load fixture cases keyed by case id for ticket/expected enrichment."""
    cases: dict[str, dict[str, Any]] = {}
    for fixture_path in _fixture_files(fixtures):
        for case in rule.load_eval_cases(fixture_path):
            case_data = case.to_dict()
            case_data["fixture_path"] = str(fixture_path)
            cases[case.case_id] = case_data
    return cases


def _fixture_lookup_for_payload(
    payload: dict[str, Any], fixtures: str | Path | None
) -> dict[str, dict[str, Any]]:
    fixture_source = fixtures if fixtures is not None else payload.get("fixture_path")
    return load_fixture_tickets_by_case_id(fixture_source)


def _apply_fixture_enrichment(
    ticket_doc: dict[str, Any], fixture_case: dict[str, Any] | None, result: dict[str, Any]
) -> None:
    if fixture_case:
        if fixture_case.get("ticket") is not None:
            ticket_doc["ticket"] = fixture_case["ticket"]
        if fixture_case.get("expected") is not None:
            ticket_doc["expected"] = fixture_case["expected"]
        if fixture_case.get("name") is not None:
            ticket_doc["name"] = fixture_case["name"]
        if fixture_case.get("description") is not None:
            ticket_doc["description"] = fixture_case["description"]
    elif result.get("expected") is not None:
        ticket_doc.setdefault("expected", result["expected"])


def _evaluation_key(evaluation: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(evaluation.get("run_id") or ""),
        str(evaluation.get("mode") or ""),
        str(evaluation.get("source") or ""),
    )


def _comparison_key(comparison: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(comparison.get("generated_at") or ""),
        str(comparison.get("provider") or ""),
        str(comparison.get("fixture_path") or ""),
    )


def _upsert_list(
    items: list[dict[str, Any]],
    new_item: dict[str, Any],
    key_func,
) -> list[dict[str, Any]]:
    new_key = key_func(new_item)
    replaced = False
    updated: list[dict[str, Any]] = []
    for item in items:
        if key_func(item) == new_key:
            updated.append(new_item)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(new_item)
    return updated


def _sort_evaluations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (str(item.get("generated_at") or ""), *_evaluation_key(item)))


def _sort_comparisons(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: _comparison_key(item))


def _classification_disagreements(
    rule_actual: dict[str, Any] | None,
    ai_actual: dict[str, Any] | None,
) -> list[str]:
    if not isinstance(rule_actual, dict) or not isinstance(ai_actual, dict):
        return ["actual"]
    fields = (
        "category",
        "severity",
        "priority",
        "sentiment",
        "language",
        "route_to",
        "sla_hours",
        "requires_human",
    )
    return [field for field in fields if rule_actual.get(field) != ai_actual.get(field)]


def upsert_eval_run_payload(
    payload: dict[str, Any],
    tickets_dir: str | Path = DEFAULT_TICKETS_DIR,
    *,
    fixtures: str | Path | None = None,
) -> list[Path]:
    """Upsert every result in one run-centric eval payload into ticket files."""
    fixture_cases = _fixture_lookup_for_payload(payload, fixtures)
    paths: list[Path] = []

    for result in payload.get("results", []):
        case_id = str(result.get("case_id") or "")
        if not case_id:
            continue

        path = run_ticket_file_path(tickets_dir, payload, case_id)
        ticket_doc = _load_existing_ticket(path, case_id)
        _apply_fixture_enrichment(ticket_doc, fixture_cases.get(case_id), result)

        metadata = result.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {"metadata": metadata}
        if "field_results" not in metadata and isinstance(result.get("field_results"), dict):
            metadata = {**metadata, "field_results": result["field_results"]}

        evaluation = {
            "run_id": payload.get("run_id"),
            "generated_at": payload.get("generated_at"),
            "fixture_path": payload.get("fixture_path"),
            "mode": payload.get("mode"),
            "source": payload.get("source"),
            "actual": result.get("actual"),
            "passed": bool(result.get("passed")),
            "failures": result.get("failures", []),
            "metadata": metadata,
        }
        ticket_doc["evaluations"] = _sort_evaluations(
            _upsert_list(ticket_doc.get("evaluations", []), evaluation, _evaluation_key)
        )
        ticket_doc["updated_at"] = utc_now_iso()
        paths.append(_write_ticket(path, ticket_doc))

    return paths


def upsert_comparison_payload(
    payload: dict[str, Any],
    tickets_dir: str | Path = DEFAULT_TICKETS_DIR,
    *,
    fixtures: str | Path | None = None,
) -> list[Path]:
    """Upsert every result in one comparison payload into ticket files."""
    fixture_cases = _fixture_lookup_for_payload(payload, fixtures)
    paths: list[Path] = []

    for result in payload.get("results", []):
        case_id = str(result.get("case_id") or "")
        if not case_id:
            continue

        path = run_ticket_file_path(tickets_dir, payload, case_id)
        ticket_doc = _load_existing_ticket(path, case_id)
        _apply_fixture_enrichment(ticket_doc, fixture_cases.get(case_id), result)

        rule = result.get("rule") or {}
        ai = result.get("ai") or {}
        disagreements = _classification_disagreements(rule.get("actual"), ai.get("actual"))
        comparison = {
            "generated_at": payload.get("generated_at"),
            "fixture_path": payload.get("fixture_path"),
            "provider": payload.get("provider"),
            "rule": rule,
            "ai": ai,
            "rule_passed": bool(result.get("rule_passed")),
            "ai_passed": bool(result.get("ai_passed")),
            "agreement": not disagreements,
            "disagreement_fields": disagreements,
        }
        ticket_doc["comparisons"] = _sort_comparisons(
            _upsert_list(ticket_doc.get("comparisons", []), comparison, _comparison_key)
        )
        ticket_doc["updated_at"] = utc_now_iso()
        paths.append(_write_ticket(path, ticket_doc))

    return paths


def convert_artifact_file(
    artifact_path: str | Path,
    tickets_dir: str | Path = DEFAULT_TICKETS_DIR,
    *,
    fixtures: str | Path | None = None,
) -> list[Path]:
    """Convert one run or comparison JSON artifact into ticket files."""
    payload = _read_json(artifact_path)
    schema_version = str(payload.get("schema_version") or "")
    if schema_version == "warp.ticket_eval_compare.v1" or "ai_source" in payload:
        return upsert_comparison_payload(payload, tickets_dir, fixtures=fixtures)
    return upsert_eval_run_payload(payload, tickets_dir, fixtures=fixtures)


def convert_runs_dir(
    runs_dir: str | Path,
    tickets_dir: str | Path = DEFAULT_TICKETS_DIR,
    *,
    fixtures: str | Path | None = None,
) -> list[Path]:
    """Convert JSON artifacts in a run directory into ticket-centric files."""
    paths: list[Path] = []
    for artifact_path in sorted(Path(runs_dir).glob("*.json")):
        if artifact_path.name == "latest.json":
            continue
        paths.extend(convert_artifact_file(artifact_path, tickets_dir, fixtures=fixtures))
    return sorted(set(paths), key=lambda path: str(path))


__all__ = [
    "TICKET_STORE_SCHEMA_VERSION",
    "DEFAULT_TICKETS_DIR",
    "safe_filename",
    "safe_case_filename",
    "safe_run_dirname",
    "run_folder_name",
    "ticket_file_path",
    "run_ticket_file_path",
    "load_fixture_tickets_by_case_id",
    "upsert_eval_run_payload",
    "upsert_comparison_payload",
    "convert_artifact_file",
    "convert_runs_dir",
]
