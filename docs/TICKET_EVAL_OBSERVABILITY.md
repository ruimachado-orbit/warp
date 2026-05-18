# Ticket eval and observability system

This document explains the current ticket eval system end-to-end: how fixtures become labels, how rule and AI lanes are scored, where artifacts are stored, and how the dashboard reads them.

## Core models

The canonical ticket/eval data shapes live in `src/ticket_model.py`.

- `TicketInput`: normalized support ticket input. It carries `id`, `subject`, `body`, source/channel/requester/account metadata, language hints, and arbitrary `metadata`. Its `classification_text` joins subject and body for classifier-style flows.
- `ClassificationResult`: normalized classifier output. It validates the current category, severity, priority, sentiment, route, SLA, human-review flag, confidence, and tags.
- `ExpectedClassification`: fixture assertions. It supports exact expected fields, allowed category/severity sets, exact tag matching, required tag containment, and minimum confidence.
- `TicketEvalCase`: one fixture case: `case_id`, `ticket`, expected labels, optional name/description, and metadata.
- `TicketEvalResult`: one evaluated case: `case_id`, `actual`, `expected`, pass/fail, failures, generated timestamp, and evaluator metadata.

The currently valid enum values are defined in `src/ticket_model.py`:

- Categories: `billing`, `bug`, `access`, `how_to`, `feature_request`, `data_privacy`, `integration`, `general`
- Severities/priorities: `critical`, `high`, `medium`, `low`
- Sentiments: `positive`, `neutral`, `negative`

## Rule-based eval flow

The rule-based lane is implemented in `src/evals/rule.py`. It exercises the existing no-LLM orchestrator path rather than a separate classifier API.

Flow:

1. Load fixture cases from JSON or JSONL with `evals.rule.load_eval_cases()`.
2. For each `TicketEvalCase`, render the ticket into the orchestrator's plain-text goal format with `evals.rule.render_ticket_goal()`.
3. Call `orchestrator.orchestrate(goal, use_llm=False, quiet=True)`.
4. Parse the text output with `evals.rule.parse_orchestrator_classification()` into a `ClassificationResult`.
5. Score actual labels against fixture expectations with `evals.rule.score_classification()`.
6. Return aggregate totals and per-case `TicketEvalResult` dictionaries from `evals.rule.evaluate_file()`.

`render_ticket_goal()` preserves ticket ID, source, channel, subject, body, and JSON metadata in the prompt text. The parser expects the current no-LLM orchestrator summary lines:

- `Classification: <category>/<severity>/<sentiment>`
- `Route: <route>`
- `SLA: <hours>h`
- `Tags: <comma-separated tags>`
- `Human required: true|false`

If parsing fails, the result uses a low-confidence fallback classification and records a `parse_error` failure. Otherwise, scoring checks exact expected fields, allowed categories/severities, tag requirements, and minimum confidence.

For exact scalar expectations (`category`, `severity`, `priority`, `sentiment`, `language`, `route_to`, `sla_hours`, and `requires_human`), scoring also emits case-level `field_results` and aggregate run-level `field_accuracy` with `tested`, `correct`, and `accuracy` values. Allowed sets, tags, and minimum confidence still affect pass/fail but are not counted in scalar field accuracy.

## AI label eval flow

The AI labeler lane is implemented in `src/evals/ai_labeler.py`. It labels the same fixtures through the LLM gateway and then reuses `evals.rule.score_classification()` to judge the AI result against fixture labels.

Key points:

- Default provider is `openrouter` (`DEFAULT_PROVIDER = "openrouter"`).
- The prompt is built by `build_label_prompt()` and asks for one JSON object only.
- The provider call uses `llm_gateway.call_with_fallback(..., providers=[provider], temperature=0.0, json_output=True)` so the selected provider is explicit.
- OpenRouter credentials come from the normal LLM gateway environment, typically `OPENROUTER_API_KEY` and optional `OPENROUTER_MODEL`.
- Parsed output is validated through `ClassificationResult.from_dict()` and an exact `route_to` allow-list in `ROUTE_VALUES`.

`evals.ai_labeler.evaluate_file()` evaluates cases in parallel with `ThreadPoolExecutor(max_workers=5)` while preserving fixture input order in the returned `results` list.

The AI lane preserves observability data in each result's `metadata`:

- `mode: ai`
- `source: llm:<provider>`
- `provider`
- resolved `model` when the gateway returns it
- `llm_prompt`
- `llm_system`
- raw model text as `llm_raw_text`
- sanitized gateway metadata under `llm_gateway`

Secrets and sensitive gateway fields are stripped by `_gateway_observability()` / `_sanitize_gateway_value()`.

Malformed AI output is intentionally preserved. If the LLM returns malformed JSON or a structurally invalid classification, `AILabelerObservabilityError` carries the raw observability metadata. `evaluate_case()` then records an `ai_labeler_error: ...` failure, writes the fallback classification, and keeps the raw LLM text and gateway metadata in the result metadata for debugging. Provider `RuntimeError`s are recorded the same way. Unexpected implementation errors such as type errors or scoring bugs are not converted into eval failures; they propagate so the command can fail loudly.

## Rule vs AI comparison flow

`evals.ai_labeler.compare_file()` runs both lanes for the same fixture:

1. Start `evals.rule.evaluate_file(path)` for the rule/no-LLM orchestrator lane and `evals.ai_labeler.evaluate_file(path, provider=provider)` for the AI lane concurrently with `ThreadPoolExecutor(max_workers=2)`.
2. Join results by `case_id` after both lane summaries complete.
3. Emit a comparison payload with schema `warp.ticket_eval_compare.v1`.

Each comparison result contains:

- `expected`
- `rule.actual`, `rule.passed`, `rule.failures`, and `rule.field_results`
- `ai.actual`, `ai.passed`, `ai.failures`, and `ai.field_results`
- top-level `rule_passed` and `ai_passed`
- top-level `rule_field_accuracy` and `ai_field_accuracy`

When comparison payloads are written into the ticket store, `src/evals/store.py` also computes whether rule and AI actual labels agree and records the specific disagreement fields.

## Artifact storage

There are two artifact layers.

### Top-level run summaries

`evals.rule.build_eval_run_payload()` wraps eval summaries with durable run metadata:

- `schema_version: warp.ticket_eval_run.v1`
- `run_id` like `ticket-eval-<timestamp>`
- `generated_at`
- `fixture_path`
- `mode` (`rule` or `ai`)
- `source` (`no-LLM orchestrator` or `llm:<provider>`)
- aggregate pass/fail counts
- aggregate `field_accuracy` for scalar expected fields when available
- per-case `results`, including `field_results` in metadata and at result level when available

`evals.rule.write_eval_artifacts()` writes timestamped JSON and Markdown files in `eval-runs/` and updates `eval-runs/latest.json` as a convenience pointer.

Comparison summaries are written by `evals.ai_labeler.write_compare_json()` and use schema `warp.ticket_eval_compare.v1`.

### Run-scoped per-ticket artifacts

For dashboard-scale history, `src/evals/store.py` writes one JSON document per case under the run folder:

```text
eval-runs/<run_id>/tickets/<case_id>.json
```

For comparison artifacts without an explicit run ID, the run folder is derived from generated time and provider, for example `comparison-<timestamp>-openrouter`.

Each ticket artifact can include:

- fixture ticket and expected labels when fixture enrichment is available
- `evaluations`: rule or AI lane entries, de-duplicated by `(run_id, mode, source)`, preserving per-case `field_results` in metadata when available
- `comparisons`: rule-vs-AI entries, de-duplicated by `(generated_at, provider, fixture_path)`, preserving lane `field_results` when available
- `updated_at`

The whole `eval-runs/` directory is ignored by Git (`/eval-runs` in `.gitignore`), so local and CI-generated histories do not get committed by default.

## Dashboard path

The static dashboard renderer lives in `src/evals/dashboard.py` and is exposed through the packaged CLI command:

```bash
warp eval-dashboard --runs-dir eval-runs --output eval-runs/dashboard.html
```

It can also be run through the script wrapper:

```bash
python3 scripts/generate-eval-dashboard.py --runs-dir eval-runs --output eval-runs/dashboard.html
```

`load_eval_runs()` prefers run-scoped ticket artifacts in `eval-runs/<run_id>/tickets/*.json`. It still reads top-level run/comparison JSON files as a fallback and skips duplicate `latest.json` payloads when a timestamped artifact already exists. Normalized dashboard data preserves additive accuracy fields (`field_accuracy`, `rule_field_accuracy`, and `ai_field_accuracy`) for downstream inspection, without adding a large field-accuracy UI section.

The dashboard prefers run-scoped ticket artifacts because they are richer: they can include the original ticket body, expected labels, multiple evaluation lanes, comparison history, evaluator metadata, and raw AI/orchestrator output. Top-level run JSON is useful for summary history but usually lacks full ticket context.

The generated `dashboard.html` is a self-contained static HTML file, not a server. Open it directly in a browser. It shows:

- Latest run summary cards
- Run history table
- Failure counts by field/prefix
- Latest run case table, or latest comparison case table
- Clickable case modal with ticket text, expected labels, actual labels or comparison lanes, failures, evaluator output, and metadata

## CLI boundaries

Eval commands are registered in `src/evals/cli.py` via `register_eval_commands(app, console)`. The general CLI entrypoint in `src/cli.py` imports and calls that registration function, but eval command bodies stay out of the general CLI file.

Current eval commands:

- `warp eval`: rule-based fixture eval
- `warp eval-ai`: AI label fixture eval
- `warp eval-compare`: rule vs AI comparison
- `warp eval-cluster-incidents`: incident clustering fixture eval
- `warp eval-store`: convert existing run/comparison JSON into run-scoped ticket artifacts
- `warp eval-dashboard`: generate the static dashboard

## Common commands

Run the rule-based eval fixture:

```bash
warp eval tests/fixtures/ticket_eval_cases.json
```

Write top-level JSON/Markdown artifacts and run-scoped ticket artifacts:

```bash
warp eval tests/fixtures/ticket_eval_cases.json \
  --artifacts-dir eval-runs \
  --tickets-dir eval-runs
```

Run AI labels through OpenRouter:

```bash
export OPENROUTER_API_KEY="..."
warp eval-ai tests/fixtures/ticket_eval_cases.json \
  --provider openrouter \
  --artifacts-dir eval-runs \
  --tickets-dir eval-runs
```

Compare rule and AI lanes:

```bash
warp eval-compare tests/fixtures/ticket_eval_cases.json \
  --provider openrouter \
  --output eval-runs/compare-openrouter.json \
  --tickets-dir eval-runs
```

Convert old top-level run/comparison JSON artifacts into run-scoped ticket artifacts:

```bash
warp eval-store --runs-dir eval-runs --fixtures tests/fixtures/ticket_eval_cases.json --tickets-dir eval-runs
```

Regenerate the dashboard:

```bash
warp eval-dashboard --runs-dir eval-runs --output eval-runs/dashboard.html
```

Open the dashboard on macOS:

```bash
open eval-runs/dashboard.html
```

Regenerate the canonical ticket-label fixture with the LLM gateway:

```bash
python3 scripts/generate-synthetic-tickets.py \
  --kind tickets \
  --count 22 \
  --provider codex_app_server \
  --output tests/fixtures/ticket_eval_cases.json
```

Regenerate the incident clustering fixture with the LLM gateway:

```bash
python3 scripts/generate-synthetic-tickets.py \
  --kind incidents \
  --count 5 \
  --tickets-per-incident 4 \
  --singletons 5 \
  --provider codex_app_server \
  --output tests/fixtures/incident_cluster_eval_cases.json
```

## Incident clustering fixture

`tests/fixtures/incident_cluster_eval_cases.json` contains examples for incident clustering eval: five 4-ticket incidents plus five unrelated singleton tickets. Expected clusters are explicit and scored with pairwise precision/recall/F1 over ticket pairs.

See [Incident clustering eval](INCIDENT_CLUSTERING_EVAL.md) for the focused fixture, runner, output contract, scoring, and latest result notes.

Run the structured AI clusterer through OpenRouter DeepSeek V4 Flash:

```bash
warp eval-cluster-incidents tests/fixtures/incident_cluster_eval_cases.json \
  --provider openrouter \
  --model deepseek/deepseek-v4-flash \
  --output eval-runs/incident-clusters-openrouter.json
```

## Current limitations

- The dashboard is static HTML, not a live server. Regenerate it after new runs.
- `eval-runs/` is ignored by Git, so share artifacts explicitly if another environment needs them.
- AI label quality is judged against fixture labels. AI runs may fail strict fixture expectations for exact tags, exact SLA hours, routes, or severity even when the label is arguably reasonable.
- The rule parser depends on the current no-LLM orchestrator text format. If that output changes, `evals.rule.parse_orchestrator_classification()` must change with it.
