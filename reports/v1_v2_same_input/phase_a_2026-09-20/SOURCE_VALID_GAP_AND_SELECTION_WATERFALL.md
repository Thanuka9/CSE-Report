# Source-valid gap and selection waterfall (Phase A)

**Plan:** `docs/v2/CSE_V2_FINAL_AGENT_EXECUTION_PLAN.md`  
**Baseline freeze:** `reports/v1_v2_same_input/baseline_freeze_2026-09-20_plus3/`  
**Cohort:** pinned 829 (`same_input_2026-09-09`)  
**Status:** quant + probe complete; PDF adjudication of review queue still **PENDING** (engine keys ≠ source truth).

## Frozen baseline KPIs (do not rewrite)

| | V2-only | Assisted | Net |
|---|---:|---:|---:|
| TARGET draft-selected | 2,816 | 2,819 | **+3** |
| E13 total draft-publishable (reference) | 3,854 | — | not same definition |
| Governance floor | — | 8,924 | separate gate |

## Selection funnel (TARGET rows on ledgers)

### V2-only
{
  "target_rows": 34594,
  "eligible_rows": 9850,
  "eligible_current": 6847,
  "eligible_current_quarterish": 6847,
  "approx_selected_target": 2861,
  "ledger_draft_selected_true": 2816
}

### Assisted
{
  "target_rows": 33566,
  "eligible_rows": 9466,
  "eligible_current": 6516,
  "eligible_current_quarterish": 6516,
  "approx_selected_target": 2865,
  "ledger_draft_selected_true": 2819
}

~9.8k ELIGIBLE rows collapse to ~2.8k selected primarily via CURRENT + duration∈{null,3} + expected-entity unique-by-metric — **selection policy**, not solely extraction failure.

## Soft-key differential (metric/entity/period/dur/cmp; value compared when both present)

| Class | Count |
|---|---:|
| V1 soft slots with no V2 ELIGIBLE peer | **6096** |
| Soft slots both present, shared value | 1899 |
| Soft slots both present, conflicting values | 295 |
| Assisted newly selected hard keys vs V2 | 106 |
| Assisted lost selected hard keys vs V2 | 103 |

## V1-only first-loss probe (n=24, live pipeline)

### V2-only
{
  "ENTITY_UNRESOLVED": 8,
  "MISSING_CELL_OR_VALUE": 6,
  "CONCEPT_UNRESOLVED": 5,
  "WITHHELD_CONFLICTING_SOURCE": 2,
  "ADMISSION_OK_BUT_NO_SOURCEFACT": 2,
  "OBSERVED_BUT_NOT_IN_PIPELINE_CANDIDATES": 1
}

### Assisted
{
  "ENTITY_UNRESOLVED": 9,
  "MISSING_CELL_OR_VALUE": 6,
  "CONCEPT_UNRESOLVED": 4,
  "ADMISSION_OK_BUT_NO_SOURCEFACT": 2,
  "SELECTED_OK": 1,
  "WITHHELD_CONFLICTING_SOURCE": 1,
  "OBSERVED_BUT_NOT_IN_PIPELINE_CANDIDATES": 1
}

## Decision gate

Probe first-loss (n=24) is dominated by **ENTITY_UNRESOLVED**, **MISSING_CELL_OR_VALUE**, and **CONCEPT_UNRESOLVED** — prioritize physical reader / header context (entity→period) over selection-bridge patches. Conflict/not-selected is secondary in this sample.

**Follow-on implemented in-session:** unanimous same-table entity/period fill when headers already print one consistent value (`ENTITY_FROM_TABLE_HEADER_UNANIMOUS` / `PERIOD_FROM_TABLE_HEADER_UNANIMOUS`). Never invent issuer COMPANY/BANK. 15-filing admission sample: admitted 308→400; ENTITY misses 71→46; PERIOD misses 151→63.

Do not treat all 6096 V1-only soft slots as correct recoverable facts until `source_review_queue.json` is PDF-adjudicated.

## Artifacts

- `phase_a_summary.json`
- `source_review_queue.json` (adjudication_status=PENDING_PDF_REVIEW)
- `v1_only_first_loss_probes.json`
- Baseline checksums: `../baseline_freeze_2026-09-20_plus3/BASELINE_FREEZE_MANIFEST.json`

## Production

V1 remains default. Not READY FOR OFFICIAL DECISION.
