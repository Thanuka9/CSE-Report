# Adapter admission investigation

**Run context:** `same_input_2026-09-09` three-way measure  
**Scope:** why 298,541 V1 observations stayed `DISCOVERY_ONLY`; what the 6,466 V1-only keys are; bridge 9,838 ELIGIBLE ↔ 3,854 draft-publishable; one PDF-verified proof trace.  
**Not in scope:** extraction patches, full-universe remeasure, unlabeled-entity invent.

---

## 1. Why all 298,541 V1 observations remained DISCOVERY_ONLY

### Feature flag does reach the resolver

In `run_filing_pipeline`, when `v1_source_observations=True`:

1. `collect_v1_source_observations(pdf)` runs  
2. `observations_to_discovery_candidates` maps them to `FactCandidate`  
3. `union_candidates(v2_candidates, v1_candidates)` merges them  
4. **`resolve_source_facts(candidates, …)` receives the union**

Assisted pipeline counters confirm this: 634,390 candidates vs 336,037 V2-only; **298,541** carry `V1_OBSERVATION_UNION`. The flag is not a dead switch.

### Categorical exclusion is by design — stamped at birth

Every observation is stamped before any V2 verification:

```text
V1_PHYSICAL_OBSERVATION
CONTEXT_UNRESOLVED_PENDING_V2_VERIFY
DISCOVERY_ONLY
publishable=False
entity_scope=None  period_end=None  duration=None  unit=None
```

(`v1_source_observations.py` lines 54–58; `observation_union.py` re-appends `DISCOVERY_ONLY`.)

`DISCOVERY_ONLY` is **not** a separate branch inside `source_admission_failure`. The resolver never special-cases the string. Rejection is ordinary missing-context admission.

### Exact rejection boundary (`source_admission_failure`)

Order of gates (resolver):

| Stage | Failure enum | Adapter behavior today |
|---|---|---|
| Numeric | `NUMERIC_UNPARSED` | Usually passes (cell parsed) |
| Concept | `CONCEPT_UNRESOLVED` | **Dominant** — statement hint often `None` → matcher uses `OTHER_FINANCIAL_STATEMENT` → abstain (e.g. “Turnover” only matches on `INCOME_STATEMENT`) |
| Entity | `ENTITY_UNRESOLVED` | **Always** — observations never fill entity |
| Period | `PERIOD_UNRESOLVED` | **Always** — never filled |
| Unit | `UNIT_UNRESOLVED` | **Always** — never filled |
| → SourceFact | — | never reached for V1-union ids |
| → ELIGIBLE | duration/comparison rules | N/A |
| → production selected | `select_pipeline_facts` | N/A |
| → draft-publishable | release / EXTRACTED* | N/A |

**There is no “V2 context verification” step that promotes DISCOVERY_ONLY → admissible.** The architecture diagram’s “verify then admit” stage is unimplemented. Union only adds unresolved candidates; they die at concept/entity/period/unit gates.

### Single-PDF waterfall (ABANS ELECTRICALS PLC, 2025-12-31)

| Boundary | Count / result |
|---|---|
| Observations collected | 398, all `discovery_only`, 0 entity/period/unit filled |
| Discovery candidates | 398 (15 concept-resolved if hint luck; here mostly not) |
| Admission on V1-only candidates | CONCEPT_UNRESOLVED 383, ENTITY_UNRESOLVED 15, **admit 0** |
| Assisted pipeline V1-union cands | 275 → CONCEPT 272 / ENTITY 3 / **admit 0** |
| SourceFacts with `v1obs-` ids | **0** |
| ELIGIBLE / production selected | **0 / 0** |

---

## 2. Decisive proof: one PDF-verified V1-only correct fact

**Fact:** ABANS ELECTRICALS PLC · `TOP_LINE` · 2025-12-31 · raw `1,928,502,029` (Turnover).

| Check | Result |
|---|---|
| PDF | Page 2: label “Turnover”, value `1,928,502,029` (verified) |
| V1 extract | Emits COMPANY / CURRENT / raw_text `1928502029` |
| V2 native candidate | Same bbox/value; concept `TOP_LINE`; period `2025-12-31`; duration **9**; **ENTITY_NOT_RESOLVED** → no SourceFact |
| Adapter candidate | Same page/bbox/value; **concept None** (hint `None` → OTHER abstain); entity/period/unit None; stamped DISCOVERY_ONLY → `CONCEPT_UNRESOLVED` at admission |
| Can V2 admit without weakening validation? | **Not with today’s adapter.** Admission requires resolved concept + entity + period + unit from **source evidence**. Adapter supplies none of the context dimensions. Inventing COMPANY (as V1 does) would weaken the fail-closed contract. |

Same issuer has **zero** V2 ELIGIBLE rows in the 829 ledger for any period — native path also stuck on entity. The cell is recoverable in principle only after a real context-verify step (bind columns / reanchor headers), not by union alone.

Also: even if entity were resolved, native duration **9** would be withheld as non-exact-quarter / cumulative under current FLOW rules — a separate selection issue from adapter admission.

---

## 3. What are the 6,466 V1-only keys?

### Identity is not fully comparable as measured

The three-way ledger key was:

`(symbol, metric, entity, period, duration, comparison, normalized_value)`

Problems:

1. **V1 `normalized_value` empty on 5,114 / 8,290 rows** — measure used `normalized_value or value`, not `raw_value` / `raw_text`. Values often live in `raw_text` only → empty-value keys inflate “V1-only”.
2. **V1 `duration_months` empty on 5,277 rows**; V2 uses `3` or empty for stocks.
3. **V1 `comparison_role` is `UNKNOWN` on 3,487 rows**; V2 uses `CURRENT` / `COMPARATIVE`.
4. V2 ELIGIBLE includes **GROUP/CONSOLIDATED** scopes V1 largely does not emit the same way.

### Recomputed families (using `raw_text` fallback; metric+entity+period+value)

| Family | Count (approx.) | Meaning |
|---|---:|---|
| `NO_V2_METRIC_PERIOD` | 3,600 | No V2 ELIGIBLE for that symbol+metric+period at all |
| `V1_EMPTY_VALUE` | 1,768 | Still no usable V1 value (often EPS_DILUTED / nulls) |
| `VALUE_OR_SCALE_DIFF` | 673 | Same entity+metric+period, different number |
| `ENTITY_DIFF` | 186 | V2 has other entity scopes only |

**Do not call all 6,466 lost correct facts.** A large share are identity/measurement artifacts or V1 rows without a V2 ELIGIBLE peer because V2 produced **no** SourceFact for that filing (entity unresolved), not because the adapter “almost” published them.

Stratified sample file: `v1_only_sample_for_pdf_verify.json`  
PDF-verified examples in `NO_V2`: ABANS TOP_LINE / OP / PBT / PAT / EPS for 2026-06-30 — numbers present on PDF page 2; V2 ELIGIBLE count for ABAN = 0.

---

## 4. Accounting: 9,838 ELIGIBLE ≠ 3,854 draft-publishable

| Measure | What it counts |
|---|---|
| **9,838** | TARGET-metric `SourceFact` with `publication_status=ELIGIBLE` on the 829 cohort — **all** entities, durations, comparisons; **no** production query selection; **no** derived metrics |
| **3,854** | E13 `draft_publishable_count` — production pipeline statuses `EXTRACTED` + `EXTRACTED_DERIVED` after entity/period/duration selection, unique snapshot metrics, **includes derived** (ROE, NPM, EPS_SELECTED, …) |

### Bridge (production selection on the 9,838)

`select_pipeline_facts` keeps ELIGIBLE ∩ CURRENT ∩ (duration null or 3) ∩ expected entity, then unique-by-metric.

Simulated on TARGET ledger:

| Step | Rows |
|---|---:|
| All TARGET ELIGIBLE | 9,838 |
| CURRENT | 6,820 |
| + COMPANY or BANK entity | 3,445 |
| Unique-by-metric per filing (COMPANY/BANK preferred) | **~2,834** on **521** filings |

~2,834 source TARGET selected ≪ 3,854 because E13 also counts **derived** metrics and a broader metric set. Conversely 9,838 ≫ 3,854 because ELIGIBLE still includes GROUP/CONSOLIDATED, comparative columns, and non-selected duplicates.

**Do not attribute the 8,924−3,854 floor gap to “adapter didn’t fire.”** Most of the ELIGIBLE→draft drop is **selection/publication policy**, and the three-way “eligible” metric was never the E13 draft definition.

---

## 5. Implications (no code change claimed)

1. **Adapter admission is categorically blocked today** — stamped `DISCOVERY_ONLY` with empty context; no verify-and-promote path exists. Flag reaches resolver; resolver correctly refuses.
2. **Next engineering step is not another universe rerun** — implement V2 context verification that binds entity/period/unit (and statement type for concept) from PDF evidence onto anchored observations, then re-measure admission→ELIGIBLE→selected on a small proof set.
3. **Re-key the V1/V2 gap** with `raw_value`/`raw_text`, stock duration null, and explicit UNKNOWN≠CURRENT handling before citing 6,466 as recoverable volume.
4. **Report draft-publishable with the production selection bridge**, not raw ELIGIBLE counts.

### Artifacts

- This file  
- `v1_only_sample_for_pdf_verify.json`  
- Existing ledgers / `gap_summary.json` / `MEASUREMENT_RESULT.md`
