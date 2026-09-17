# Extraction Investigation Status

Maps `CSE_V2_FINAL_EXTRACTION_TEST_PROGRAM.md` T00–T29 against this branch.
Production extraction stays **V1**. Do not set `configs/app.yml` `extraction.engine: v2`.
Coverage floor stays `min_draft_publishable = 8924`. V1 is not source truth.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.
Recovery plan: `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`.
Verified open-work path: `docs/v2/VERIFIED_OPEN_WORK_AND_FINAL_ENGINEERING_PATH.md` (engineering head `0d844aa`+).
No-patches recovery strategy: `docs/v2/EXTRACTION_RECOVERY_STRATEGY_NO_PATCHES.md` (R0 freeze + R1 matrix started).

**Verdict:** Architecture improved; first T25 holdout **retired** after F1/F3 + SFCL truth fix. Not engineering-complete. Not OFFICIAL-only. **Recovery direction:** port V1 structural intelligence into V2 contracts (no issuer patches). **Next human step: N17** blind adjudication (`docs/v2/N17_BLIND_ADJUDICATION.md`).

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
| N11 Clean-SHA baseline | **DONE** | `baseline_run_summary.json` — `actual_code_sha=2ff5d1f…`, `all_deterministic=true` |
| N12 Canonical regen | **DONE** | Freeze `ef4b200` + report `0d844aa` |
| N13 CI / PR | **OPEN** | Branch pushed; `gh` not authenticated — [compare](https://github.com/Thanuka9/CSE-Report/compare/main...v2/extraction-investigation?expand=1) |
| N14 Universe challenger | **DONE (fail-closed)** | Post-F1/F3: draft-publishable **3,748** vs floor **8,924** (+64 vs prior 3,684); 43 OCR_REQUIRED_NOT_AVAILABLE — `n14_challenger_2026-09-09.json` |
| R0 Direction freeze | **DONE** | `R0_DIRECTION_FREEZE.md` + strategy copied |
| R1 V1↔V2 matrix | **DONE (draft)** | `V1_V2_EXTRACTION_COMPONENT_MATRIX.md` — header/unit PORT_V1 next |
| R2 First-failure census | **SEED only** | locked-33 seed — `r2_seed_first_failure_locked33.json`; full-universe still open |
| N16 New holdout identity | DONE (identity only) | `holdout_v2_identity_manifest.json` — 13 filings; **do not score until N17** |
| N17 Blind gold | **PACKAGE READY / NOT ADJUDICATED** | `n17_blind_review_queue.json` + `N17_BLIND_ADJUDICATION.md` |
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

R3 V1-derived H1 header transplant (bake-off vs H0) after ranking R2 families → N17 human blind-adjudicate in parallel → N18 score → N13 CI (`gh auth`) → OCR packaging for remaining 43 → OFFICIAL only after parity + holdout.
