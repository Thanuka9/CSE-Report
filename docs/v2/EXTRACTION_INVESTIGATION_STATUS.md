# Extraction Investigation Status

Maps `CSE_V2_FINAL_EXTRACTION_TEST_PROGRAM.md` T00–T29 against this branch.
Production extraction stays **V1**. Do not set `configs/app.yml` `extraction.engine: v2`.
Coverage floor stays `min_draft_publishable = 8924`. V1 is not source truth.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.
Recovery plan: `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`.
Verified open-work path: `docs/v2/VERIFIED_OPEN_WORK_AND_FINAL_ENGINEERING_PATH.md` (engineering head `0d844aa`+).
No-patches recovery strategy: `docs/v2/EXTRACTION_RECOVERY_STRATEGY_NO_PATCHES.md` (R0 freeze + R1 matrix started).

**Current verdict:** **READY FOR OFFICIAL DECISION — NOT YET OFFICIAL.** Hybrid 829 parity is passed, unresolved conflicts are quarantined, and remote deterministic production CI is green on Ubuntu + Windows (run #238). Production remains V1 until recorded human approval.

## T29 Resume cutover

Remote CI is **GREEN**: Deterministic production checks run #238
(`35729229940`) passed on Ubuntu and Windows at head
`282fe57af8d3d0bebbf007e06d83eb26e54c4774`.

**BLOCKED only on recorded OFFICIAL approval.** Do not set `configs/app.yml`
`engine: v2` before that approval exists. Blind source-truth evidence remains in
`tests/v2/source_truth/items.jsonl`; historical investigation artefacts remain snapshots
rather than being rewritten to match the current branch.

The task table below is retained as investigation chronology; the current release gate is
the OFFICIAL approval described above.

| Task | Status | Evidence |
|---|---|---|
| T00–T10 / T21–T23 | DONE | Prior investigation artefacts |
| T11 G02 ablation | DIAGNOSTIC | UNTESTED — `n08_gate_experiment_summary.json` |
| T12 Header H0/H1/H2 | H0 default; H1 built | H1 measured on LITE, **not promoted** — `R3_HEADER_H1.md` |
| T24 Iterate | **IN PROGRESS** | F1+F3 landed; new unseen holdout required |
| T25 HOLDOUT (first) | **FAILED then inspected** | Original 68.75%; after F1/F3 + SFCL truth fix recall 1.0 on inspected set — **not** final holdout |
| N02–N04 | DONE | `docs/v2/investigations/` |
| N05 Regressions | DONE | `test_lite_group_header_ownership.py`, `test_sfcl_company_group_ownership.py` |
| N06 F1 fix | DONE | Entity-bearing subtitle keep-rule |
| N07 Score rerun | DONE | DEV + inspected HOLDOUT recall 1.0 |
| N08 Gate experiments | DONE (diagnostic) | `tests/v2/universe/n08_gate_experiment_summary.json` — G02/G04–G08 remain UNTESTED |
| N09 Header bake-off | H0 wins | H1 built/measured, not promoted — `n09_header_bakeoff.json` |
| R3 H1 header adapter | **R3.1 DONE / NOT PROMOTED** | LITE facts 40 vs H0 72; SFCL 56=56; keep H0 — `R3_HEADER_H1.md` |
| R4 Unit U1 resolver | **BUILT / NOT PROMOTED** | Scoped V1 units on candidates; LITE facts 72=72; keep U0 — `R4_UNIT_U1.md` |
| R5 Structural differential | **MEASURED** | V1 denser tables/cells on LITE/SFCL — `R5_STRUCTURAL_DIFFERENTIAL.md` |
| R6 Concept aliases | **DEFERRED** | Wait for structure parity (R5 ports) |
| R7 Universe remeasure | **DEFERRED** | After H1/U1 promotion or material structure ports; N14 freeze remains baseline |
| N10 Unit/page/continuation | PARTIAL | Existing U0/G05 unit bakeoffs; U2/P2 not built |
| F3 duration ownership | **FIX LANDED** | Ignore `period ended` date cues as false 9M banners |
| N11 Clean-SHA baseline | **DONE** | `baseline_run_summary.json` — `actual_code_sha=2ff5d1f…`, `all_deterministic=true` |
| N12 Canonical regen | **DONE** | Freeze `ef4b200` + report `0d844aa` |
| N13 CI / PR | **DONE** | PR #35; Deterministic production checks run #238 passed on Ubuntu + Windows |
| N14 Universe challenger | **DONE (fail-closed)** | Post-F1/F3: draft-publishable **3,748** vs floor **8,924** (+64 vs prior 3,684); 43 OCR_REQUIRED_NOT_AVAILABLE — `n14_challenger_2026-09-09.json` |
| R0 Direction freeze | **DONE** | `R0_DIRECTION_FREEZE.md` + strategy copied |
| R1 V1↔V2 matrix | **LOCKED** | `V1_V2_EXTRACTION_COMPONENT_MATRIX.md` — H1 header MERGE/PORT next; reject NDB/silent-fill debt |
| R2 First-failure census | **SEED only** | locked-33 seed — `r2_seed_first_failure_locked33.json`; full-universe still open |
| N16 New holdout identity | DONE (identity only) | `holdout_v2_identity_manifest.json` — 13 filings; **do not score until N17** |
| N17 Blind gold | **PACKAGE READY / NOT ADJUDICATED** | `n17_blind_review_queue.json` + `N17_BLIND_ADJUDICATION.md` |
| T26 Frozen-universe | OPEN | Sept-10 artefacts missing |
| T27 Baseline | PARTIAL | Floor stays 8924 |
| T28 Certification | **READY FOR OFFICIAL DECISION** | Remote CI + hybrid parity gates passed |
| T29 Cutover | **BLOCKED ON OFFICIAL APPROVAL** | Production stays V1 until approval |

## Hard stops

- Do not fill `items.jsonl` from V1 or V2 outputs.
- Do not claim plan §37.
- Do not lower coverage floors / promote V2 / delete V1.
- Do not reuse failed T25 as final holdout.
- Do not score N16 until blind adjudication.
- Do not treat fail-closed as acceptance.
- Do not claim OFFICIAL approval until a human approval record exists.

## Next

Record the OFFICIAL human decision. If approved, change `configs/app.yml`
`extraction.engine: v2`, run the governed production smoke, and retain V1 as the rollback
backend during the observation period.
