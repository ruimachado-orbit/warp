---
name: helpdesk-operations
description: Operate common helpdesk systems safely: Zendesk, Intercom, Freshdesk, Salesforce Service Cloud, HubSpot Service Hub, Jira Service Management, Front, and Help Scout.
version: 1.0.0
author: Maio Labs
license: MIT
---

# Helpdesk Operations

## Standard workflow

1. Identify source system and ticket/conversation/case ID.
2. Read current state.
3. Run support triage.
4. Prepare payload: tags, priority, assignment, internal note, customer reply.
5. Present dry-run payload.
6. Execute only after explicit approval or `--execute`.
7. Re-read ticket to verify the mutation.

## Escalate immediately

- production outage
- data/privacy/security issue
- enterprise account blocked
- billing dispute with churn risk
- negative sentiment with high severity
