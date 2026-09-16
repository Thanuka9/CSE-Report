# Extraction Investigation Status

Maps `CSE_V2_FINAL_EXTRACTION_TEST_PROGRAM.md` T00–T29 against this branch.
Production extraction stays **V1**. Do not set `configs/app.yml` `extraction.engine: v2`.
Coverage floor stays `min_draft_publishable = 8924`. V1 is not source truth.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.

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
| T12 Header H0/H1/H2 | H0 ONLY | H2 not built |
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
| T24 Iterate | DONE | Major T10 cluster closed; G02/G04–G08 remain UNTESTED |
| T25 HOLDOUT gold | DONE | 24 HOLDOUT items; score in `t25_holdout_score.json`; **no retune from holdout** |
| T26 Frozen-universe A/B | ENGINEERING CLOSED (FAIL-CLOSED) | Sept-10 artefacts missing; Sept-05 pin diagnostic `t26_frozen_universe_diagnostic.json` |
| T27 SOURCE_VALIDATED_BASELINE | PARTIAL | `docs/v2/SOURCE_VALIDATED_BASELINE.md` from T10+T25 only; floor stays 8924 |
| T28 Certification | NOT CERTIFIED | Awaiting **OFFICIAL** review |
| T29 Resume cutover | BLOCKED ON OFFICIAL ONLY | All engineering checklist items closed (incl. fail-closed 13/15); human OFFICIAL remains |

## Hard stops

- Do not fill `items.jsonl` from V1 or V2 outputs.
- Do not claim plan §37.
- Do not lower coverage floors.
- Do not enable P1 as production without Tesseract proof (Docker OCR smoke closes packaging).
- Do not choose H2/U2/P2; they are not built.
- Do not retune rules from HOLDOUT misses.

## Cutover document

`docs/v2/CUTOVER_CHECKLIST.md` — engineering complete; **sole remaining gate is OFFICIAL human review**.
