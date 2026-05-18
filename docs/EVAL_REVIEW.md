# Eval System Review

**Date:** 2026-05-18
**Scope:** `src/evals/`, `src/ticket_model.py`, `tests/test_ticket_eval.py`, `tests/test_ai_ticket_labeler.py`

## Strengths

- Shared `score_classification()` between rule and AI lanes — good separation of concerns
- Clean data models with validation in `ticket_model.py`
- Observability with secret stripping on the AI path — well thought out
- Schema versioning on all artifact types
- Fixture enrichment at storage time (not eval time)
- Self-contained static dashboard with no server dependency
- Tests cover happy path, error paths, and observability preservation

---

## Changes To Make

### 1. Narrow the blanket `except Exception` in `ai_labeler.py`

**Problem:** `ai_labeler.py:229` catches all exceptions and silently records them as `ai_labeler_error`. The `AILabelerObservabilityError` catch above it (line 219) correctly handles known LLM parse/validation failures. But the second catch turns TypeErrors, AttributeErrors, and any bug in our own scoring logic into a quiet eval failure. You'd never notice your code has a bug because it would just look like the LLM failed.

**What to change:** Narrow `except Exception` to `except RuntimeError`. That's the type `_label_ticket_with_observability` explicitly raises when the gateway returns `ok: False`. Any other exception type is a real bug and should propagate.

**File:** `src/evals/ai_labeler.py`, line 229

**Before:**
```python
except Exception as exc:
    return TicketEvalResult(
        case_id=case.case_id,
        actual=_fallback_classification(),
        ...
    )
```

**After:**
```python
except RuntimeError as exc:
    return TicketEvalResult(
        case_id=case.case_id,
        actual=_fallback_classification(),
        ...
    )
```

**Why this is safe:** The only non-`AILabelerObservabilityError` exception that `_label_ticket_with_observability` raises is a `RuntimeError` when the gateway returns `ok: False`. Everything else (JSON parse errors, invalid labels) is already wrapped in `AILabelerObservabilityError`. If something unexpected happens, we *want* it to crash loudly.

---

### 2. Consolidate duplicated code

**Problem:** Three things are defined in multiple places:

| What | Copies | Where |
|------|--------|-------|
| `utc_now_iso()` | 3 | `ticket_model.py:24`, `rule.py:239`, `store.py:19` |
| `_fallback_classification()` | 2 | `rule.py:145`, `ai_labeler.py:194` |
| `_safe_filename()` / `_safe_path_component()` | 2 | `rule.py:247`, `store.py:23` |

This also fixes issue #3 (private member access) — `ai_labeler.py:321` calls `rule._utc_now_iso()`, reaching into a private function.

**What to change:**

**a) `utc_now_iso`** — already public in `ticket_model.py`. Delete the private copies in `rule.py` and `store.py`. Update all call sites:
- `rule.py`: replace `_utc_now_iso()` calls with `from ticket_model import utc_now_iso`
- `store.py`: replace local `utc_now_iso()` with import from `ticket_model`
- `ai_labeler.py:321`: replace `rule._utc_now_iso()` with `utc_now_iso()` (imported from `ticket_model`)

**b) `_fallback_classification`** — move to `ticket_model.py` as a public function `fallback_classification()`. It returns a `ClassificationResult`, so it belongs next to that class. Delete the copies in `rule.py` and `ai_labeler.py`, import from `ticket_model` instead.

**c) `_safe_filename`** — `rule.py` has `_safe_filename()`, `store.py` has `_safe_path_component()`. They do the same regex sanitization with different fallback strings. Keep `_safe_path_component(value, fallback)` in `store.py` as the canonical version (it already takes a fallback param). In `rule.py`, import and call `store._safe_path_component(value, "ticket-eval-run")` — or better, since `rule.py` only uses it in `write_eval_artifacts`, just import `safe_run_dirname` from store.

Actually, `rule.py` uses `_safe_filename` to build artifact filenames from run_id, which isn't the same as a "run dirname." Simplest fix: move `_safe_filename` out of `rule.py` into `store.py` as a public `safe_filename()`, and have `rule.py` import it. Then `store.py`'s `_safe_path_component` can call `safe_filename` internally too.

**Why:** Less drift risk. When someone changes the fallback classification in one place and forgets the other, the two lanes silently diverge.

---

### 3. Add per-field accuracy to eval summaries

**Problem:** `score_classification()` returns binary pass/fail. The aggregate `pass_rate` from `evaluate_file()` is too coarse to answer:
- "Does the AI get category right 95% of the time but route wrong 30%?"
- "Is one field dragging down the overall pass rate?"
- "Which fields does rule beat AI on, and vice versa?"

A case fails if *any* field is wrong, so a 50% pass rate could mean "every case has one wrong field" or "half the cases are completely wrong." You can't tell.

**What to change:**

**a) Extend `score_classification()` return value** — instead of just `(passed, failures)`, also return a dict of per-field results:

```python
def score_classification(actual, expected) -> tuple[bool, list[str], dict[str, bool]]:
    failures = []
    field_results = {}
    
    for field_name in ("category", "severity", "priority", "sentiment",
                       "language", "route_to", "sla_hours", "requires_human"):
        expected_value = getattr(expected, field_name)
        if expected_value is not None:
            actual_value = getattr(actual, field_name)
            match = actual_value == expected_value
            field_results[field_name] = match
            if not match:
                failures.append(f"{field_name} expected {expected_value} got {actual_value}")
    
    # ... rest of checks (allowed_categories, tags, confidence)
    
    return not failures, failures, field_results
```

**b) Aggregate per-field accuracy in `evaluate_file()`** — after collecting all results, compute:

```python
field_accuracy = {}
for field in ("category", "severity", "priority", "sentiment",
              "language", "route_to", "sla_hours", "requires_human"):
    tested = [r for r in field_results_list if field in r]
    if tested:
        correct = sum(1 for r in tested if r[field])
        field_accuracy[field] = {"tested": len(tested), "correct": correct,
                                 "accuracy": correct / len(tested)}
```

Add `"field_accuracy": field_accuracy` to the summary dict returned by both `rule.evaluate_file()` and `ai_labeler.evaluate_file()`.

**c) Surface in `compare_file()`** — include `rule_field_accuracy` and `ai_field_accuracy` in the comparison payload so the dashboard can show a side-by-side per-field comparison.

**Why this matters:** This is the single highest-value change. The whole point of having two eval lanes is to compare them — and right now the only comparison metric is overall pass/fail rate. Per-field accuracy turns the eval from "did it work?" into "where specifically does each approach succeed and fail?"

**Backward compatibility:** Not a concern — nothing external consumes `score_classification()`. Change the return type and update the ~4 call sites (`rule.evaluate_case`, `ai_labeler.evaluate_case`, and tests).

---

### 4. Parallelize AI eval execution

**Problem:** Both `evaluate_file()` functions use sequential list comprehensions:
```python
results = [evaluate_case(case, provider=provider) for case in cases]
```
Each AI case makes a serial LLM call. With 20+ fixtures, this is unnecessarily slow.

**What to change:**

**a) `ai_labeler.evaluate_file()`** — use `concurrent.futures.ThreadPoolExecutor`:

```python
from concurrent.futures import ThreadPoolExecutor

def evaluate_file(path, provider=DEFAULT_PROVIDER):
    cases = rule.load_eval_cases(path)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda c: evaluate_case(c, provider=provider), cases))
    # ... rest unchanged
```

`pool.map` preserves input order, so the return shape is identical. Each `evaluate_case` already handles its own errors internally (returns a TicketEvalResult with failures, never raises), so one failing case doesn't poison the batch.

**b) `compare_file()`** — run rule and AI evals in parallel since they're independent:

```python
with ThreadPoolExecutor(max_workers=2) as pool:
    rule_future = pool.submit(rule.evaluate_file, path)
    ai_future = pool.submit(evaluate_file, path, provider)
    rule_summary = rule_future.result()
    ai_summary = ai_future.result()
```

**c) Leave `rule.evaluate_file()` sequential** — it spawns subprocesses internally, and the orchestrator isn't designed for concurrent calls. Parallelizing it could cause subprocess contention. Not worth the risk for the rule path which is already fast.

**Why:** Purely a UX/speed improvement. Doesn't change any behavior or output format. The monkeypatched tests will still work because `monkeypatch` replaces the attribute on the module object, which is shared across threads.

**Max workers = 5:** Reasonable default. Rate limits aren't a concern. No backwards-compat wrapper needed.

---

## Issues Noted But Not Acting On Now

### 5. Rule eval tests orchestration plumbing, not classification rules

`rule.evaluate_case()` calls `orchestrator.orchestrate(use_llm=False)`, which spawns `support_triage.py` as a subprocess through the full pipeline. If the subprocess times out or tool selection changes, the eval breaks even though classification rules are fine. Ideally the classifier would be callable directly. Not blocking — just means the rule eval is more of an integration test than a unit eval.

### 6. Fixture edge-case diversity

~20 synthetic tickets exist but are generated, not curated. Should add 10-15 hand-written edge cases covering: ambiguous tickets, non-English, empty body, conflicting signals, `allowed_categories`/`allowed_severities` as primary assertions.

### 7. No latency/cost in aggregate summaries

Metadata captures `usage.total_tokens` and `_execution_time` but nothing aggregates them. Adding `total_tokens` and `mean_latency_ms` to the summary would be trivial and valuable.

### 8. Language detection in rule path

`rule.py:81` only supports `pt`/`en` and relies on triage tool putting BCP-47 codes in tags.

### 9. `compare_file()` doesn't surface agreement metrics

The store computes `_classification_disagreements()` and `agreement`, but `compare_file()` doesn't include per-field agreement rates in its summary.

### 10. Dashboard is a monolith

`dashboard.py` mixes data normalization with HTML rendering. Separating them would make it testable and maintainable, but it works as-is.
