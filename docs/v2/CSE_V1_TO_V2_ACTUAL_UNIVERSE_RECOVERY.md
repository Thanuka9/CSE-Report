# CSE V2 — Actual Universe Recovery Mandate

**Goal: recover V1-scale correct extraction inside V2, without V1's unsafe assumptions.**  
**Repository:** `Thanuka9/CSE-Report` · **Branch examined:** `v2/extraction-investigation` · **Head examined:** `1cfb6d550959812aa2a3233fee8b3c5d3f1bb317`  
**Production:** V1 remains default · **Historical draft-publishable floor:** 8,924, unchanged.  
**Status:** implementation mandate — it is **not** a claim the integrated recovery path has already been built.

## 1. Stop optimizing the wrong metric

The engineering goal is **not** another 4–20 true positives on the former N18 13-filing regression. It is to recover the large number of *correct, source-supported, target-eligible* financial facts V1 can discover but V2 currently loses, and to demonstrate that recovery on a fixed full-universe PDF cohort. A conservative extractor with near-zero critical errors but less than half the historic publication volume is not a completed V2.

Historical evidence: E13 summary at `d29b392…` says **3,854 draft-publishable**, **829 selected PDFs**, **820 extracted**, **9 pipeline errors**, against historical floor **8,924**. The underlying E13 `run_manifest_2026-09-09.json` nevertheless says `working_tree_dirty: true` / `d29b392-dirty` while the folder calls the run clean. Resolve this inconsistency before calling a run reproducible. That result combines source and derived/publication outcomes: do not equate 3,854 with 3,854 distinct PDF source facts. The latest user-reported former-N18 regression is **53 TP / 62 FN / 0 critical wrong**; it is safety/regression evidence, **not** proof of full-universe coverage. Preserve the frozen original N17 gold and first N18 score.

The 8,924 floor is a historical governance threshold, **not** independent proof that V1 has 8,924 correct source facts on today's exact PDFs. The first job is to establish a genuinely comparable V1/V2 run, not use that caveat to excuse under-recovery or lower the floor.

## 2. Re-establish one apples-to-apples baseline FIRST

Freeze the **same 829 selected filing identities**, exact PDF SHA256s/revisions, target periods, issuer/security master, price snapshot, metric definitions, entity query, release policy and code/dependency versions. Run V1 and V2 on those same bytes. If the historic V1 run cannot be reconstructed, record that limitation and create a *new governed V1 comparator* on the frozen PDFs. Do not label that new comparator the old historical 8,924 result.

Build one **target-fact ledger**, not candidate-count charts. Fact identity must retain filing/PDF SHA, issuer/security, metric and actual source concept, source entity, period, FLOW duration (null for STOCK), current/comparative role, currency/unit, raw value, and query/publication scope. Keep alternative observations and disagreements; do not collapse GROUP→COMPANY, current→comparative, 3M→YTD, or duplicate values across different sources.

The comparison must separate:

| Category | Evidence required |
|---|---|
| BOTH_SAME | Both engines recover same source fact |
| BOTH_DIFFERENT | Difference in value, concept, entity, period, duration, unit or selection |
| V1_ONLY_SOURCE_VALID | PDF verifies a target fact V2 loses |
| V1_ONLY_INVALID | V1 candidate lacks valid source support / has incorrect context |
| V2_ONLY_SOURCE_VALID | V2 correctly recovers what V1 misses |
| BOTH_MISS_REPORTED | Independent PDF review proves reported fact both miss |
| SOURCE_NOT_REPORTED | Target genuinely absent in filing |
| SOURCE_AMBIGUOUS | PDF cannot establish fact or ownership |
| INPUT/OCR_ERROR | Cannot yet fairly compare extraction |

Source-verify stratified V1-only and disagreement samples across sectors, layouts, Q4/YTD, current/prior, units, per-share, notes, OCR and continuation. **V1 is never gold truth.** The PDF and locked source contract decide. E02's `ENTITY_UNRESOLVED`, `NO_TARGET_CANDIDATE` and raw-column counts are diagnostic *proxies*, not independently verified missing target facts.

**Deliver:** `reports/v1_v2_same_input/<run_id>/input_manifest.json`, `fact_ledger.parquet`, `disagreement_review.csv`, `source_verification.jsonl`, and `gap_summary.json`. Report observed totals and sample uncertainty honestly.

## 3. The actual architecture change — V1 must feed candidates into V2

The current `src/cse_financial_etl/v2/orchestration/filing_pipeline.py` runs only this source path:

```text
V2 detect_statement_regions → reconstruct_statements → bind_column_context(H0/H1)
→ build_candidates → resolve_source_facts → validate_source_facts
→ derive_facts → production_selection
```

A better H0/H1 header binder **cannot recover a page, table, row or numeric cell V2 never reconstructed**. Small entity-only fixes cannot be the whole strategy.

**Implement a second challenger-only upstream source-observation path** using V1's actual document/table/row/cell compiler capabilities:

```text
                          EXACT PDF + SHA
                                │
             ┌──────────────────┴─────────────────┐
             │                                    │
    V2 structural reader                V1 physical reader/compiler
             │                           (source observations only)
             └──────────────────┬─────────────────┘
                                ↓
                    Source-anchored observation adapter
                                ↓
                   Deduplicated typed candidate union
                                ↓
                 V2 source-context/evidence verification
                                ↓
             Existing V2 resolver / SourceFact / CandidateTrace
                                ↓
             Existing validation → selection → publication
```

**Do not feed V1 final published numbers into V2.** Feed *source observations* recovered from PDF geometry before any V1 unsafe inference or final publication. The existing repo's V1→V2 component matrix identifies reusable assets: `compiler/header_tree.py`, `compiler/units.py`, `compiler/statement_compiler.py`, `compiler/column_compiler.py`, `compiler/structure_normalizer.py`, `document/table_reconstructor.py`, `document/region_detector.py`, and `document/continuation.py`. Wire winning physical readers and methods into a real provider, rather than produce another matrix that says `PORT_V1`.

Use V2 `CanonicalDocument`, `CanonicalStatement`, `FactCandidate`, `SourceFact`, `SourceRef`, `CandidateTrace`, validation and production selection as the authoritative contracts. Do **not** create two competing fact ledgers or a V3.

### Adapter acceptance contract

Each recovered observation must retain reader ID/version, PDF SHA, page/bbox or independently reanchored exact source span, statement/row/column IDs, raw label/value, source-concept candidate, and actual entity/period/duration/comparison/currency/scale/unit evidence refs. Missing or conflicting dimensions remain unresolved with explicit reasons. Observations without verifiable anchoring remain **DISCOVERY_ONLY**, never publishable. Reanchor V1 rows/cells to the original PDF; do not manufacture `SourceRef` from V1's final workbook.

Preserve: explicit source TOTAL_LIABILITIES only; PAT from accepted income-statement source, not CHANGES_IN_EQUITY; explicitly printed Q4 3M only (never FY−9M); EPS/NAVPS no statement-thousands inheritance; GROUP never silently COMPANY/BANK; issuer/expected query metadata never source proof. Duplicate observations dedupe by source identity; conflicts remain visible/withheld. Reader provenance must survive to a validated SourceFact **or** a reason-coded rejection.

Create a small challenger feature flag and provider/adapter boundary. Leave V1 production and the existing V2 mode untouched until measured promotion.

## 4. Experiment that must show large gains

Run on the **same frozen PDF SHA set**:

- **A — V1 normal + V2 normal:** classify same-input *source-valid V1-only gap*.
- **B — V2 + V1 safe source observations:** union candidates upstream of existing V2 validation/policy; measure new correct facts.
- **C — short ablation:** V2 + V1 page/statement; + V1 table/row/cell; + V1 headers/units; + full safe union. Keep only runs that answer which component supplies lift.

For every ablation, publish this table:

| KPI | V1 baseline | V2-only | V1-assisted V2 |
|---|---:|---:|---:|
| Identical PDF SHA count and errors | measured | measured | measured |
| Deduplicated source target observations | measured | measured | measured |
| Independently source-validated eligible facts | measured | measured | measured |
| Correct V1-only gap recovered / remaining | measured | measured | measured |
| **Additional correct draft-publishable SOURCE facts** | — | baseline | **measured** |
| Additional correct DERIVED and market facts | — | baseline | separately measured |
| Total same-definition draft-publishable | measured | baseline | measured |
| Previously correct facts lost | — | — | measured/explained |
| Critical wrong / NOT_REPORTED false positives | measured | measured | measured |
| Withheld after source evidence → resolver → validation → selection → publication | measured | measured | measured |

**Engineering outcome target:** first integrated full-universe run should recover a substantial part of the independently source-validated V1-only gap, provisionally **≥25% of that proven gap**; stretch **≥1,000 additional correct publishable facts if at least that many are genuinely recoverable**. These are targets, **not** fabricated results or guarantees. If the validated gap is smaller, measure the real recoverable fraction. If the union adds 20,000 candidates but few validated/selected facts, the next intervention must target the *measured loss stage*, not another isolated N18 issuer.

Do not claim a win with +4 on 13 filings or a candidate-count increase. A change only gets promoted when **correct full-universe source and publishable facts materially rise**, zero new critical wrong, no unexplained correct-fact losses, source evidence intact, and input+code manifests reproducible. Keep V1 production and the 8,924 floor unchanged.

## 5. Explicit stop-and-pivot rules

Stop incremental issuer/failure patching if **two meaningful identical-input universe experiments** fail to close a material part of the source-validated V1-only gap. Then interrogate the upstream V1 reader adapter and the loss waterfall, instead of repeating `ENTITY_UNRESOLVED → small fix → rerun`. If V1-only candidates cannot be source-anchored, quantify the unsupported portion; if source-anchored but V2 withholds them, show *which concrete rule and evidence* is responsible. Do not weaken validation merely to inflate output.

A full-universe count without same-input V1 comparison is an operational challenger, **not parity proof**. The E13 wrapper-vs-manifest dirty-SHA disagreement must be resolved before final governance.

## 6. Exact implementation handoff

1. **Freeze** identical source manifest and compare V1/V2 on same PDFs/output definitions. Explain the old dirty-manifest inconsistency.
2. **Build** target-fact differential with source-verified V1-only gap; do not compare raw candidate counts to gold.
3. **Implement** V1 physical source-observation provider and PDF anchoring adapter into V2 contracts.
4. **Union** V1/V2 candidates before V2 resolution, preserving conflicts and SourceRef; V1 published output never enters the union.
5. **Run** full same-input challenger plus component ablations; publish recovered correct source facts, selected/publishable lift, lost facts, and rejection waterfall.
6. **Keep/pivot** according to measured large-scale lift; recover highest-volume capability rather than next isolated issuer.
7. **Only then** address remaining 62 former-N18 FN families as regression/safety cases, and expand OCR/input recovery, CI and clean replay.
8. **After parity**, create a new unseen holdout, blind PDF gold, frozen first score, workbook/lineage reconciliation, OFFICIAL review and controlled V2 cutover with V1 rollback.

### Coding-agent instruction (copy verbatim)

> Build and measure a V1-assisted source-observation path into V2, not another entity-case patch. Freeze one exact same-PDF-SHA universe, produce a source-verified V1/V2 target-fact gap ledger, adapt V1 physical PDF/table/row/cell observations into V2 SourceRef/FactCandidate before the resolver, and run V2-only vs V1-assisted V2 through unchanged V2 validation, selection and publication. Report **additional correct source-only and draft-publishable facts** separately from derived metrics, count lost correct facts and all withholding stages, and preserve zero critical wrong. Do not use V1 final published values as gold or invent missing entity/period/unit. Do not claim success with a new document, tiny N18 improvement, raw candidates, or an unverified clean-run label. Commit code, tests, input/hash manifests and full-universe measurements. Keep V1 production until certified parity and fresh unseen proof.

**This document is the changed direction. The adapter, comparison and improved full-universe count remain to be IMPLEMENTED and MEASURED; do not mark them complete based on this MD.**
