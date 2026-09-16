# Extraction Investigation Status

Maps `CSE_V2_FINAL_EXTRACTION_TEST_PROGRAM.md` T00–T29 against this branch.
Production extraction stays **V1**. Do not set `configs/app.yml` `extraction.engine: v2`.
Coverage floor stays `min_draft_publishable = 8924`. V1 is not source truth.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.
Recovery plan: `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`.

**Verdict:** Architecture improved; first unseen holdout **FAILED** then repaired on inspected set. Not engineering-complete. Not OFFICIAL-only. New holdout (N16) pending blind gold (N17).

| Task | Status | Evidence |
|---|---|---|
| T00–T10 / T21–T23 | DONE | Prior investigation artefacts |
| T11 G02 ablation | DIAGNOSTIC | UNTESTED — `n08_gate_experiment_summary.json` |
| T12 Header H0/H1/H2 | H0 MEASURED | H1/H2 not built — `n09_header_bakeoff.json` |
| T24 Iterate | **IN PROGRESS** | F1+F3 landed; new unseen holdout required |
| T25 HOLDOUT (first) | **FAILED then inspected** | Original 68.75%; after F1/F3 + SFCL truth fix recall 1.0 on inspected set — **not** final holdout |
| N02–N04 | DONE | `docs/v2/investigations/` |
| N05 Regressions | DONE | `test_lite_group_header_ownership.py`, `test_sfcl_company_group_ownership.py` |
| N06 F1 fix | DONE | Entity-bearing subtitle keep-rule |
| N07 Score rerun | DONE | DEV + inspected HOLDOUT recall 1.0 |
| N08 Gate experiments | DONE (diagnostic) | `tests/v2/universe/n08_gate_experiment_summary.json` — G02/G04–G08 remain UNTESTED |
| N09 Header bake-off | DONE (H0 only) | `tests/v2/universe/n09_header_bakeoff.json` — H1/H2 not built |
| N10 Unit/page/continuation | PARTIAL | Existing U0/G05 unit bakeoffs; U2/P2 not built |
| F3 duration ownership | **FIX LANDED** | Ignore `period ended` date cues as false 9M banners |
| N16 New holdout identity | DONE (identity only) | `holdout_v2_identity_manifest.json` — 13 filings; **do not score until N17** |
| N17 Blind gold | **NOT STARTED** | |
| T26 Frozen-universe | OPEN | Sept-10 artefacts missing |
| T27 Baseline | PARTIAL | Floor stays 8924 |
| T28 Certification | **BLOCKED ON ENGINEERING** | |
| T29 Cutover | **BLOCKED ON ENGINEERING + OFFICIAL** | |

## Hard stops

- Do not fill `items.jsonl` from V1 or V2 outputs.
- Do not claim plan §37.
- Do not lower coverage floors / promote V2 / delete V1.
- Do not reuse failed T25 as final holdout.
- Do not score N16 until blind adjudication.
- Do not treat fail-closed as acceptance.
- Do not claim OFFICIAL-only.

## Next

N17 blind-adjudicate `holdout_v2_identity_manifest.json` → N18 score → N11–N14 clean baseline/CI/universe as capacity allows → N20 Sept-10 when artefacts exist → N23 OFFICIAL.
