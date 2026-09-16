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
| T24 Iterate | **REOPENED** | Unseen holdout exposed new defect families (LITE FN; SFCL truth mislabel + header evidence gap) |
| T25 HOLDOUT gold | **FAILED** | 24 items; TP 11; FN 3; critical wrong 2 vs original truth; entity-resolved recall **68.75%**; freeze `t25_failed_holdout_freeze.json` |
| N02 LITE diagnosis | DONE | First failure **entity ownership**; Group subtitle dropped from heading band — `investigations/N02_LITE_TRACE.md` |
| N03 SFCL diagnosis | DONE | V2 matched PDF Company\|Group; holdout truth mislabeled — corrected to COMPANY; `investigations/N03_SFCL_TRACE.md` |
| N04 Root-cause families | DONE | F1 header/column ownership (P0); F3 duration spans; F2 evidence propagation — `investigations/N04_ROOT_CAUSE_FAMILIES.md` |
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

Execute N00–N24 in `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`.
