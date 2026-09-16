# V2 Extraction Certification Report

**Status: NOT CERTIFIED**

Production extraction remains **V1**. Coverage floor remains **8924**.
Do not set `configs/app.yml` `extraction.engine: v2`.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.

## What passed

| Gate | Result |
|---|---|
| T00–T10 investigation harness | DONE |
| T10 DEV source truth (40 items) | DONE |
| T21/T22 insurance GWP TOP_LINE alias + regression | DONE |
| T25 HOLDOUT gold sample (24 items) | DONE (evaluation only; no retune) |
| G01 / G03 / G09 | KEEP |
| Locked-33 A/B determinism | DONE (prior baseline) |
| Engine default | V1 |

## Scoring snapshot

### DEV (T10)

- 40 items; 31 TP; 0 value mismatches; 8 G01 withheld; entity-resolved recall **1.0**

### HOLDOUT (T25)

- 24 items; 11 TP; 2 entity mismatches (SFCL); 3 FN (LITE); 4 G01 withheld
- Entity-resolved recall **0.6875** (diagnostic only)
- **No rule changes** from these holdout misses

### Still blocked for certification

- September-10 frozen-universe A/B missing
- G02/G04–G08 UNTESTED
- Coverage floor redesign / OCR packaging / OFFICIAL review

## Hard stops still in force

- Do not promote V2.
- Do not lower `min_draft_publishable`.
- Do not delete V1.
- Do not retune rules from holdout misses without a new locked holdout.

## Artefacts

- `docs/v2/SOURCE_VALIDATED_BASELINE.md`
- `docs/v2/EXTRACTION_GATE_DECISIONS.md`
- `docs/v2/EXTRACTION_INVESTIGATION_STATUS.md`
- `tests/v2/source_truth/items.jsonl`
- `tests/v2/universe/t10_score.json`
- `tests/v2/universe/t25_holdout_score.json`
