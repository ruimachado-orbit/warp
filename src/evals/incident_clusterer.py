"""AI incident clustering lane for support tickets."""

from __future__ import annotations

import hashlib
import json
import random as _random
from itertools import combinations
from pathlib import Path
from typing import Any

import llm_gateway
from ticket_model import utc_now_iso

DEFAULT_PROVIDER = "openrouter"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
OUTPUT_SCHEMA_VERSION = "warp.incident_clusterer.output.v1"
EVAL_SCHEMA_VERSION = "warp.incident_cluster_eval_result.v1"

_PROMPT_BASE_VERSION = "v1"

_SYSTEM_PROMPT_TEMPLATE = f"""\
You cluster Warp support tickets into shared incidents.

Prompt version: __PROMPT_VERSION__.
Output schema version: {OUTPUT_SCHEMA_VERSION}.

Role and task:
- Cluster Warp support tickets into shared incidents.
- Group tickets that describe the same underlying customer-impacting problem.
- Keep unrelated tickets as singleton clusters.

Grouping rules:
- Use evidence from product area, integration/provider, error message, symptom, affected workflow, and wording.
- Do not cluster tickets together just because they share a broad category like billing, access, or bug.
- Prefer concrete shared causes or symptoms over generic topic similarity.

Return one JSON object with this exact shape:
{{
  "schema_version": "{OUTPUT_SCHEMA_VERSION}",
  "prompt_version": "__PROMPT_VERSION__",
  "clusters": [
    {{
      "incident_id": "stable_snake_case_id",
      "kind": "incident",
      "summary": "one sentence describing the shared underlying issue",
      "ticket_ids": ["ticket-id-1", "ticket-id-2"],
      "confidence": 0.86,
      "signals": ["shared", "specific", "signals"]
    }},
    {{
      "incident_id": "stable_snake_case_singleton_id",
      "kind": "singleton",
      "summary": "one sentence describing this standalone request",
      "ticket_ids": ["ticket-id-3"],
      "confidence": 0.75,
      "signals": ["standalone", "signals"]
    }}
  ]
}}

Validation rules:
- Include every input ticket exactly once.
- Do not include unknown ticket IDs.
- Use kind="incident" for clusters with 2 or more tickets.
- Use kind="singleton" for clusters with exactly 1 ticket.
- Incident IDs must be unique stable snake_case strings.
- Confidence must be between 0 and 1.
- Signals must be short explanatory strings describing why the tickets belong together or stand alone.

Return valid JSON only. Do not include markdown fences, commentary, or extra text."""

_CONTENT_HASH = hashlib.sha256(_SYSTEM_PROMPT_TEMPLATE.encode()).hexdigest()[:8]
PROMPT_VERSION = f"warp.incident_clusterer.prompt.{_PROMPT_BASE_VERSION}.{_CONTENT_HASH}"
SYSTEM_PROMPT = _SYSTEM_PROMPT_TEMPLATE.replace("__PROMPT_VERSION__", PROMPT_VERSION)


class IncidentClustererObservabilityError(ValueError):
    """Clusterer parse/validation error carrying provider observability."""

    def __init__(self, message: str, observability: dict[str, Any]) -> None:
        super().__init__(message)
        self.observability = observability


def load_incident_fixture(path: str | Path) -> dict[str, Any]:
    """Load an incident clustering fixture JSON object."""
    fixture_path = Path(path)
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("incident fixture must be a JSON object")
    tickets = data.get("tickets")
    if not isinstance(tickets, list) or not tickets:
        raise ValueError("incident fixture must contain a non-empty tickets list")
    return data


def _ticket_for_prompt(ticket: dict[str, Any]) -> dict[str, Any]:
    """Return only model-visible ticket fields, excluding expected labels and fixture hints."""
    return {
        "ticket_id": ticket.get("ticket_id"),
        "subject": ticket.get("subject"),
        "body": ticket.get("body"),
        "channel": ticket.get("channel"),
    }


def build_cluster_prompt(tickets: list[dict[str, Any]]) -> str:
    """Build the user prompt containing only ticket IDs and visible ticket JSON."""
    visible_tickets = [_ticket_for_prompt(ticket) for ticket in tickets]
    seed = "\n".join(sorted(str(t.get("ticket_id", "")) for t in visible_tickets))
    rng = _random.Random(seed)
    rng.shuffle(visible_tickets)
    ticket_ids = [str(ticket.get("ticket_id")) for ticket in visible_tickets]
    return f"""Input ticket IDs: {json.dumps(ticket_ids, ensure_ascii=False)}

Tickets:
{json.dumps(visible_tickets, ensure_ascii=False, indent=2)}"""


def _parse_llm_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed LLM JSON response: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("malformed LLM JSON response: expected a JSON object")
    return data


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
    return {
        str(key): _sanitize_gateway_value(value)
        for key, value in result.items()
        if key != "text" and not _is_sensitive_key(str(key))
    }


def validate_cluster_output(data: dict[str, Any], input_ticket_ids: set[str]) -> dict[str, Any]:
    """Validate and normalize clusterer output."""
    if data.get("schema_version") != OUTPUT_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {OUTPUT_SCHEMA_VERSION}")
    if data.get("prompt_version") != PROMPT_VERSION:
        raise ValueError(f"prompt_version must be {PROMPT_VERSION}")
    clusters = data.get("clusters")
    if not isinstance(clusters, list) or not clusters:
        raise ValueError("clusters must be a non-empty list")

    seen_incident_ids: set[str] = set()
    seen_ticket_ids: set[str] = set()
    normalized_clusters: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters, start=1):
        if not isinstance(cluster, dict):
            raise ValueError(f"cluster {index} must be an object")
        incident_id = cluster.get("incident_id")
        if not isinstance(incident_id, str) or not incident_id.strip():
            raise ValueError(f"cluster {index}.incident_id must be a non-empty string")
        if incident_id in seen_incident_ids:
            raise ValueError(f"duplicate incident_id: {incident_id}")
        seen_incident_ids.add(incident_id)

        ticket_ids = cluster.get("ticket_ids")
        if not isinstance(ticket_ids, list) or not ticket_ids:
            raise ValueError(f"cluster {incident_id}.ticket_ids must be a non-empty list")
        if not all(isinstance(ticket_id, str) and ticket_id.strip() for ticket_id in ticket_ids):
            raise ValueError(f"cluster {incident_id}.ticket_ids must contain only non-empty strings")
        ticket_id_set = set(ticket_ids)
        if len(ticket_id_set) != len(ticket_ids):
            raise ValueError(f"cluster {incident_id} contains duplicate ticket IDs")
        unknown_ticket_ids = sorted(ticket_id_set - input_ticket_ids)
        if unknown_ticket_ids:
            raise ValueError(f"cluster {incident_id} references unknown ticket IDs: {unknown_ticket_ids}")
        duplicate_assignments = sorted(ticket_id_set & seen_ticket_ids)
        if duplicate_assignments:
            raise ValueError(f"tickets assigned to multiple clusters: {duplicate_assignments}")
        seen_ticket_ids.update(ticket_id_set)

        expected_kind = "singleton" if len(ticket_ids) == 1 else "incident"
        kind = cluster.get("kind")
        if kind != expected_kind:
            raise ValueError(f"cluster {incident_id}.kind must be {expected_kind}")
        summary = cluster.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(f"cluster {incident_id}.summary must be a non-empty string")
        signals = cluster.get("signals")
        if not isinstance(signals, list) or not signals:
            raise ValueError(f"cluster {incident_id}.signals must be a non-empty list")
        if not all(isinstance(signal, str) and signal.strip() for signal in signals):
            raise ValueError(f"cluster {incident_id}.signals must contain only non-empty strings")
        confidence = cluster.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise ValueError(f"cluster {incident_id}.confidence must be a number")
        if not 0 <= float(confidence) <= 1:
            raise ValueError(f"cluster {incident_id}.confidence must be between 0 and 1")

        normalized_clusters.append(
            {
                "incident_id": incident_id,
                "kind": kind,
                "summary": summary,
                "ticket_ids": ticket_ids,
                "confidence": float(confidence),
                "signals": signals,
            }
        )

    missing_ticket_ids = sorted(input_ticket_ids - seen_ticket_ids)
    if missing_ticket_ids:
        raise ValueError(f"clusters missing input ticket IDs: {missing_ticket_ids}")

    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "clusters": normalized_clusters,
    }


def _cluster_pairs(clusters: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for cluster in clusters:
        for left, right in combinations(sorted(cluster.get("ticket_ids", [])), 2):
            pairs.add((left, right))
    return pairs


def score_clusters(
    predicted_clusters: list[dict[str, Any]], expected_clusters: list[dict[str, Any]]
) -> dict[str, Any]:
    """Score predicted clusters using pairwise precision/recall/F1."""
    predicted_pairs = _cluster_pairs(predicted_clusters)
    expected_pairs = _cluster_pairs(expected_clusters)
    true_positive = len(predicted_pairs & expected_pairs)
    false_positive = len(predicted_pairs - expected_pairs)
    false_negative = len(expected_pairs - predicted_pairs)
    precision = true_positive / (true_positive + false_positive) if predicted_pairs else 0.0
    recall = true_positive / (true_positive + false_negative) if expected_pairs else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "pairwise_true_positive": true_positive,
        "pairwise_false_positive": false_positive,
        "pairwise_false_negative": false_negative,
        "pairwise_precision": precision,
        "pairwise_recall": recall,
        "pairwise_f1": f1,
        "predicted_pair_count": len(predicted_pairs),
        "expected_pair_count": len(expected_pairs),
    }


def _cluster_tickets_with_observability(
    tickets: list[dict[str, Any]],
    *,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt = build_cluster_prompt(tickets)
    result = llm_gateway.call_with_fallback(
        prompt,
        providers=[provider],
        system=SYSTEM_PROMPT,
        max_tokens=8192,
        temperature=0.0,
        json_output=True,
        model=model,
    )
    if not result.get("ok"):
        raise RuntimeError(f"LLM provider {provider} failed: {result.get('error') or 'unknown error'}")

    raw_text = str(result.get("text") or "")
    resolved_provider = result.get("provider") or provider
    resolved_model = result.get("model") or model
    observability = {
        "provider": resolved_provider,
        "model": resolved_model,
        "source": f"llm:{resolved_provider}/{resolved_model}",
        "llm_prompt": prompt,
        "llm_system": SYSTEM_PROMPT,
        "llm_raw_text": raw_text,
        "llm_gateway": _gateway_observability(result),
    }
    try:
        data = _parse_llm_json(raw_text)
        output = validate_cluster_output(
            data,
            {str(ticket.get("ticket_id")) for ticket in tickets},
        )
    except ValueError as exc:
        raise IncidentClustererObservabilityError(str(exc), observability) from exc
    return output, observability


def cluster_tickets(
    tickets: list[dict[str, Any]],
    *,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Cluster a list of ticket dicts into incidents using the configured AI model."""
    output, _metadata = _cluster_tickets_with_observability(tickets, provider=provider, model=model)
    return output


def evaluate_file(
    path: str | Path,
    *,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Cluster an incident fixture and score predictions against expected clusters."""
    fixture = load_incident_fixture(path)
    tickets = fixture["tickets"]
    expected_clusters = fixture.get("expected_clusters") or []
    if not isinstance(expected_clusters, list) or not expected_clusters:
        raise ValueError("incident fixture must contain a non-empty expected_clusters list")

    output, observability = _cluster_tickets_with_observability(tickets, provider=provider, model=model)
    predicted_clusters = output["clusters"]
    metrics = score_clusters(predicted_clusters, expected_clusters)
    return {
        "schema_version": EVAL_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "fixture_path": str(path),
        "provider": provider,
        "model": model,
        "source": f"llm:{provider}/{model}",
        "prompt_version": PROMPT_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "total_tickets": len(tickets),
        "expected_cluster_count": len(expected_clusters),
        "predicted_cluster_count": len(predicted_clusters),
        "ok": metrics["pairwise_f1"] == 1.0,
        "metrics": metrics,
        "predicted_clusters": predicted_clusters,
        "expected_clusters": expected_clusters,
        "metadata": {key: value for key, value in observability.items() if value is not None},
    }


def write_eval_json(payload: dict[str, Any], output_path: str | Path) -> Path:
    """Write an incident clustering eval payload as stable, pretty JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


__all__ = [
    "DEFAULT_PROVIDER",
    "DEFAULT_MODEL",
    "PROMPT_VERSION",
    "OUTPUT_SCHEMA_VERSION",
    "EVAL_SCHEMA_VERSION",
    "SYSTEM_PROMPT",
    "build_cluster_prompt",
    "cluster_tickets",
    "evaluate_file",
    "load_incident_fixture",
    "score_clusters",
    "validate_cluster_output",
    "write_eval_json",
]
