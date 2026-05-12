     1|# Warp
     2|
     3|Autonomous customer support operations agent built in the Axeng style. It connects to common helpdesk/CRM systems, classifies tickets, routes work, drafts replies, searches knowledge, and keeps support operations disciplined.
     4|
     5|## What it does
     6|
     7|- Triage: category, severity, sentiment, priority, SLA, tags, queue.
     8|- Classification: billing, bug, access, how-to, feature request, privacy, integration, general.
     9|- Routing: L1, L2 technical support, billing, privacy/legal, product feedback, integrations.
    10|- Drafting: safe customer replies and internal notes.
    11|- Knowledge: local Markdown KB search for macros, policy, troubleshooting.
    12|- Helpdesk operations: search/read/update patterns for major support systems.
    13|- Safe execution: external mutations default to dry-run unless called with `--execute`.
    14|
    15|## Supported systems
    16|
    17|Primary systems:
    18|
    19|- Zendesk Support
    20|- Intercom
    21|- Freshdesk
    22|- Salesforce Service Cloud
    23|- HubSpot Service Hub
    24|- Jira Service Management
    25|- Front
    26|- Help Scout
    27|
    28|Collaboration / knowledge:
    29|
    30|- Slack
    31|- Notion
    32|- Local Markdown KB under `knowledge/`
    33|
    34|## Quick start
    35|
    36|```bash
    37|cd /Users/axevoid/Code/axsupport
    38|cp .env.example .env
    39|cp config/config.yaml.example config/config.yaml
    40|python3 -m venv .venv
    41|source .venv/bin/activate
    42|pip install -r requirements.txt
    43|python3 src/orchestrator.py --no-llm "triage: customer says production is down and all users are blocked"
    44|```
    45|
    46|## Example commands
    47|
    48|```bash
    49|# Rule-based triage without LLM
    50|python3 src/orchestrator.py --no-llm "triage this Zendesk ticket: invoice charge is wrong and customer is angry"
    51|
    52|# Check Zendesk configuration
    53|python3 src/tools/zendesk_tool.py check
    54|
    55|# Search Zendesk tickets
    56|python3 src/tools/zendesk_tool.py search "type:ticket status<solved urgent"
    57|
    58|# Draft-only internal note for Zendesk; no mutation
    59|python3 src/tools/zendesk_tool.py note 12345 "Customer reports production outage. Routed critical to L2."
    60|
    61|# Actually write the note after review
    62|python3 src/tools/zendesk_tool.py note 12345 "Customer reports production outage. Routed critical to L2." --execute
    63|
    64|# Search local knowledge base
    65|python3 src/tools/knowledge_tool.py search "refund policy enterprise cancellation"
    66|```
    67|
    68|## Tool map
    69|
    70|| Tool | File | Purpose |
    71||---|---|---|
    72|| support triage | `src/tools/support_triage.py` | category/severity/sentiment/SLA/routing/draft |
    73|| knowledge | `src/tools/knowledge_tool.py` | local Markdown KB search |
    74|| Zendesk | `src/tools/zendesk_tool.py` | tickets, comments, replies |
    75|| Intercom | `src/tools/intercom_tool.py` | conversations, notes, replies |
    76|| Freshdesk | `src/tools/freshdesk_tool.py` | tickets, notes, replies |
    77|| Salesforce Service | `src/tools/salesforce_service_tool.py` | Cases |
    78|| HubSpot Service | `src/tools/hubspot_service_tool.py` | tickets |
    79|| Jira Service | `src/tools/jira_service_tool.py` | requests/issues |
    80|| Front | `src/tools/front_tool.py` | conversations |
    81|| Help Scout | `src/tools/helpscout_tool.py` | conversations |
    82|
    83|## Safety model
    84|
    85|- Read/search/check actions can run directly.
    86|- Write actions (`reply`, `note`, `comment`, `update`) return `dry_run: true` by default.
    87|- To mutate an external system, pass `--execute` directly to the specific tool after reviewing payload.
    88|- Never put secrets in chat or commit `.env`.
    89|
    90|## Configuration
    91|
    92|Use `.env.example` for required credentials and `config/config.yaml.example` for queues, SLA defaults, provider order, and integration toggles.
    93|
    94|## Roadmap
    95|
    96|- OAuth flows for providers that support them.
    97|- Incident clustering across tickets.
    98|- CSAT/churn-risk dashboard.
    99|- Macro performance analytics.
   100|- Multi-brand routing rules.
   101|- Human approval queue UI.
   102|