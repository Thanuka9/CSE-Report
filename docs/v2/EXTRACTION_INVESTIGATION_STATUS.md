# Extraction Investigation Status

Maps `CSE_V2_FINAL_EXTRACTION_TEST_PROGRAM.md` T00–T29 against this branch.
Production extraction stays **V1**. Do not set `configs/app.yml` `extraction.engine: v2`.
Coverage floor stays `min_draft_publishable = 8924`. V1 is not source truth.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.

| Task | Status | Evidence |
|---|---|---|
| T00 Freeze | DONE | `tests/v2/universe/investigation_freeze.json` |
| T01 Source Metric Truth Contract | DONE | `docs/v2/SOURCE_METRIC_TRUTH_CONTRACT.md`. OPEN: PAT vs attributable; TOTAL_EQUITY vs owners; cents/share `0.01`; document-level entity (G01). |
| T02 Neutral schema | DONE | `src/cse_financial_etl/v2/contracts/investigation.py` |
| T03 DEV/HOLDOUT split | DONE | DEV 22 / HOLDOUT 11. `items.jsonl` empty. |
| T04 CandidateTrace | DONE | Rejected candidates retained. |
| T05–T09 Locked-33 baseline | DONE | 33/33 deterministic. 905 SourceFacts. V1 comparator-only. |
| T10 Blind adjudication | QUEUE ONLY | `tests/v2/source_truth/t10_review_queue.json` (40 DEV pointers, no comparator values). **Human blocked.** Not gold. |
| T11 G02 ablation | DIAGNOSTIC | Cascade 766 = per_column 766. Decision **UNTESTED**. |
| T12 Header H0/H1/H2 | H0 ONLY | Locked-33 H0: 635/891 entity, 715 period, 494 duration, 585 comparison, 873 unit columns resolved. H1 not ported. **H2 not built.** |
| T13 Unit U0/U1/U2 | U0 ONLY | Locked-33: 18 unit-unresolved columns, 0 cents evidence, 0 USD columns. U0 parses USD as USD with no FX. cents/share scale **OPEN**. **U2 not built.** |
| T14 Page router P0/P1/P2 | P1 OPT-IN | Production P0. P1 census: 7 mixed filings, 9 empty pages. No Tesseract. **P2 not built.** |
| T15 Continuation | DIAGNOSTIC | Locked-33: 0 explicit continuation regions. Schema-evidence continuation not enabled. **UNTESTED.** |
| T16 Whole-PDF discovery | DIAGNOSTIC | 32 exact hits, 9 other-page. Does not publish. |
| T17 Table reconstruction | DIAGNOSTIC | Layout tests in `test_reconstruction_layouts.py`. Cell `SourceRef` is the numeric token. |
| T18 Concept semantics | DIAGNOSTIC | PAT/PBT/Revenue positives; EBITDA, attributable, closing price, bank Interest income negatives. |
| T19 Issuer/regime audit | DIAGNOSTIC | `audit_issuer_regime`. Name heuristics are not final truth. |
| T20 Defect ranking | DONE | `tests/v2/universe/defect_family_ranking.json`. Not source-confirmed. |
| T21 Generalized fix | PARTIAL | Cell-level `SourceRef` cleared value-reproducible failures. Narrative fuzzy TOP_LINE on highlights/SOFP is now abstained (SEYB). Remaining 16 `CONTEXT_EVIDENCE_INCOMPLETE` are GREG FLOW rows headed `Period ended` with no month count. Duration is not invented. |
| T22–T24 Iterate | BLOCKED | Needs T10 source-confirmed families. |
| T25 HOLDOUT gold | BLOCKED | Do not inspect holdout to tune rules. |
| T26 Frozen-universe A/B | BLOCKED | September-10 artefacts not in-repo. |
| T27 SOURCE_VALIDATED_BASELINE | BLOCKED | |
| T28 Certification | BLOCKED | |
| T29 Resume cutover | BLOCKED | Cutover checklist items 12, 13, 15, 18–20 plus OFFICIAL review. |

## Hard stops

- Do not fill `items.jsonl` from V1 or V2 outputs.
- Do not claim plan §37.
- Do not lower coverage floors.
- Do not enable P1 as production without Tesseract proof.
- Do not choose H2/U2/P2; they are not built.
- G09 currently infers COMPANY on EPS_NOTE when the blob has no Group. That is **not** source-confirmed KEEP.

## Cutover document

`docs/v2/CUTOVER_CHECKLIST.md` still blocks V2 default. The Downloads cutover-tasks file is not in this workspace; the in-repo checklist is the authority for production promotion.
