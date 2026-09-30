# Same-input three-way measurement result

**Run ID:** `same_input_2026-09-09`  
**Cohort:** 829 CSE download-named PDFs (exact historic E13 `selected_filing_count`)  
**Engines:** V1-only · V2-only · V1-assisted V2 (`v1_source_observations=True`)  
**Filings attempted / errors:** 829 / 0  
**Python:** CPython 3.12 (project `requires-python >=3.12`)

## Reconcile: 812 freeze vs 829 E13

| Set | Count | Rule |
|---|---:|---|
| Prior `input_manifest.json` freeze | 812 | sha16-named local copies only (`period_filingId_<16hex>`) |
| Historic E13 selection | 829 | CSE download-named files (`period_filingId_<timestamp…>`) |
| Pinned cohort (this run) | **829** | All local CSE download-named PDFs in target periods, SHA256-hashed |

- 17 issuer-period keys exist only as download-named files (no sha16 twin).
- 799 SHA overlap freeze↔E13; 13 same-key byte mismatches.
- Artifacts: `reconcile_812_vs_829.json`, `pinned_cohort.json`.

## KPI table (TARGET metrics only)

| KPI | V1-only | V2-only | V1-assisted V2 |
|---|---:|---:|---:|
| Target fact rows / eligible SourceFacts | 8,290 | 9,838 | 9,838 |
| Identical fact keys vs V2 | — | 1,824 | 1,824 |
| V1-only keys vs V2 | 6,466 | — | — |
| Newly recovered keys by adapter vs V2 | — | — | **0** |
| Net eligible delta (assisted − V2) | — | — | **0** |
| Withheld SourceFacts (non-ELIGIBLE) | — | 24,976 | 24,976 |
| V1 discovery-union candidates | — | 0 | 298,541 |
| Discovery-only pending V2 verify | — | 0 | 298,541 |

### Verdict

**Recovery is not demonstrated.** The scaffold unions 298,541 V1 physical observations as `DISCOVERY_ONLY` / `CONTEXT_UNRESOLVED_PENDING_V2_VERIFY`, but **zero** of those become additional ELIGIBLE SourceFacts. Draft-publishable eligible count is identical for V2-only and V1-assisted V2 (9,838).

V2 already emits more TARGET ELIGIBLE rows than this V1 comparator (9,838 vs 8,290), largely via GROUP/CONSOLIDATED scopes V1 does not emit the same way — but **6,466 V1 keys remain unmatched** under the identity used here (symbol, metric, entity, period, duration, comparison, value). Those V1-only keys are **engine-differential observations**, not yet independently PDF-adjudicated as source-valid.

Dominant V2 candidate blockers (summed across filings): CONCEPT_UNRESOLVED 282,780 · ENTITY_NOT_RESOLVED 82,350 · PERIOD_NOT_RESOLVED 26,863.

## Artifacts

- `reconcile_812_vs_829.json`
- `pinned_cohort.json`
- `three_way_measure_summary.json`
- `gap_summary.json`
- `ledger_v1.csv` / `ledger_v2.csv` / `ledger_v1_assisted_v2.csv`
- `three_way_measure_run.log`

## Reproduce

```text
py -3.12 -u scripts/v2_same_input_three_way_measure.py --reuse-cohort --workers 6
```
