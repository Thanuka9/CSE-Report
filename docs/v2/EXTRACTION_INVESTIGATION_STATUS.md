# Extraction Investigation Status

Maps `CSE_V2_FINAL_EXTRACTION_TEST_PROGRAM.md` T00–T29 against this branch.
Production extraction stays **V1**. Do not set `configs/app.yml` `extraction.engine: v2`.
Coverage floor stays `min_draft_publishable = 8924`. V1 is not source truth.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.
Recovery plan: `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md` (audited head `99e658c`).

**Verdict:** Architecture improved; first unseen holdout **FAILED**. Not engineering-complete. Not OFFICIAL-only.

| Task | Status | Evidence |
|---|---|---|
| T00 Freeze | DONE | `tests/v2/universe/investigation_freeze.json` |
| T01 Source Metric Truth Contract | DONE | PAT ≠ attributable; TOTAL_EQUITY inclusive; BANK TOP_LINE = Gross income; GWP contribution aliases; cents/share `0.01` |
| T02 Neutral schema | DONE | `v2/contracts/investigation.py` |
| T03 DEV/HOLDOUT split | DONE | Locked 33 DEV; 12-filing HOLDOUT identity manifest |
| T04 CandidateTrace | DONE | Exact in-run candidates; production selection separate |
| T05–T09 Locked-33 baseline | DONE | 33/33 deterministic; SourceFacts proven-entity only |
| T10 Blind adjudication | DONE | 40 DEV items in `items.jsonl` |
| T11 G02 ablation | DIAGNOSTIC | Cascade = per_column; decision UNTESTED |
| T12 Header H0/H1/H2 | H0 ONLY | H2 not built; SFCL reopen (N03/N09) |
| T13 Unit U0/U1/U2 | U0 ONLY | U2 not built |
| T14 Page router P0/P1/P2 | P1 OPT-IN | P2 not built; OCR packaging proven via Docker smoke |
| T15 Continuation | DIAGNOSTIC | UNTESTED |
| T16 Whole-PDF discovery | DIAGNOSTIC | Does not publish |
| T17 Table reconstruction | DIAGNOSTIC | Cell SourceRef numeric token |
| T18 Concept semantics | DIAGNOSTIC | + GWP contribution TOP_LINE |
| T19 Issuer/regime audit | DIAGNOSTIC | Name heuristics not final truth |
| T20 Defect ranking | DONE | `defect_family_ranking.json` |
| T21 Generalized fix | DONE | G01 issuer-name; G09 EPS inference; insurance GWP contribution alias |
| T22 Permanent regression | DONE | `tests/v2/regression/test_insurance_gwp_top_line.py` |
| T23 Rerun DEV scoring | DONE | `t10_score.json` — entity-resolved recall 1.0 after GWP fix |
| T24 Iterate | **REOPENED / IN PROGRESS** | F1 fix landed; F3 duration ownership still open; new unseen holdout still required |
| T25 HOLDOUT gold | **FAILED (first unseen); inspected set re-scored** | Original fail 68.75%; after F1 + SFCL truth fix N07 TP 16 / FN 0 / critical 0 / recall 1.0 on **inspected** set — **not** final holdout |
| N02 LITE diagnosis | DONE | First failure was entity ownership — `investigations/N02_LITE_TRACE.md` |
| N03 SFCL diagnosis | DONE | Truth mislabel corrected; V2 matched PDF — `investigations/N03_SFCL_TRACE.md` |
| N04 Root-cause families | DONE | F1 fixed; F3 open — `investigations/N04_ROOT_CAUSE_FAMILIES.md` |
| N05 Regressions | DONE | `tests/v2/regression/test_lite_group_header_ownership.py`, `test_sfcl_company_group_ownership.py` |
| N06 F1 fix | DONE | `column_context._is_entity_bearing_subtitle` keeps Group/Company subtitles |
| N07 Score rerun | DONE | `t10_score.json` / `t25_holdout_score.json` — DEV+inspected HOLDOUT recall 1.0 |
| T26 Frozen-universe A/B | **OPEN (artefact-blocked)** | Sept-10 artefacts missing; Sept-05 pin is diagnostic only — **not** acceptance |
| T27 SOURCE_VALIDATED_BASELINE | PARTIAL / PROVISIONAL | T10 + inspected T25; floor stays 8924 |
| T28 Certification | **BLOCKED ON ENGINEERING** | Need new unseen holdout + F3 + gates + universe |
| T29 Resume cutover | **BLOCKED ON ENGINEERING + OFFICIAL** | Not OFFICIAL-only |
| N05 LITE/SFCL regressions | DONE | Permanent real-PDF regressions: `tests/v2/regression/test_lite_group_header_ownership.py`, `test_sfcl_company_group_ownership.py` |
| N06 F1 generalized fix | DONE | `v2/resolution/column_context.py` — entity-bearing statement subtitles kept in heading-band context (not dropped as `_ACCOUNT_LINE` + year) |
| N07 DEV scoring rerun | **IN PROGRESS** | Post-F1 `t10_score.json` / source-truth scoring rerun pending or in progress; not a certification pass |
| N06 follow-on (F3) | **OPEN** | LITE duration ownership / merged quarter–YTD spans still unfixed after F1 |
| T26 Frozen-universe A/B | **OPEN (artefact-blocked)** | Sept-10 artefacts missing; Sept-05 pin is diagnostic only — **not** acceptance |
| T27 SOURCE_VALIDATED_BASELINE | PARTIAL / PROVISIONAL | T10 + failed T25 only; floor stays 8924 |
| T28 Certification | **BLOCKED ON ENGINEERING** | Holdout failed; gates unresolved; NOT CERTIFIED |
| T29 Resume cutover | **BLOCKED ON ENGINEERING + OFFICIAL** | Not OFFICIAL-only |

## Hard stops

- Do not fill `items.jsonl` from V1 or V2 outputs.
- Do not claim plan §37.
- Do not lower coverage floors.
- Do not promote V2 or delete V1.
- Do not reuse the failed T25 12-file set as the final holdout.
- Do not treat fail-closed diagnostics as acceptance passes.
- Do not claim OFFICIAL review is the only remaining blocker.
- Do not patch LITE/SFCL with issuer-specific constants.

## Next

Finish N07 post-F1 DEV scoring; then N08–N10 (gates, header bake-off). F3 duration span ownership for LITE remains open. Execute remaining N00–N24 in `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`.
