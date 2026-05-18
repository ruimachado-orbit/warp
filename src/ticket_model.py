"""Canonical ticket and classification evaluation models for Warp."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


CATEGORY_VALUES = {
    "billing",
    "bug",
    "access",
    "how_to",
    "feature_request",
    "data_privacy",
    "integration",
    "general",
}
SEVERITY_VALUES = {"critical", "high", "medium", "low"}
SENTIMENT_VALUES = {"positive", "neutral", "negative"}


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_dict(value: dict[str, Any] | None, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dict")
    return value


def _ensure_list(value: list[Any] | None, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    return value


def _validate_choice(value: str | None, allowed: set[str], field_name: str) -> None:
    if value is not None and value not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}")


def _validate_confidence(value: float | None, field_name: str = "confidence") -> None:
    if value is None:
        return
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")


@dataclass
class TicketInput:
    """Canonical representation of a support ticket."""

    id: str
    subject: str = ""
    body: str = ""
    source: str = "synthetic"
    channel: str | None = None
    requester_id: str | None = None
    account_id: str | None = None
    created_at: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "warp.ticket_input.v1"

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("TicketInput.id is required")
        self.metadata = _ensure_dict(self.metadata, "metadata")

    @property
    def classification_text(self) -> str:
        """Text passed to the per-ticket classifier."""
        parts = [part.strip() for part in (self.subject, self.body) if part and part.strip()]
        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TicketInput":
        if not isinstance(data, dict):
            raise TypeError("TicketInput.from_dict requires a dict")
        return cls(
            id=str(data.get("id") or data.get("ticket_id") or ""),
            subject=str(data.get("subject") or ""),
            body=str(data.get("body") or data.get("text") or data.get("description") or ""),
            source=str(data.get("source") or "synthetic"),
            channel=data.get("channel"),
            requester_id=data.get("requester_id"),
            account_id=data.get("account_id"),
            created_at=data.get("created_at"),
            language=data.get("language"),
            metadata=_ensure_dict(data.get("metadata"), "metadata"),
            schema_version=str(data.get("schema_version") or "warp.ticket_input.v1"),
        )


@dataclass
class ClassificationResult:
    """Structured output of support_triage.classify()."""

    category: str
    severity: str
    priority: str
    sentiment: str
    language: str
    route_to: str
    sla_hours: int
    requires_human: bool
    confidence: float
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "warp.classification_result.v1"

    def __post_init__(self) -> None:
        _validate_choice(self.category, CATEGORY_VALUES, "category")
        _validate_choice(self.severity, SEVERITY_VALUES, "severity")
        _validate_choice(self.priority, SEVERITY_VALUES, "priority")
        _validate_choice(self.sentiment, SENTIMENT_VALUES, "sentiment")
        if not self.language:
            raise ValueError("language is required")
        if not self.route_to:
            raise ValueError("route_to is required")
        if int(self.sla_hours) < 0:
            raise ValueError("sla_hours must be non-negative")
        _validate_confidence(self.confidence)
        self.sla_hours = int(self.sla_hours)
        self.requires_human = bool(self.requires_human)
        self.confidence = float(self.confidence)
        self.tags = [str(tag) for tag in _ensure_list(self.tags, "tags")]
        self.metadata = _ensure_dict(self.metadata, "metadata")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassificationResult":
        if not isinstance(data, dict):
            raise TypeError("ClassificationResult.from_dict requires a dict")
        severity = str(data.get("severity") or "low")
        return cls(
            category=str(data.get("category") or "general"),
            severity=severity,
            priority=str(data.get("priority") or severity),
            sentiment=str(data.get("sentiment") or "neutral"),
            language=str(data.get("language") or "en"),
            route_to=str(data.get("route_to") or "Customer Support L1"),
            sla_hours=int(data.get("sla_hours") if data.get("sla_hours") is not None else 72),
            requires_human=bool(data.get("requires_human", False)),
            confidence=float(data.get("confidence") if data.get("confidence") is not None else 0.0),
            tags=[str(tag) for tag in _ensure_list(data.get("tags"), "tags")],
            metadata=_ensure_dict(data.get("metadata"), "metadata"),
            schema_version=str(data.get("schema_version") or "warp.classification_result.v1"),
        )


def fallback_classification() -> ClassificationResult:
    """Return the canonical fallback classification used for eval failures."""
    return ClassificationResult(
        category="general",
        severity="low",
        priority="low",
        sentiment="neutral",
        language="en",
        route_to="Customer Support L1",
        sla_hours=72,
        requires_human=False,
        confidence=0.0,
        tags=[],
    )


@dataclass
class ExpectedClassification:
    """Gold labels and assertions for classification evaluation."""

    category: str | None = None
    severity: str | None = None
    priority: str | None = None
    sentiment: str | None = None
    language: str | None = None
    route_to: str | None = None
    sla_hours: int | None = None
    requires_human: bool | None = None
    allowed_categories: list[str] = field(default_factory=list)
    allowed_severities: list[str] = field(default_factory=list)
    tags_exact: list[str] | None = None
    tags_contains: list[str] = field(default_factory=list)
    min_confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "warp.expected_classification.v1"

    def __post_init__(self) -> None:
        _validate_choice(self.category, CATEGORY_VALUES, "category")
        _validate_choice(self.severity, SEVERITY_VALUES, "severity")
        _validate_choice(self.priority, SEVERITY_VALUES, "priority")
        _validate_choice(self.sentiment, SENTIMENT_VALUES, "sentiment")
        for value in self.allowed_categories:
            _validate_choice(value, CATEGORY_VALUES, "allowed_categories")
        for value in self.allowed_severities:
            _validate_choice(value, SEVERITY_VALUES, "allowed_severities")
        _validate_confidence(self.min_confidence, "min_confidence")
        self.metadata = _ensure_dict(self.metadata, "metadata")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ExpectedClassification":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise TypeError("ExpectedClassification.from_dict requires a dict")
        return cls(
            category=data.get("category"),
            severity=data.get("severity"),
            priority=data.get("priority"),
            sentiment=data.get("sentiment"),
            language=data.get("language"),
            route_to=data.get("route_to"),
            sla_hours=data.get("sla_hours"),
            requires_human=data.get("requires_human"),
            allowed_categories=[str(v) for v in _ensure_list(data.get("allowed_categories"), "allowed_categories")],
            allowed_severities=[str(v) for v in _ensure_list(data.get("allowed_severities"), "allowed_severities")],
            tags_exact=data.get("tags_exact"),
            tags_contains=[str(v) for v in _ensure_list(data.get("tags_contains"), "tags_contains")],
            min_confidence=data.get("min_confidence"),
            metadata=_ensure_dict(data.get("metadata"), "metadata"),
            schema_version=str(data.get("schema_version") or "warp.expected_classification.v1"),
        )


@dataclass
class TicketEvalCase:
    """One ticket fixture plus expected classification labels."""

    case_id: str
    ticket: TicketInput
    expected: ExpectedClassification
    name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "warp.ticket_eval_case.v1"

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id is required")
        self.ticket = self.ticket if isinstance(self.ticket, TicketInput) else TicketInput.from_dict(self.ticket)
        self.expected = (
            self.expected
            if isinstance(self.expected, ExpectedClassification)
            else ExpectedClassification.from_dict(self.expected)
        )
        self.metadata = _ensure_dict(self.metadata, "metadata")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ticket"] = self.ticket.to_dict()
        data["expected"] = self.expected.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TicketEvalCase":
        if not isinstance(data, dict):
            raise TypeError("TicketEvalCase.from_dict requires a dict")
        return cls(
            case_id=str(data.get("case_id") or data.get("id") or ""),
            ticket=TicketInput.from_dict(data.get("ticket") or {}),
            expected=ExpectedClassification.from_dict(data.get("expected")),
            name=data.get("name"),
            description=data.get("description"),
            metadata=_ensure_dict(data.get("metadata"), "metadata"),
            schema_version=str(data.get("schema_version") or "warp.ticket_eval_case.v1"),
        )


@dataclass
class TicketEvalResult:
    """Result of evaluating one ticket classification."""

    case_id: str
    actual: ClassificationResult
    expected: ExpectedClassification
    passed: bool
    failures: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "warp.ticket_eval_result.v1"

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id is required")
        self.actual = self.actual if isinstance(self.actual, ClassificationResult) else ClassificationResult.from_dict(self.actual)
        self.expected = (
            self.expected
            if isinstance(self.expected, ExpectedClassification)
            else ExpectedClassification.from_dict(self.expected)
        )
        self.failures = [str(failure) for failure in _ensure_list(self.failures, "failures")]
        self.metadata = _ensure_dict(self.metadata, "metadata")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["actual"] = self.actual.to_dict()
        data["expected"] = self.expected.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TicketEvalResult":
        if not isinstance(data, dict):
            raise TypeError("TicketEvalResult.from_dict requires a dict")
        return cls(
            case_id=str(data.get("case_id") or ""),
            actual=ClassificationResult.from_dict(data.get("actual") or {}),
            expected=ExpectedClassification.from_dict(data.get("expected")),
            passed=bool(data.get("passed", False)),
            failures=[str(v) for v in _ensure_list(data.get("failures"), "failures")],
            generated_at=str(data.get("generated_at") or utc_now_iso()),
            metadata=_ensure_dict(data.get("metadata"), "metadata"),
            schema_version=str(data.get("schema_version") or "warp.ticket_eval_result.v1"),
        )
