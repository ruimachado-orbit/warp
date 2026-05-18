# PR0 Integration Baseline

PR0 integrates three preparatory workstreams into one baseline for later ticket-model PRs:

1. `fix/packaging-cli-entrypoint`
2. `fix/config-env-consistency`
3. `feat/provider-openrouter-codex-app-server`

The goal is to make Warp install and run consistently, preserve existing environment-variable compatibility, and expand LLM provider fallback without changing ticket models or helpdesk domain behavior.

## What Changed

### Packaging and CLI entrypoint

- Added `src/cli.py` as the packaged Typer CLI module.
- Kept `bin/axsupport-cli` as a compatibility wrapper for source-tree workflows.
- Declared top-level modules in `setup.py` so the console entrypoint can import them after package installation.
- Exposed the installable console script as `warp=cli:main`.

At runtime, `warp query "..."` delegates to the orchestrator, `warp status` reports LLM provider configuration, and `warp chat` runs the same interactive flow that previously lived in `bin/axsupport-cli`.

### Config and environment aliases

- Added `WARP_CONFIG` as the preferred config-file override.
- Preserved `AXSUPPORT_CONFIG` as a legacy alias.
- Added `WARP_HTTP_TIMEOUT` as the preferred helpdesk HTTP timeout variable.
- Preserved `AXSUPPORT_HTTP_TIMEOUT` as a legacy alias.
- Standardized LLM provider ordering on `LLM_PROVIDER_ORDER`.
- Preserved `LLM_PROVIDERS` as a legacy alias.

Preferred env names win over legacy aliases when both are set. Empty env values are ignored so callers can unset a preferred variable and still fall back to a legacy alias.

### LLM provider gateway additions

- Added `openrouter` support through the OpenAI-compatible chat completions client.
- Added `codex_app_server` support through the official Codex app-server JSON-RPC-like protocol, preferring `stdio://`.
- Added `codex` and `codex-app-server` aliases for `codex_app_server`.
- Added per-provider model env vars:
  - `OPENAI_MODEL`, default `gpt-5.4-mini`
  - `OPENROUTER_MODEL`, default `deepseek/deepseek-v4-flash`
  - `CODEX_APP_SERVER_MODEL`, default `gpt-5.5`
- Added OpenRouter request metadata:
  - `OPENROUTER_HTTP_REFERER`
  - `OPENROUTER_APP_TITLE`, default `Warp`
- Added Codex app-server transport settings: `CODEX_APP_SERVER_URL` defaults to `stdio://`, `CODEX_APP_SERVER_COMMAND` defaults to `codex`, and timeout/cwd/sandbox/approval-policy env vars control the `thread/start` request.
- Extended default fallback order to `anthropic`, `openai`, `openrouter`, `codex_app_server`.

## Affected Files

- `.env.example`: documents preferred env names, legacy aliases, provider order, OpenRouter, and Codex app server settings.
- `README.md`: documents runtime config/env compatibility and LLM provider behavior.
- `config/config.yaml.example`: includes `codex_app_server` in the default provider list.
- `setup.py`: packages top-level source modules and exposes `warp=cli:main`.
- `bin/axsupport-cli`: delegates to the packaged CLI while remaining executable for existing workflows.
- `src/cli.py`: hosts packaged Typer commands.
- `src/config.py`: resolves preferred env vars and legacy aliases.
- `src/llm_gateway.py`: implements OpenRouter, direct Codex app-server stdio integration, provider aliases, model env vars, and shared OpenAI-compatible calls for OpenAI/OpenRouter.
- `src/orchestrator.py`: includes `codex_app_server` in the default LLM provider fallback list.
- `src/tools/helpdesk_common.py`: resolves preferred and legacy HTTP timeout env vars.
- `tests/test_cli.py`: covers CLI commands and packaging metadata.
- `tests/test_config_env.py`: covers preferred env vars, legacy aliases, and precedence.
- `tests/test_llm_gateway.py`: covers OpenAI-compatible providers, model overrides, Codex aliases, mocked app-server stdio protocol, unsupported transport failures, provider fallback, and status output.

## Runtime Behavior

CLI execution has two supported paths:

- Installed package: `warp ...` invokes `cli:main`.
- Source tree compatibility: `bin/axsupport-cli ...` imports `src/cli.py` and invokes the same `main()`.

Configuration loading has this precedence:

- Config path: `WARP_CONFIG`, then `AXSUPPORT_CONFIG`, then `config/config.yaml`, then `config/config.yaml.example`.
- LLM provider order: `LLM_PROVIDER_ORDER`, then `LLM_PROVIDERS`, then YAML/defaults.
- Helpdesk timeout: `WARP_HTTP_TIMEOUT`, then `AXSUPPORT_HTTP_TIMEOUT`, then `30`.

LLM fallback tries providers in the configured order and returns the first successful response. Missing credentials or provider-local transport errors allow fallback to continue. For Codex, Warp launches `codex app-server --listen stdio://`, sends `initialize`, `initialized`, `thread/start`, and `turn/start`, then collects `item/agentMessage/delta` events until a terminal turn event.

## Env and Config Compatibility

PR0 keeps existing installs working while moving docs and examples to Warp-prefixed names:

| Preferred | Legacy alias | Behavior |
| --- | --- | --- |
| `WARP_CONFIG` | `AXSUPPORT_CONFIG` | Preferred path wins when both are set. |
| `WARP_HTTP_TIMEOUT` | `AXSUPPORT_HTTP_TIMEOUT` | Preferred timeout wins when both are set. Invalid integer values fall back to the default. |
| `LLM_PROVIDER_ORDER` | `LLM_PROVIDERS` | Preferred comma-separated provider order wins when both are set. |

The YAML example now includes `codex_app_server`, but env provider order can override that without editing config files.

## Tests

PR0 is covered by focused tests in:

- `tests/test_cli.py`
  - imports the packaged CLI entrypoint
  - verifies `query` delegates to the orchestrator
  - verifies `status` renders provider status
  - verifies `setup.py` declares `warp=cli:main` and packages top-level modules
- `tests/test_config_env.py`
  - verifies preferred env vars override legacy aliases
  - verifies legacy aliases still work
  - verifies provider order parsing
  - verifies helpdesk timeout alias behavior
- `tests/test_llm_gateway.py`
  - verifies OpenRouter uses the OpenAI-compatible client and headers
  - verifies OpenAI model override behavior
  - verifies Codex app-server aliases use the direct stdio provider path
  - verifies the mocked app-server protocol sequence: `initialize`, `initialized`, `thread/start`, `turn/start`, and delta collection
  - verifies app-server env overrides for command, model, cwd, sandbox, approval policy, and timeout
  - verifies unsupported transports fail provider-locally without falling back to OpenAI-compatible HTTP behavior
  - verifies status includes the integrated provider order

The existing orchestrator and support triage tests continue to guard baseline routing and classification behavior.

## Non-Goals

PR0 does not change ticket models, ticket persistence, helpdesk schemas, or downstream PR1 behavior.

PR0 does not add new helpdesk actions, change routing rules, alter support-triage classification logic, or make external writes on behalf of the user.

PR0 does not require OpenRouter credentials or a live Codex process for the unit suite. Codex runtime support expects a local Codex CLI with `app-server` support and defaults to the `stdio://` transport.
