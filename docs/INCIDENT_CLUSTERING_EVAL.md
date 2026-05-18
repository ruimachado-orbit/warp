# Incident clustering eval

The incident clustering eval measures whether Warp can group related support tickets into incidents. It is a grouping eval, not strict label classification: the important question is whether tickets that belong together are clustered together and unrelated tickets stay separate.

## Fixture

Fixture path: `tests/fixtures/incident_cluster_eval_cases.json`

- Schema: `warp.incident_cluster_eval.v1`
- 25 tickets total
- Five 4-ticket incidents plus five unrelated singleton tickets
- 10 expected clusters total

The fixture includes timestamps and expected clustering hints, but the model input includes only these customer-visible ticket fields:

- `ticket_id`
- `subject`
- `body`
- `channel`

The model must not see `created_at`, `expected_incident_id`, `expected_clusters`, or fixture `signals`.

## Prompt sent to the model

The clusterer uses a role split:

- `SYSTEM_PROMPT` contains the full clustering contract: role/task, grouping rules, exact JSON output shape, validation rules, `PROMPT_VERSION`, `OUTPUT_SCHEMA_VERSION`, and the valid-JSON-only instruction.
- The user prompt is built by `build_cluster_prompt(tickets)` and contains only the ticket payload:
  - `Input ticket IDs: [...]`
  - `Tickets:` followed by pretty-printed visible ticket JSON.

The tickets JSON is derived from `_ticket_for_prompt()` and includes only `ticket_id`, `subject`, `body`, and `channel`. It excludes `created_at`, `expected_incident_id`, `expected_clusters`, and fixture `signals`. `build_cluster_prompt()` deterministically shuffles the visible tickets using the sorted ticket IDs as a seed, so the prompt is reproducible without preserving fixture order.

## Small prompt example

This example is shortened to three visible tickets rather than the full 25-ticket fixture. The task instructions, schema, and rules are sent separately in `SYSTEM_PROMPT`; the user prompt only contains this payload:

```text
Input ticket IDs: ["IC-GH-001", "IC-GH-002", "IC-SINGLE-001"]

Tickets:
[
  {
    "ticket_id": "IC-GH-001",
    "subject": "GitHub OAuth keeps sending me back to login",
    "body": "When I click Connect GitHub from Warp Drive, the GitHub authorization page appears, I approve it, and then Warp drops me back on the same login screen. I have tried Chrome and Safari.",
    "channel": "email"
  },
  {
    "ticket_id": "IC-GH-002",
    "subject": "Cannot finish GitHub integration setup",
    "body": "Our team is trying to enable the GitHub integration. After approving the OAuth app, the callback returns to Warp but the integration still says not connected.",
    "channel": "email"
  },
  {
    "ticket_id": "IC-SINGLE-001",
    "subject": "Need VAT added to March invoice",
    "body": "Please reissue our March invoice with our company VAT number and billing address. This is only for our finance records.",
    "channel": "email"
  }
]
```

## Expected response example

For the three-ticket example above, a valid response would include one incident cluster and one singleton cluster:

```json
{
  "schema_version": "warp.incident_clusterer.output.v1",
  "prompt_version": "warp.incident_clusterer.prompt.v1.<content_hash>",
  "clusters": [
    {
      "incident_id": "github_oauth_redirect_loop",
      "kind": "incident",
      "summary": "GitHub OAuth authorization completes but returns users to the start or leaves the integration disconnected.",
      "ticket_ids": ["IC-GH-001", "IC-GH-002"],
      "confidence": 0.91,
      "signals": ["github integration", "oauth authorization", "callback or redirect loop"]
    },
    {
      "incident_id": "invoice_vat_reissue_request",
      "kind": "singleton",
      "summary": "A customer needs a March invoice reissued with VAT and billing details.",
      "ticket_ids": ["IC-SINGLE-001"],
      "confidence": 0.82,
      "signals": ["invoice", "VAT", "billing address", "standalone finance request"]
    }
  ]
}
```

If someone needs the user prompt for a run, reproduce it in Python with `build_cluster_prompt(load_incident_fixture(path)["tickets"])`; pair it with `SYSTEM_PROMPT` for the full model request.

## Runner

Run the current OpenRouter DeepSeek V4 Flash eval with:

```bash
warp eval-cluster-incidents tests/fixtures/incident_cluster_eval_cases.json \
  --provider openrouter \
  --model deepseek/deepseek-v4-flash \
  --output eval-runs/incident-clusters-openrouter.json
```

Do not commit `eval-runs/` artifacts by default; that directory is ignored by Git.

## Implementation

- Clusterer: `src/evals/incident_clusterer.py`
- CLI registration: `src/evals/cli.py`
- Model call: `llm_gateway` with an explicit model override from `--model`

Versioned contracts:

- Prompt: `warp.incident_clusterer.prompt.v1.<content_hash>` where `<content_hash>` is an 8-character SHA-256 prefix derived from the system prompt template.
- Model output schema: `warp.incident_clusterer.output.v1`
- Eval result schema: `warp.incident_cluster_eval_result.v1`

## Model output contract

Every input ticket must be assigned exactly once to a cluster. Each cluster contains:

- `incident_id`
- `kind`: `incident` or `singleton`
- `summary`
- `ticket_ids`
- `confidence`
- `signals`

## Scoring

Scoring is pairwise over ticket pairs:

- Precision penalizes false merges: unrelated tickets predicted in the same cluster.
- Recall penalizes false splits: related tickets predicted in different clusters.
- F1 combines precision and recall.
- Singletons have no positive expected pairs, but false merges involving singletons create false positives.

## Latest DeepSeek V4 Flash result

Latest OpenRouter DeepSeek V4 Flash run:

- Tickets: 25
- Expected clusters: 10
- Predicted clusters: 11
- True positives: 26
- False positives: 0
- False negatives: 4
- Precision: 1.0
- Recall: 0.8666666667
- F1: 0.9285714286

Succeeded:

- Perfectly clustered GitHub OAuth callback loop tickets.
- Perfectly clustered Warp Drive sync failure tickets.
- Perfectly clustered Okta SSO/SCIM provisioning tickets.
- Perfectly clustered Warp client crash-on-launch tickets.
- Kept all five singleton tickets separate.
- Did not merge unrelated tickets.

Failed:

- Split expected `slack_webhook_delivery_delays` into two plausible subclusters:
  - Delay tickets: `IC-SLACK-001`, `IC-SLACK-003`
  - Duplication tickets: `IC-SLACK-002`, `IC-SLACK-004`
- False-negative pairs: `IC-SLACK-001/002`, `IC-SLACK-001/004`, `IC-SLACK-002/003`, `IC-SLACK-003/004`

Interpretation: this is partly a grouping-rubric boundary issue, not only a model failure. Tickets from the same integration and timeframe but with different symptoms may need an explicit policy defining whether to group them into one incident or split them by symptom.

## Recommended next steps

- Define the incident grouping policy.
- Add that policy to the clustering prompt and fixture expectations.
- Optionally track split and merge counts in eval output.
- Optionally add incident clustering metrics to dashboard evals.
