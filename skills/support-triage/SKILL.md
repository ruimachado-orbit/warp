---
name: support-triage
description: Triage a customer support ticket/conversation into category, severity, sentiment, SLA, queue, tags, next action, and draft reply. Use whenever a user asks to classify, prioritize, route, or respond to support tickets.
version: 1.0.0
author: Maio Labs
license: MIT
---

# Support Triage

Use this skill for every customer ticket unless the user explicitly asks for a raw system lookup.

## Required output

1. Category: billing, bug, access, how-to, feature request, privacy, integration, or general.
2. Severity: critical, high, medium, low.
3. Sentiment: positive, neutral, negative.
4. SLA target.
5. Queue/owner.
6. Tags.
7. Missing information.
8. Draft customer reply.
9. Internal note if escalation is needed.

## Safety

Do not send replies or update tickets without explicit execution confirmation/tool success.
