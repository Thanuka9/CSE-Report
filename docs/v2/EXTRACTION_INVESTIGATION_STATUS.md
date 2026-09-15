# Extraction Investigation Status

Maps `CSE_V2_FINAL_EXTRACTION_TEST_PROGRAM.md` T00–T29 against this branch.
Production extraction stays **V1**. Do not set `configs/app.yml` `extraction.engine: v2`.
Coverage floor stays `min_draft_publishable = 8924`. V1 is not source truth.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.

| Task | Status | Evidence |
|---|---|---|
| T00 Freeze | DONE | `tests/v2/universe/investigation_freeze.json` records `investigation_base_sha` and `actual_code_sha`. |
| T01 Source Metric Truth Contract | DONE | PAT = total period profit, not attributable. TOTAL_EQUITY = inclusive total, not owners. BANK TOP_LINE = Gross income. cents/share scale `0.01`. G01 KEEP: do not copy issuer-name entity. |
| T02 Neutral schema | DONE | `src/cse_financial_etl/v2/contracts/investigation.py` |
| T03 DEV/HOLDOUT split | DONE | Locked 33 = DEV/regression. New unseen 12-filing HOLDOUT in `holdout_manifest.json`. Do not inspect holdout. |
| T04 CandidateTrace | DONE | Exact in-run candidates. Production selection recorded separately from publication. |
| T05–T09 Locked-33 baseline | DONE | 33/33 deterministic on fresh read/parse A/B. 1642 SourceFacts (all proven entities). V1 comparator-only. Production selection is separate. |
| T10 Blind adjudication | DONE | `tests/v2/source_truth/items.jsonl` — 40 DEV SourceTruthItems from PDF-page review. Reviewer `t10-blind-pdf-review`. Not gold. Holdout untouched. |
| T11 G02 ablation | DIAGNOSTIC | Cascade equals per-column on locked 33. Decision **UNTESTED** (T10 did not adjudicate cascade). |
| T12 Header H0/H1/H2 | H0 ONLY | Locked-33 H0: 635/891 entity, 715 period, 494 duration, 715 comparison, 873 unit columns resolved. H1 not ported. **H2 not built.** |
| T13 Unit U0/U1/U2 | U0 ONLY | cents/share scale locked at `0.01`. **U2 not built.** |
| T14 Page router P0/P1/P2 | P1 OPT-IN | Production P0. P1 census: 7 mixed filings, 9 empty pages. No Tesseract. **P2 not built.** |
| T15 Continuation | DIAGNOSTIC | Locked-33: 0 explicit continuation regions. Schema-evidence continuation not enabled. **UNTESTED.** |
| T16 Whole-PDF discovery | DIAGNOSTIC | 32 exact hits, 9 other-page. Does not publish. |
| T17 Table reconstruction | DIAGNOSTIC | Layout tests in `test_reconstruction_layouts.py`. Cell `SourceRef` is the numeric token. |
| T18 Concept semantics | DIAGNOSTIC | PAT/PBT/Revenue positives; EBITDA, attributable, closing price, bank Interest income negatives. T10 confirms PAT ≠ attributable and BANK TOP_LINE = Gross income. |
| T19 Issuer/regime audit | DIAGNOSTIC | `audit_issuer_regime`. Name heuristics are not final truth. |
| T20 Defect ranking | DONE | `tests/v2/universe/defect_family_ranking.json`. V1 disagreements are not source-confirmed. T10 families are in `t10_score.json`. |
| T21 Generalized fix | PARTIAL | Cell-level `SourceRef`. G01 issuer-name entity removed. G09 EPS_NOTE Company inference removed. Remaining `CONTEXT_EVIDENCE_INCOMPLETE` FLOW rows headed `Period ended` still do not invent duration. |
| T22–T24 Iterate | PARTIAL | T10 scored in `tests/v2/universe/t10_score.json`. G01/G03/G09 KEEP. G02/G04–G08 UNTESTED. No holdout inspection. |
| T25 HOLDOUT gold | BLOCKED | New unseen holdout. Do not inspect holdout to tune rules. |
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
- Do not inspect HOLDOUT PDFs.

## T10 record

40 DEV VALUE_DISAGREEMENT pointers were reviewed from raw PDF page text.
`items.jsonl` is Reviewer 1 complete. 39 REPORTED, 1 AMBIGUOUS (ABL TOP_LINE: no
Gross income line). Entity-unlabelled REPORTED rows stay `entity_scope` null.
GREG duration stays null. PAT is the total period line, not attributable.
TOTAL_EQUITY is the inclusive total, not owners.

## Pre-T10 infrastructure

Source extraction no longer filters by expected production entity. Production
selection is measured separately. CandidateTrace uses the exact pipeline
candidates. Full read/parse A/B is required for the locked baseline. Canonical
freeze, baseline, experiments, and ranking share one `actual_code_sha`.

Investigation ruff, mypy, and `tests/v2` are green. Canonical artefacts share
`actual_code_sha`. CandidateTrace records `candidate_id` and SourceFact linkage.
Run-level canonical parquet/jsonl files are assembled after the locked A/B.
Full `pytest` still has 8 V1 universe failure-pack failures
that call `extract_filing` and are unchanged versus `e92689d`. Those PDFs are
gitignored, so GitHub CI skips that file.

## Cutover document

`docs/v2/CUTOVER_CHECKLIST.md` still blocks V2 default. The Downloads cutover-tasks file is not in this workspace; the in-repo checklist is the authority for production promotion.
