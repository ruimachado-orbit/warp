#!/usr/bin/env python3
"""Support triage, classification, SLA, routing, and reply drafting."""
import json
import re
import sys
from datetime import datetime, timezone

CATEGORY_RULES = {
    "billing": ["invoice", "billing", "charge", "payment", "refund", "subscription", "plan", "pricing", "vat"],
    "bug": ["bug", "error", "broken", "doesn't work", "not working", "crash", "failed", "failure", "exception", "stack trace"],
    "access": ["login", "password", "2fa", "mfa", "permission", "access", "account", "sso", "invite", "locked"],
    "how_to": ["how do i", "how can i", "where do i", "setup", "configure", "tutorial", "guide"],
    "feature_request": ["feature", "request", "would like", "can you add", "enhancement", "roadmap"],
    "data_privacy": ["gdpr", "delete my data", "personal data", "privacy", "dpa", "subprocessor", "export data"],
    "integration": ["api", "webhook", "integration", "zapier", "salesforce", "hubspot", "zendesk", "slack"],
}

SEVERITY_RULES = [
    ("critical", ["down", "outage", "production down", "can't access", "cannot access", "security breach", "data loss", "blocked", "all users"]),
    ("high", ["urgent", "asap", "major", "many users", "deadline", "cannot use", "broken for us"]),
    ("medium", ["issue", "problem", "not working", "bug", "help", "incorrect"]),
    ("low", ["question", "how", "minor", "cosmetic", "feature request", "nice to have"]),
]

NEGATIVE = ["angry", "frustrated", "unhappy", "terrible", "awful", "useless", "bad", "disappointed", "cancel"]
POSITIVE = ["thanks", "thank you", "great", "love", "helpful", "awesome"]

ROUTING = {
    "billing": "Billing / Finance Support",
    "bug": "Technical Support L2",
    "access": "Identity & Account Support",
    "how_to": "Customer Education / L1 Support",
    "feature_request": "Product Feedback Queue",
    "data_privacy": "Privacy / Legal Ops",
    "integration": "Integrations Support",
    "general": "Customer Support L1",
}

SLA_HOURS = {"critical": 1, "high": 4, "medium": 24, "low": 72}


def _score_keywords(text: str, rules: dict) -> dict:
    lower = text.lower()
    scores = {}
    for label, keywords in rules.items():
        scores[label] = sum(1 for kw in keywords if kw in lower)
    return scores


def classify(text: str) -> dict:
    text = text.strip()
    scores = _score_keywords(text, CATEGORY_RULES)
    category = max(scores, key=scores.get) if scores and max(scores.values()) > 0 else "general"

    lower = text.lower()
    severity = "low"
    for sev, keywords in SEVERITY_RULES:
        if any(kw in lower for kw in keywords):
            severity = sev
            break
    if category in {"data_privacy"} and severity in {"low", "medium"}:
        severity = "high"

    sentiment_score = sum(1 for w in POSITIVE if w in lower) - sum(1 for w in NEGATIVE if w in lower)
    sentiment = "negative" if sentiment_score < 0 else "positive" if sentiment_score > 0 else "neutral"

    language = "pt" if re.search(r"\b(não|obrigado|fatura|pagamento|erro|ajuda|urgente)\b", lower) else "en"
    requires_human = severity in {"critical", "high"} or sentiment == "negative" or category == "data_privacy"
    sla_hours = SLA_HOURS[severity]

    return {
        "category": category,
        "severity": severity,
        "priority": severity,
        "sentiment": sentiment,
        "language": language,
        "route_to": ROUTING.get(category, ROUTING["general"]),
        "sla_hours": sla_hours,
        "requires_human": requires_human,
        "confidence": round(min(0.95, 0.45 + (scores.get(category, 0) * 0.15) + (0.1 if severity != "low" else 0)), 2),
        "tags": sorted({category, severity, sentiment, language}),
    }


def draft_reply(text: str, classification: dict) -> str:
    category = classification["category"]
    severity = classification["severity"]
    route = classification["route_to"]
    if classification.get("language") == "pt":
        greeting = "Olá,"
        ack = "Obrigado por nos contactar — já identificámos o tema e vamos ajudar."
        human = "Vou encaminhar isto para a equipa certa para análise prioritária." if classification.get("requires_human") else "Vou deixar abaixo os próximos passos recomendados."
        close = "Obrigado pela paciência."
    else:
        greeting = "Hi,"
        ack = "Thanks for reaching out — I’ve reviewed the issue and classified it so we can help quickly."
        human = "I’m routing this to the right team for priority review." if classification.get("requires_human") else "Here are the recommended next steps."
        close = "Thanks for your patience."

    next_steps = {
        "billing": "Please confirm the account email, invoice number, and whether this is a refund, charge, or plan question.",
        "bug": "Please share the affected workspace, steps to reproduce, expected result, actual result, and any screenshots/logs.",
        "access": "Please confirm the affected user email, login method, and whether SSO/MFA is enabled.",
        "how_to": "Please confirm what outcome you are trying to achieve and the workspace/product area you are using.",
        "feature_request": "I’ll capture this as product feedback. If possible, please share the workflow and impact this would unlock.",
        "data_privacy": "For privacy/security reasons, we’ll handle this through the privacy process and may ask for identity verification.",
        "integration": "Please share the integration name, endpoint or workflow, timestamp, request ID if available, and any error response.",
        "general": "Please share any additional context that helps us reproduce or understand the request.",
    }.get(category, "Please share any additional context that helps us resolve this faster.")

    return f"{greeting}\n\n{ack}\n\nClassification: {category} / {severity}. {human}\n\nNext step: {next_steps}\n\nAssigned queue: {route}.\n\n{close}"


def run(args: list) -> dict:
    action = args[0] if args else "triage"
    text = " ".join(args[1:]) if len(args) > 1 else " ".join(args) if args else ""
    if action in {"classify", "triage", "draft"} and not text:
        text = sys.stdin.read().strip()
    classification = classify(text)
    result = {
        "tool": "support_triage",
        "ok": True,
        "action": action,
        "input_excerpt": text[:500],
        "classification": classification,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if action in {"draft", "triage"}:
        result["draft_reply"] = draft_reply(text, classification)
    return result


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1:]), indent=2, ensure_ascii=False))
