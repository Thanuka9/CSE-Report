# V2 Extraction Certification Report

**Status: NOT CERTIFIED — BLOCKED ON ENGINEERING**

Production extraction remains **V1**. Coverage floor remains **8924**.
Do not set `configs/app.yml` `extraction.engine: v2`.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.
Verified engineering checkpoint: `a537f8fd83663b1d21a70b400428869256e882bf`.

Final path: `docs/v2/VERIFIED_OPEN_WORK_AND_FINAL_ENGINEERING_PATH.md`.

## Verdict

V2 is **not** certified and **not** ready for cutover. OFFICIAL is **not** the only blocker.

## First T25 holdout (retired)

```text
FAILED initially (entity-resolved recall 68.75%; 3 FN LITE; 2 critical wrong SFCL)
→ investigated (N02/N03)
→ LITE extraction defects fixed (F1 entity subtitle + F3 duration)
→ SFCL truth-label error corrected (Company values mislabeled Group)
→ rescored 1.0 on entity-resolved inspected facts (TP 16 / FN 0 / critical 0)
→ permanently retired from final holdout use
```

Do **not** present the repaired first holdout as final certification evidence.

## Final holdout path

```text
N16 identity locked (13 filings) — holdout_v2_identity_manifest.json
→ N17 blind truth pending
→ N18 scoring pending
```

## What passed (engineering / investigation)

| Gate | Result |
|---|---|
| T00–T10 investigation harness | DONE |
| T10 DEV source truth | DONE (entity-resolved recall 1.0) |
| F1 / F3 LITE fixes + regressions | DONE |
| SFCL PDF ownership + truth correction | DONE |
| G01 / G03 / G09 | KEEP |
| N08 gate diagnostics | DONE (G02/G04–G08 still UNTESTED) |
| N09 header diagnostic | H0 MEASURED only (H1/H2 not built) |
| Checklist 18 OCR packaging | DONE |
| Checklist 20 V2 publish path | DONE (opt-in `engine=v2`) |
| Engine default | V1 |

## Still open before certification

| Gate | Result |
|---|---|
| N17 / N18 new unseen holdout | PENDING / BLOCKED ON N17 |
| N11 clean-SHA locked-33 baseline | OPEN |
| N12 canonical artefact regen | OPEN |
| N13 CI green | OPEN |
| N14 current-universe V2 challenger | OPEN (prior 3,684 vs 8,924 predates F1/F3) |
| G02 / G04–G08 | UNTESTED vs source truth |
| H1 / H2 | not built |
| N20 Sept-10 exact replay | OPEN (artefacts missing) |
| T28 / T29 | BLOCKED ON ENGINEERING (+ OFFICIAL later) |

## Hard stops

- Do not promote V2 / lower 8924 / delete V1.
- Do not score N16 before blind truth.
- Do not reuse first T25 as final holdout.
- Do not claim OFFICIAL-only / H2 complete / G02–G08 decided.
- Do not treat Sept-05 diagnostic as Sept-10 acceptance.

## Artefacts

- `docs/v2/VERIFIED_OPEN_WORK_AND_FINAL_ENGINEERING_PATH.md`
- `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`
- `docs/v2/EXTRACTION_INVESTIGATION_STATUS.md`
- `tests/v2/source_truth/holdout_v2_identity_manifest.json`
- `tests/v2/universe/t25_failed_holdout_freeze.json`
- `tests/v2/universe/n08_gate_experiment_summary.json`
- `tests/v2/universe/n09_header_bakeoff.json`
