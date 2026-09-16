# V2 Extraction Certification Report

**Status: NOT CERTIFIED — BLOCKED ON ENGINEERING**

Production extraction remains **V1**. Coverage floor remains **8924**.
Do not set `configs/app.yml` `extraction.engine: v2`.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.
Audited head at recovery plan: `99e658c`.

## Verdict

First unseen holdout (**T25**) **FAILED**. Critical wrong facts are present.
This branch is **not** engineering-complete and **not** blocked on OFFICIAL review only.

## What passed (engineering / investigation)

| Gate | Result |
|---|---|
| T00–T10 investigation harness | DONE |
| T10 DEV source truth (40 items) | DONE (entity-resolved recall 1.0 after GWP fix) |
| T21/T22 insurance GWP TOP_LINE alias + regression | DONE |
| G01 / G03 / G09 | KEEP |
| Locked-33 A/B determinism | DONE (prior baseline) |
| Checklist 18 OCR packaging | DONE (Dockerfile + container smoke) |
| Checklist 20 V2 publish path | DONE (opt-in `engine=v2`; default V1) |
| Engine default | V1 |

## What failed or remains open

| Gate | Result |
|---|---|
| T24 iterate | **REOPENED** — holdout exposed new defect families |
| T25 HOLDOUT | **FAILED** — recall 68.75%; 3 FN (LITE); 2 critical wrong (SFCL) |
| T26 frozen-universe | OPEN — Sept-10 artefacts missing; Sept-05 diagnostic ≠ acceptance |
| Checklist 12 institutional gold | OPEN — investigation gold ≠ §37 |
| Checklist 13 frozen-universe acceptance | OPEN — not passed |
| Checklist 15 current-universe | FAIL signal — 3,684 vs floor 8,924 (fail-closed ≠ pass) |
| G02 / G04–G08 | UNTESTED |
| T28 certification | **BLOCKED ON ENGINEERING** |
| T29 cutover | **BLOCKED ON ENGINEERING + OFFICIAL** |

## Scoring snapshot

### DEV (T10)

- 40 items; 31 TP; 0 value mismatches; 8 G01 withheld; entity-resolved recall **1.0**

### HOLDOUT (T25) — FAILED

- 24 items; 11 TP; 2 entity/value mismatches (SFCL); 3 FN (LITE); 4 G01 withheld (HNBF/NAMU)
- Entity-resolved recall **0.6875**
- Critical wrong facts **2**
- Failed holdout is now engineering evidence; do not reuse as final holdout

## Hard stops still in force

- Do not promote V2.
- Do not lower `min_draft_publishable`.
- Do not delete V1.
- Do not treat fail-closed as a passing acceptance test.
- Do not claim OFFICIAL-only stage.

## Artefacts

- `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`
- `docs/v2/SOURCE_VALIDATED_BASELINE.md`
- `docs/v2/EXTRACTION_GATE_DECISIONS.md`
- `docs/v2/EXTRACTION_INVESTIGATION_STATUS.md`
- `docs/v2/CUTOVER_CHECKLIST.md`
- `tests/v2/source_truth/items.jsonl`
- `tests/v2/universe/t10_score.json`
- `tests/v2/universe/t25_holdout_score.json`
- `tests/v2/universe/t25_failed_holdout_freeze.json`
- `tests/v2/universe/t26_frozen_universe_diagnostic.json`
