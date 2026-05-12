# Axsupport

Autonomous customer support operations agent for triage, classification, routing, drafting, knowledge lookup, SLA management, and helpdesk automation.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)

**Autonomous AI agent built with the Axeng architecture.**

> Self-hosted, open source, no cloud dependencies. Runs on any machine.

---

## ⚡ Quick Start

### Prerequisites

- Python 3.12+
- 3 LLM provider API key(s): anthropic, openai, openrouter

### Install

```bash
# Clone
git clone <your-repo-url>
cd axsupport

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

cp config/config.yaml.example config/config.yaml
# Edit config/config.yaml
```


### Run

```bash
# Interactive chat
python3 bin/axsupport-cli chat

# Query
python3 src/orchestrator.py "your query here"

# Status check
python3 bin/axsupport-cli status
```


---

## 🎯 Features


### Intelligent Orchestration
- Natural language query routing
- Automatic tool selection
- Multi-provider LLM synthesis with fallback
- Context-aware responses


### Integrations

- **Slack** — Ready to use
- **Notion** — Ready to use

### LLM Providers

- **Anthropic Claude** — Automatic fallback
- **OpenAI** — Automatic fallback
- **OpenRouter** — Automatic fallback

---

## 📋 Configuration

### Environment Variables

```bash
# .env

SLACK_BOT_TOKEN=your_key_here
SLACK_APP_TOKEN=your_key_here
NOTION_TOKEN=your_key_here
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
OPENROUTER_API_KEY=your_key_here
```

### Config File

```yaml
# config/config.yaml




llm:
  providers: ['anthropic', 'openai', 'openrouter']
  default: anthropic
  max_tokens: 4096
  temperature: 0.7
```

---

## 🏗️ Architecture

```
axsupport/
├── src/
│   ├── orchestrator.py         # NL query router + tool executor
│   ├── llm_gateway.py          # Multi-provider LLM client
│   ├── config.py               # Unified config loader
│   └── tools/                  # Integration tools

│       ├── slack_tool.py
│       ├── notion_tool.py

├── skills/                     # Claude Code skills
│   └── example-skill/
│       └── SKILL.md


├── bin/
│   └── axsupport-cli    # CLI interface

└── config/
    ├── config.yaml             # Agent configuration
    └── tools.yaml              # Tool registry
```

---

## 🤝 Contributing

```bash
git checkout -b feat/your-feature
# Make changes
git commit -m "feat: your feature"
git push origin feat/your-feature
# Open PR
```

---

## 📄 License

MIT © 2026

---

## 🙏 Credits

Built with:
- [Axeng](https://github.com/ruimachado-orbit/axeng) — Agent architecture
- [Claude Code](https://claude.ai/code) — AI development
- [Agent Factory](https://github.com/maio-labs/sapiens) — Project scaffolding