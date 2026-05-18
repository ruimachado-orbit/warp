"""Generate synthetic eval fixtures using the configured LLM gateway."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import llm_gateway
from ticket_model import CATEGORY_VALUES, SENTIMENT_VALUES, SEVERITY_VALUES, TicketEvalCase

DEFAULT_OUTPUT_PATH = Path("tests/fixtures/ticket_eval_cases.json")
DEFAULT_INCIDENT_OUTPUT_PATH = Path("tests/fixtures/incident_cluster_eval_cases.json")
DEFAULT_COUNT = 22
DEFAULT_INCIDENT_COUNT = 5
DEFAULT_TICKETS_PER_INCIDENT = 4
DEFAULT_SINGLETON_COUNT = 5
DEFAULT_PROVIDER = "codex_app_server"
INCIDENT_CLUSTER_SCHEMA_VERSION = "warp.incident_cluster_eval.v1"


SYSTEM_PROMPT = """You generate realistic customer support ticket evaluation fixtures for Warp.
Return valid JSON only. Do not include markdown fences, commentary, or extra text."""

INCIDENT_SYSTEM_PROMPT = """You generate realistic incident clustering evaluation fixtures for Warp support tickets.
Return valid JSON only. Do not include markdown fences, commentary, or extra text."""


def build_generation_prompt(count: int) -> str:
    """Build the JSON-only prompt for synthetic ticket fixture generation."""
    categories = ", ".join(sorted(CATEGORY_VALUES))
    severities = ", ".join(sorted(SEVERITY_VALUES))
    sentiments = ", ".join(sorted(SENTIMENT_VALUES))

    return f"""Generate exactly {count} synthetic support ticket eval cases.

Return a single JSON object with this shape:
{{
  "cases": [
    {{
      "case_id": "short_snake_case_unique_id",
      "name": "short human-readable name",
      "description": "one sentence explaining what the fixture covers",
      "ticket": {{
        "id": "SYN-001",
        "subject": "realistic customer ticket subject",
        "body": "realistic support ticket body with enough context to classify",
        "source": "synthetic",
        "channel": "email",
        "language": "en",
        "metadata": {{"synthetic": true}}
      }},
      "expected": {{
        "category": "one allowed category",
        "severity": "one allowed severity",
        "priority": "same as severity unless there is a clear reason",
        "sentiment": "one allowed sentiment",
        "language": "en",
        "route_to": "expected queue name",
        "sla_hours": 24,
        "requires_human": true,
        "tags_contains": ["category-or-signal-tag"]
      }},
      "metadata": {{"generator": "llm"}}
    }}
  ]
}}

Allowed category values: {categories}
Allowed severity and priority values: {severities}
Allowed sentiment values: {sentiments}

Use realistic support scenarios across billing, bugs, access, how-to questions, feature requests,
data privacy, integrations, and general inquiries. Use exact route_to values from this list only:
Billing / Finance Support; Technical Support L2; Identity & Account Support;
Customer Education / L1 Support; Product Feedback Queue; Privacy / Legal Ops;
Integrations Support; Customer Support L1.
Keep case_id values unique and stable-looking. Do not invent enum values or route names.
Do not omit required case_id, ticket.id, ticket.subject, ticket.body, or expected labels."""


def build_incident_generation_prompt(
    incident_count: int,
    tickets_per_incident: int,
    singleton_count: int,
) -> str:
    """Build the JSON-only prompt for synthetic incident clustering fixture generation."""
    total_tickets = incident_count * tickets_per_incident + singleton_count
    expected_cluster_count = incident_count + singleton_count
    return f"""Generate an incident clustering eval fixture for customer support tickets.

Create exactly:
- {incident_count} multi-ticket incidents
- {tickets_per_incident} tickets per multi-ticket incident
- {singleton_count} unrelated singleton tickets
- {total_tickets} total tickets
- {expected_cluster_count} expected clusters

Return a single JSON object with this exact top-level shape:
{{
  "schema_version": "{INCIDENT_CLUSTER_SCHEMA_VERSION}",
  "name": "Incident clustering eval fixture",
  "description": "short description",
  "tickets": [
    {{
      "ticket_id": "IC-INCIDENT-001",
      "subject": "realistic support ticket subject",
      "body": "realistic support ticket body",
      "channel": "email",
      "created_at": "2026-05-18T10:00:00Z",
      "expected_incident_id": "stable_snake_case_incident_id",
      "signals": ["shared", "incident", "signals"]
    }}
  ],
  "expected_clusters": [
    {{
      "incident_id": "stable_snake_case_incident_id",
      "kind": "incident",
      "summary": "one sentence describing the shared underlying incident",
      "signals": ["shared", "incident", "signals"],
      "ticket_ids": ["IC-INCIDENT-001", "IC-INCIDENT-002"]
    }},
    {{
      "incident_id": "stable_snake_case_singleton_id",
      "kind": "singleton",
      "summary": "one sentence explaining why this ticket is unrelated",
      "signals": ["singleton", "signals"],
      "ticket_ids": ["IC-SINGLE-001"]
    }}
  ],
  "evaluation_notes": {{
    "primary_metric": "pairwise clustering precision/recall/F1 over ticket_id pairs",
    "positive_pairs": "tickets sharing the same expected_incident_id",
    "negative_pairs": "tickets with different expected_incident_id values, including singleton tickets",
    "singleton_policy": "singleton tickets should remain alone unless a future fixture intentionally links them to an incident"
  }}
}}

Rules:
- Multi-ticket incidents must describe the same underlying customer-impacting problem with varied wording.
- Singleton tickets must be plausible support requests but unrelated to every other ticket.
- Every ticket_id must be unique.
- Every incident_id must be unique and stable snake_case.
- Every ticket.expected_incident_id must match exactly one expected_clusters[].incident_id.
- Every expected_clusters[].ticket_ids entry must refer to an existing ticket_id.
- Each incident cluster must contain exactly {tickets_per_incident} ticket IDs.
- Each singleton cluster must contain exactly 1 ticket ID.
- Use specific shared signals such as product area, error message, integration, provider, symptom, timeframe, or affected workflow.
- Do not include markdown fences, comments, or extra text outside the JSON object."""


def parse_llm_json(text: str) -> dict[str, Any]:
    """Parse an LLM JSON response into a dict."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response was not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    return data


def validate_cases_payload(data: dict[str, Any], expected_count: int) -> list[TicketEvalCase]:
    """Validate generated fixture data through TicketEvalCase.from_dict."""
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("generated JSON must contain a cases list")
    if len(raw_cases) != expected_count:
        raise ValueError(f"generated {len(raw_cases)} cases, expected {expected_count}")

    cases: list[TicketEvalCase] = []
    seen_case_ids: set[str] = set()
    seen_ticket_ids: set[str] = set()
    for index, raw_case in enumerate(raw_cases, start=1):
        try:
            case = TicketEvalCase.from_dict(raw_case)
        except Exception as exc:
            raise ValueError(f"case {index} is invalid: {exc}") from exc
        if case.case_id in seen_case_ids:
            raise ValueError(f"duplicate case_id: {case.case_id}")
        if case.ticket.id in seen_ticket_ids:
            raise ValueError(f"duplicate ticket.id: {case.ticket.id}")
        seen_case_ids.add(case.case_id)
        seen_ticket_ids.add(case.ticket.id)
        cases.append(case)
    return cases


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label} must contain only non-empty strings")
    return value


def validate_incident_payload(
    data: dict[str, Any],
    *,
    expected_incident_count: int = DEFAULT_INCIDENT_COUNT,
    expected_tickets_per_incident: int = DEFAULT_TICKETS_PER_INCIDENT,
    expected_singleton_count: int = DEFAULT_SINGLETON_COUNT,
) -> dict[str, Any]:
    """Validate generated incident clustering fixture data."""
    if data.get("schema_version") != INCIDENT_CLUSTER_SCHEMA_VERSION:
        raise ValueError(f"generated JSON must use schema_version {INCIDENT_CLUSTER_SCHEMA_VERSION}")

    tickets = data.get("tickets")
    clusters = data.get("expected_clusters")
    if not isinstance(tickets, list):
        raise ValueError("generated JSON must contain a tickets list")
    if not isinstance(clusters, list):
        raise ValueError("generated JSON must contain an expected_clusters list")

    expected_ticket_count = expected_incident_count * expected_tickets_per_incident + expected_singleton_count
    expected_cluster_count = expected_incident_count + expected_singleton_count
    if len(tickets) != expected_ticket_count:
        raise ValueError(f"generated {len(tickets)} tickets, expected {expected_ticket_count}")
    if len(clusters) != expected_cluster_count:
        raise ValueError(f"generated {len(clusters)} clusters, expected {expected_cluster_count}")

    seen_ticket_ids: set[str] = set()
    ticket_incidents: dict[str, str] = {}
    for index, ticket in enumerate(tickets, start=1):
        if not isinstance(ticket, dict):
            raise ValueError(f"ticket {index} must be an object")
        ticket_id = _require_string(ticket.get("ticket_id"), f"ticket {index}.ticket_id")
        if ticket_id in seen_ticket_ids:
            raise ValueError(f"duplicate ticket_id: {ticket_id}")
        seen_ticket_ids.add(ticket_id)
        ticket_incidents[ticket_id] = _require_string(
            ticket.get("expected_incident_id"), f"ticket {index}.expected_incident_id"
        )
        _require_string(ticket.get("subject"), f"ticket {index}.subject")
        _require_string(ticket.get("body"), f"ticket {index}.body")
        _require_string_list(ticket.get("signals"), f"ticket {index}.signals")

    seen_cluster_ids: set[str] = set()
    cluster_ticket_ids: set[str] = set()
    incident_count = 0
    singleton_count = 0
    cluster_by_ticket_id: dict[str, str] = {}
    for index, cluster in enumerate(clusters, start=1):
        if not isinstance(cluster, dict):
            raise ValueError(f"cluster {index} must be an object")
        incident_id = _require_string(cluster.get("incident_id"), f"cluster {index}.incident_id")
        if incident_id in seen_cluster_ids:
            raise ValueError(f"duplicate incident_id: {incident_id}")
        seen_cluster_ids.add(incident_id)
        kind = cluster.get("kind")
        if kind not in {"incident", "singleton"}:
            raise ValueError(f"cluster {index}.kind must be incident or singleton")
        ticket_ids = _require_string_list(cluster.get("ticket_ids"), f"cluster {index}.ticket_ids")
        if kind == "incident":
            incident_count += 1
            if len(ticket_ids) != expected_tickets_per_incident:
                raise ValueError(
                    f"incident cluster {incident_id} has {len(ticket_ids)} tickets, expected {expected_tickets_per_incident}"
                )
        else:
            singleton_count += 1
            if len(ticket_ids) != 1:
                raise ValueError(f"singleton cluster {incident_id} must have exactly 1 ticket")
        _require_string(cluster.get("summary"), f"cluster {index}.summary")
        _require_string_list(cluster.get("signals"), f"cluster {index}.signals")
        for ticket_id in ticket_ids:
            if ticket_id not in seen_ticket_ids:
                raise ValueError(f"cluster {incident_id} references unknown ticket_id: {ticket_id}")
            if ticket_id in cluster_ticket_ids:
                raise ValueError(f"ticket_id appears in multiple clusters: {ticket_id}")
            cluster_ticket_ids.add(ticket_id)
            cluster_by_ticket_id[ticket_id] = incident_id

    if incident_count != expected_incident_count:
        raise ValueError(f"generated {incident_count} incident clusters, expected {expected_incident_count}")
    if singleton_count != expected_singleton_count:
        raise ValueError(f"generated {singleton_count} singleton clusters, expected {expected_singleton_count}")
    if cluster_ticket_ids != seen_ticket_ids:
        missing = sorted(seen_ticket_ids - cluster_ticket_ids)
        raise ValueError(f"expected_clusters missing ticket_ids: {missing}")
    if set(ticket_incidents.values()) != seen_cluster_ids:
        raise ValueError("ticket expected_incident_id values must match expected cluster incident_id values")
    for ticket_id, expected_incident_id in ticket_incidents.items():
        if cluster_by_ticket_id[ticket_id] != expected_incident_id:
            raise ValueError(
                f"ticket {ticket_id} expected_incident_id {expected_incident_id} does not match cluster {cluster_by_ticket_id[ticket_id]}"
            )

    notes = data.get("evaluation_notes")
    if not isinstance(notes, dict) or "pairwise" not in str(notes.get("primary_metric", "")):
        raise ValueError("generated JSON must contain pairwise evaluation_notes.primary_metric")

    return data


def serialize_fixture(cases: list[TicketEvalCase]) -> str:
    """Serialize eval cases using the repository fixture format."""
    payload = {"cases": [case.to_dict() for case in cases]}
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def serialize_incident_fixture(payload: dict[str, Any]) -> str:
    """Serialize an incident clustering fixture."""
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def generate_cases(count: int = DEFAULT_COUNT, provider: str = DEFAULT_PROVIDER) -> list[TicketEvalCase]:
    """Generate and validate synthetic ticket eval cases from an LLM provider."""
    if count <= 0:
        raise ValueError("count must be positive")

    result = llm_gateway.call_with_fallback(
        build_generation_prompt(count),
        providers=[provider],
        system=SYSTEM_PROMPT,
        max_tokens=12000,
        temperature=0.4,
        json_output=True,
    )
    if not result.get("ok"):
        raise RuntimeError(f"LLM provider failed: {result.get('error') or 'unknown error'}")

    data = parse_llm_json(str(result.get("text") or ""))
    return validate_cases_payload(data, count)


def generate_incident_fixture(
    *,
    incident_count: int = DEFAULT_INCIDENT_COUNT,
    tickets_per_incident: int = DEFAULT_TICKETS_PER_INCIDENT,
    singleton_count: int = DEFAULT_SINGLETON_COUNT,
    provider: str = DEFAULT_PROVIDER,
) -> dict[str, Any]:
    """Generate and validate synthetic incident clustering fixtures from an LLM provider."""
    if incident_count <= 0:
        raise ValueError("incident_count must be positive")
    if tickets_per_incident <= 1:
        raise ValueError("tickets_per_incident must be greater than 1")
    if singleton_count < 0:
        raise ValueError("singleton_count must be non-negative")

    result = llm_gateway.call_with_fallback(
        build_incident_generation_prompt(incident_count, tickets_per_incident, singleton_count),
        providers=[provider],
        system=INCIDENT_SYSTEM_PROMPT,
        max_tokens=16000,
        temperature=0.45,
        json_output=True,
    )
    if not result.get("ok"):
        raise RuntimeError(f"LLM provider failed: {result.get('error') or 'unknown error'}")

    data = parse_llm_json(str(result.get("text") or ""))
    return validate_incident_payload(
        data,
        expected_incident_count=incident_count,
        expected_tickets_per_incident=tickets_per_incident,
        expected_singleton_count=singleton_count,
    )


def write_fixture(cases: list[TicketEvalCase], output_path: str | Path) -> None:
    """Write generated cases to a JSON fixture file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_fixture(cases), encoding="utf-8")


def write_incident_fixture(payload: dict[str, Any], output_path: str | Path) -> None:
    """Write generated incident clustering data to a JSON fixture file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_incident_fixture(payload), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate synthetic eval fixtures with the configured LLM gateway."
    )
    parser.add_argument(
        "--kind",
        choices=["tickets", "incidents"],
        default="tickets",
        help="Fixture kind to generate (default: tickets).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            f"Output fixture path (default: {DEFAULT_OUTPUT_PATH} for tickets, "
            f"{DEFAULT_INCIDENT_OUTPUT_PATH} for incidents)"
        ),
    )
    parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=None,
        help=(
            f"Number of ticket cases, or number of multi-ticket incidents when --kind incidents "
            f"(defaults: {DEFAULT_COUNT} tickets, {DEFAULT_INCIDENT_COUNT} incidents)."
        ),
    )
    parser.add_argument(
        "--tickets-per-incident",
        type=int,
        default=DEFAULT_TICKETS_PER_INCIDENT,
        help=f"Tickets per multi-ticket incident when --kind incidents (default: {DEFAULT_TICKETS_PER_INCIDENT}).",
    )
    parser.add_argument(
        "--singletons",
        type=int,
        default=DEFAULT_SINGLETON_COUNT,
        help=f"Unrelated singleton tickets when --kind incidents (default: {DEFAULT_SINGLETON_COUNT}).",
    )
    parser.add_argument(
        "-p",
        "--provider",
        default=DEFAULT_PROVIDER,
        help=f"LLM provider to use (default: {DEFAULT_PROVIDER})",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the generated fixture JSON instead of writing a file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate cases, then report without writing a file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        if args.kind == "tickets":
            count = args.count if args.count is not None else DEFAULT_COUNT
            output = args.output or str(DEFAULT_OUTPUT_PATH)
            cases = generate_cases(count=count, provider=args.provider)
            if args.stdout:
                print(serialize_fixture(cases), end="")
            elif args.dry_run:
                print(f"Generated and validated {len(cases)} cases; no file written.")
            else:
                write_fixture(cases, output)
                print(f"Wrote {len(cases)} cases to {output}")
        else:
            incident_count = args.count if args.count is not None else DEFAULT_INCIDENT_COUNT
            output = args.output or str(DEFAULT_INCIDENT_OUTPUT_PATH)
            payload = generate_incident_fixture(
                incident_count=incident_count,
                tickets_per_incident=args.tickets_per_incident,
                singleton_count=args.singletons,
                provider=args.provider,
            )
            tickets = payload["tickets"]
            clusters = payload["expected_clusters"]
            if args.stdout:
                print(serialize_incident_fixture(payload), end="")
            elif args.dry_run:
                print(
                    f"Generated and validated {len(tickets)} incident tickets across {len(clusters)} clusters; no file written."
                )
            else:
                write_incident_fixture(payload, output)
                print(f"Wrote {len(tickets)} incident tickets across {len(clusters)} clusters to {output}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
