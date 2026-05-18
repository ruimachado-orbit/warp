# Warp

Autonomous customer support operations agent built in the Axeng style. It connects to common helpdesk/CRM systems, classifies tickets, routes work, drafts replies, searches knowledge, and keeps support operations disciplined.

## What it does

- Triage: category, severity, sentiment, priority, SLA, tags, queue.
- Classification: billing, bug, access, how-to, feature request, privacy, integration, general.
- Routing: L1, L2 technical support, billing, privacy/legal, product feedback, integrations.
- Drafting: safe customer replies and internal notes.
- Knowledge: local Markdown KB search for macros, policy, troubleshooting.
- Helpdesk operations: search/read/update patterns for major support systems.
- Safe execution: external mutations default to dry-run unless called with `--execute`.

## Supported systems

Primary systems:

- Zendesk Support
- Intercom
- Freshdesk
- Salesforce Service Cloud
- HubSpot Service Hub
- Jira Service Management
- Front
- Help Scout

Collaboration / knowledge:

- Slack
- Notion
- Local Markdown KB under `knowledge/`

## Quick start

```bash
cd warp
cp .env.example .env
cp config/config.yaml.example config/config.yaml
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 src/orchestrator.py --no-llm "triage: customer says production is down and all users are blocked"
```

## Example commands

```bash
# Rule-based triage without LLM
python3 src/orchestrator.py --no-llm "triage this Zendesk ticket: invoice charge is wrong and customer is angry"

# Check Zendesk configuration
python3 src/tools/zendesk_tool.py check

# Search Zendesk tickets
python3 src/tools/zendesk_tool.py search "type:ticket status<solved urgent"

# Draft-only internal note for Zendesk; no mutation
python3 src/tools/zendesk_tool.py note 12345 "Customer reports production outage. Routed critical to L2."

# Actually write the note after review
python3 src/tools/zendesk_tool.py note 12345 "Customer reports production outage. Routed critical to L2." --execute

# Search local knowledge base
python3 src/tools/knowledge_tool.py search "refund policy enterprise cancellation"
```

## Tool map

| Tool | File | Purpose |
|---|---|---|
| support triage | `src/tools/support_triage.py` | category/severity/sentiment/SLA/routing/draft |
| knowledge | `src/tools/knowledge_tool.py` | local Markdown KB search |
| Zendesk | `src/tools/zendesk_tool.py` | tickets, comments, replies |
| Intercom | `src/tools/intercom_tool.py` | conversations, notes, replies |
| Freshdesk | `src/tools/freshdesk_tool.py` | tickets, notes, replies |
| Salesforce Service | `src/tools/salesforce_service_tool.py` | Cases |
| HubSpot Service | `src/tools/hubspot_service_tool.py` | tickets |
| Jira Service | `src/tools/jira_service_tool.py` | requests/issues |
| Front | `src/tools/front_tool.py` | conversations |
| Help Scout | `src/tools/helpscout_tool.py` | conversations |

## Safety model

- Read/search/check actions can run directly.
- Write actions (`reply`, `note`, `comment`, `update`) return `dry_run: true` by default.
- To mutate an external system, pass `--execute` directly to the specific tool after reviewing payload.
- Never put secrets in chat or commit `.env`.

## Configuration

Use `.env.example` for required credentials and `config/config.yaml.example` for queues, SLA defaults, provider order, and integration toggles.
Runtime env names use the Warp prefix: `WARP_CONFIG` for an optional config-file override and `WARP_HTTP_TIMEOUT` for helpdesk HTTP requests. The legacy `AXSUPPORT_CONFIG` and `AXSUPPORT_HTTP_TIMEOUT` aliases remain supported for existing installs. LLM fallback order is configured with `LLM_PROVIDER_ORDER`; `LLM_PROVIDERS` remains supported as an alias.

LLM fallback supports `anthropic`, `openai`, `openrouter`, and `codex_app_server`.
OpenAI uses `OPENAI_API_KEY` with `OPENAI_MODEL` defaulting to `gpt-5.4-mini`.
OpenRouter uses `OPENROUTER_API_KEY` with `OPENROUTER_MODEL` defaulting to `deepseek/deepseek-v4-flash`.
Codex uses the official Codex app-server protocol, not an OpenAI-compatible `/v1/chat/completions` endpoint and not a `codex exec` fallback. By default Warp launches `codex app-server --listen stdio://` for each Codex provider call. `CODEX_APP_SERVER_URL` is a transport URL and defaults to `stdio://`; Warp currently supports the `stdio://` transport. Configure `CODEX_APP_SERVER_COMMAND`, `CODEX_APP_SERVER_MODEL`, `CODEX_APP_SERVER_TIMEOUT`, `CODEX_APP_SERVER_CWD`, `CODEX_APP_SERVER_SANDBOX`, and `CODEX_APP_SERVER_APPROVAL_POLICY` as needed.

## Roadmap

- OAuth flows for providers that support them.
- Incident clustering across tickets.
- CSAT/churn-risk dashboard.
- Macro performance analytics.
- Multi-brand routing rules.
- Human approval queue UI.
