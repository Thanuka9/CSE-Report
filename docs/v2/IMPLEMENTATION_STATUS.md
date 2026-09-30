# V2 Implementation Status

Mark a phase complete only when its acceptance tests pass.

## Phase 0 — Freeze and Isolate
- [x] V1 reference record (`docs/v2/V1_REFERENCE.md`, SHA `ae2a721a332de252c841693b301b52692f8863d8`)
- [x] V2 decision record (`docs/v2/DECISIONS.md`)
- [x] `src/cse_financial_etl/v2/` isolated package
- [x] `tests/v2/` tree
- [x] Parallel replay script skeleton (`scripts/v2_fixed_input_replay.py`)
- [x] Implementation plan copied to `docs/v2/AGENT_IMPLEMENTATION_PLAN.md`

Evidence:
- tests: `tests/v2/unit/test_contracts.py`, `tests/v2/unit/test_replay.py`
- remaining risks: replay still needs frozen Sept-10 artefacts; V2 pipeline determinism is covered on synthetic filings

## Phase 1 — Governance Guards First
- [x] Coverage-floor non-lowering CI check
- [x] Explicit V2 `ReleaseContext`
- [x] Workbook reconciliation test harness

Evidence:
- tests: `tests/v2/unit/test_coverage_floors.py`, `tests/v2/unit/test_release_context.py`, `tests/v2/unit/test_workbook_reconciliation.py`
- remaining risks: V1 production still uses `set_release_mode`; that is unchanged until V2 cutover

## Phase 2 — Core Contracts
- [x] `SourceRef`, canonical document/statement, `StatementColumn`/`StatementCell`
- [x] `FactCandidate`, `SourceFact`, `DerivedFact`
- [x] Diagnostic status enums
- [x] Serialization / frozen-model / provenance tests

Evidence:
- tests: `tests/v2/unit/test_contracts.py`, `tests/v2/property/test_contract_invariants.py`
- remaining risks: statement reconstruction and column resolvers exist; live CSE calibration is started in Phase 6/13 but not §37-complete

## Phase 3 — Native Document Reader
- [x] PyMuPDF → `CanonicalDocument`
- [x] Text, bbox, page, line grouping, parser metadata
- [x] Deterministic re-parse test
- [x] Synthetic native PDF fixture (institutional golden PDFs remain Phase 13)

Evidence:
- tests: `tests/v2/unit/test_native_reader.py`
- remaining risks: visual-baseline clustering may still need golden-PDF calibration in Phase 5

## Phase 4 — Statement Detection
- [x] Deterministic heading-band statement-page/region detection
- [x] Notes / contents / multi-title index false positives constrained
- [x] Explicit continuation only; no numeric-density type invention

Evidence:
- tests: `tests/v2/unit/test_statement_detector.py`
- remaining risks: letterhead/company-name collisions with title phrases; title below a 12-line heading band

## Phase 5 — Statement Reconstruction
- [x] Rows, columns, header hierarchy, cells with lineage
- [x] No `metric_code` assignment during reconstruction

Evidence:
- tests: `tests/v2/unit/test_statement_reconstruction.py`
- remaining risks: header-cue heuristics may drop unusual account lines; no separate `header_tree.py` (header lines are classified inside `table_reconstructor.py`)

## Phase 6 — Column-Owned Context
- [x] Entity / period / duration / comparison-role / unit resolvers bound to `StatementColumn`
- [x] Query targets (`expected_entity_scope`, `target_period_end`) are ignored as source
- [x] Real-PDF header cues: dotted `dd.mm.yyyy`, split year rows, Group/Company and six-month/quarter column splits

Evidence:
- tests: `tests/v2/unit/test_column_context.py`, `tests/v2/unit/test_real_pdf_golden.py`
- remaining risks: Hayleys-style year+quarter mixed grids still publish some FY FLOW as quarter (those stay withheld); company-only pages without the word Company remain unpublished

## Phase 7 — Concept Registry
- [x] Single registry loader with conflict detection
- [x] Source vs derived concepts; `TOTAL_LIABILITIES` derivation forbidden
- [x] Alias match returns original source label plus regime bucket

Evidence:
- tests: `tests/v2/unit/test_concept_registry.py`, `tests/v2/unit/test_matcher_extended.py`
- remaining risks: SLFRS4 vs SLFRS17 still needs explicit filing/report evidence, not issuer-type inference

## Phase 8 — Row Concept Matching
- [x] Exact / RapidFuzz candidates; abstain on forbidden labels and wrong statement type
- [x] `source_concept` / `matched_alias` / proven `accounting_regime` on `ConceptCandidate` and `SourceFact`

Evidence:
- tests: `tests/v2/unit/test_concept_registry.py`, `tests/v2/unit/test_matcher_extended.py`, `tests/v2/unit/test_resolver_and_validation.py`
- remaining risks: controlled-alias vs exact-alias scoring on noisy OCR labels; ambiguity-delta still synthetic

## Phase 9 — Candidate Builder and Resolver
- [x] No assumed entity/period/unit; GROUP is not converted to COMPANY
- [x] Every emitted `SourceFact` retains `SourceRef` lineage
- [x] Non-quarter FLOW facts are withheld (`EXACT_QUARTER_NOT_REPORTED` / `CUMULATIVE_ONLY`)

Evidence:
- tests: `tests/v2/unit/test_resolver_and_validation.py`
- remaining risks: real filings with mixed COMPANY/GROUP column grids

## Phase 10 — Existing Validation Integration
- [x] Compatibility boundary to proven V1 `compute_quarter_ratios`
- [x] Q4/cumulative FLOW fail-closed; liabilities not derived from assets−equity
- [x] `EPS_SELECTED` and ratios are `DerivedFact` (no `cell_id`)

Evidence:
- tests: `tests/v2/unit/test_resolver_and_validation.py`
- remaining risks: V1 ratio edge cases (negative equity) inherit V1 policy

## Phase 11 — OCR / Complex PDF Route
- [x] Same `CanonicalDocument`; detector is parser-agnostic
- [x] OCR only when native token count is 0 or `force_ocr=True`
- [x] OCR implementation exists (`v2.ocr.tesseract` rasterize + image_to_data)
- [x] Production `Dockerfile` installs Tesseract, Ghostscript, and the `ocr` extra
- [x] Production-image OCR smoke path wired (`scripts/v2_ocr_runtime_smoke.py`; `.github/workflows/ocr-production-validation.yml`)

Evidence:
- tests: `tests/v2/unit/test_native_reader.py`, `tests/v2/unit/test_ocr_scanned_sample.py`, `tests/v2/unit/test_ocr_runtime_packaging.py`
- remaining risks: OCR implementation rasterizes pages through Tesseract when installed. Missing Tesseract raises `OCR_REQUIRED_NOT_AVAILABLE`. Image smoke is `workflow_dispatch` only; full-universe scanned-PDF coverage is not claimed. Cutover checklist item 18 is engineering-closed (fail-closed on universe OCR errors).

## Phase 12 — Workbook V2 Renderer
- [x] Numeric-or-null Snapshot cells; status strings on other sheets
- [x] Reconciliation before save; explicit `ReleaseContext` required
- [x] Zero is numeric, not a missing-status string

Evidence:
- tests: `tests/v2/unit/test_workbook_v2.py`, `tests/v2/unit/test_workbook_reconciliation.py`
- remaining risks: Snapshot currently pivots latest period × `SNAPSHOT_METRICS` only

## Phase 13 — Golden Corpus Run
- [x] Scoring harness: precision/recall plus entity/period/duration/unit/numeric accuracy and `critical_wrong_populated`
- [x] Synthetic adjudicated corpus (>=25 cases) with engineering gates from plan §37
- [x] Locked 33-filing local scoring set (`tests/v2/golden/real_filings_lock.json`) mixing MANUAL_QA, MANUAL_OR_PRIOR, and V1 PIPELINE_SEEDED probes
- [x] Local runner over the locked set (`scripts/v2_real_golden_run.py`)
- [x] Audited vendor PAT truths: JAT `108959808`, COMB BANK `16621006000`, DIAL `8187022000`, JKH `5378093000`
- [x] Investigation gold scored (T10 DEV + T25 holdout; fail-closed vs §37 institutional gold)

Evidence:
- tests: `tests/v2/unit/test_synthetic_golden_corpus.py`, `tests/v2/unit/test_golden_shadow_cutover.py`, `tests/v2/unit/test_real_pdf_golden.py`, `tests/v2/unit/test_gold_lock.py`, `tests/v2/unit/test_adjudication_overlay.py`
- fixtures: `tests/v2/golden/corpus.py`, `tests/v2/golden/real_filings_lock.json`, `tests/v2/golden/adjudication_round1.json`, `tests/fixtures/golden_financial_facts.json`
- scores: `tests/v2/universe/t10_score.json` (31 TP / entity-resolved recall 1.0); `tests/v2/universe/t25_holdout_score.json` (11 TP / recall ~0.6875; no retune)
- remaining risks: the lock is still not institutional gold. Locked 33 probe **209/237**, **0 critical-wrong**, recall **88.19%**. Plan §37 and cutover checklist item 12 are **engineering-closed, institutional fail-closed**. Production extraction engine is V1; V2 is challenger-only.

## Phase 14 — Full Universe Shadow Run
- [x] Fact-identity shadow diff with class counts by metric/reason/issuer/parser/sector
- [x] CLI: `scripts/v2_shadow_diff.py`, `scripts/v2_universe_shadow.py`
- [x] Pinned best-available V1 snapshot `outputs/normalized_facts_2026-09-05.csv` (`tests/v2/golden/universe_pin.json`)
- [x] T26 frozen-universe **diagnostic** recorded (Sept-05 pin only; **not** Sept-10 acceptance; checklist 13 remains open)

Evidence:
- tests: `tests/v2/unit/test_golden_shadow_cutover.py`, `tests/v2/unit/test_universe_shadow.py`
- artefact: `tests/v2/universe/t26_frozen_universe_diagnostic.json` (Sept-05 pin; Sept-10 missing; NEW 139 / LOST 22 / UNCHANGED 15)
- remaining risks: Sept-10 freeze still missing; fail-closed diagnostic ≠ acceptance

## Phase 15 — Cutover
- [x] Production extraction engine is **V1** (`configs/app.yml` `extraction.engine: v1`); `engine: v2` is the challenger until gold and universe gates pass
- [x] `assert_v1_remains_default` still refuses V1 deletion when `ready=True`
- [x] V2 workbook publish path + `workbook_dispatch` wired (`production_workbook.py`, `run_production_pipeline.py`; tests `test_production_workbook_routing`, `test_workbook_dispatch`)
- [ ] **Pending engineering recovery:** T25 holdout FAILED (recall 68.75%; LITE FN; SFCL critical wrong) — see `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`
- [ ] **Pending after engineering:** institutional **OFFICIAL** review; V2 default / V1 deletion not started

Evidence:
- tests: `tests/v2/unit/test_golden_shadow_cutover.py`, `tests/v2/unit/test_release_context.py`, `tests/v2/unit/test_production_engine.py`
- remaining risks: do not claim OFFICIAL-only; critical wrong facts reopen extraction work before cutover

---

## Plan audit (2026-09-13; status corrected 2026-09-16)

Checked `CSE_V2_CURSOR_AGI_IMPLEMENTATION_PLAN.md` §§0–44 against the isolated V2 tree. Production extraction engine is V1; V2 is challenger-only. Coverage floor is still `min_draft_publishable = 8924`. V1 `extract_filing` remains importable. Cutover `ready` stays false. **T25 failed; engineering incomplete; not OFFICIAL-only.**

### Hard rules with tests
Never invent entity/period/unit; never convert GROUP→COMPANY; non-quarter FLOW withheld; Q4/cumulative FLOW fail-closed; `TOTAL_LIABILITIES` not derived; workbook Snapshot cells numeric-or-blank; explicit `ReleaseContext`; V2 does not call `set_release_mode`; OFFICIAL omits `REVIEW` facts; closing market price is not `LAST_TRADED_PRICE`.

### Package tree vs plan §6
Folded into existing modules (recorded, not missing product):
- `statements/column_context.py` → `resolution/column_context.py`
- `resolution/entity.py`, `period.py`, `units.py`, `candidate_builder.py` → `column_context.py` + `resolver.py`
- `taxonomy/profiles.py` → regime fields on `ConceptDefinition`
- `validation/structural.py`, `cross_period.py`, `publication.py` → `validation/accounting.py` + resolver publication reasons
- `orchestration/universe_pipeline.py` → `diagnostics/universe.py` live shadow only
- `statements/header_tree.py` not built; header cues are line-class heuristics

Extra vs plan (allowed): `v2/governance/`, `diagnostics/golden.py`, `shadow.py`, `real_filings.py`, `exceptions.py`, `v2/production/`, `v2/market/`.

Tests live under `tests/v2/unit`, `tests/v2/property`, `tests/v2/golden`. Plan dirs `tests/v2/fixtures`, `regression`, and `universe` were not created as separate trees.

### Open institutional / engineering gates
- Checklist 12: T10 useful; T25 **FAILED** (68.75% recall; 2 critical wrong) — not §37 gold
- Checklist 13: T26 Sept-05 diagnostic only; September-10 artefacts absent — **open**
- Checklist 15: 2026-09-09 V2 challenger **3,684** vs floor **8,924** — fail signal, **not** a pass
- Checklist 17: OFFICIAL review required **after** engineering completion
- Checklist 18–20: OCR packaging, regime lineage, V2 workbook dispatch — engineering done

### Active recovery
- Follow `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md` (N00–N24)
- T24 REOPENED; T25 FAILED; T28 BLOCKED ON ENGINEERING; T29 BLOCKED ON ENGINEERING + OFFICIAL

### Deferred
- Plan §24: Paddle OCR deferred; Tesseract packaged (item 18)
- Plan §25–26: Table Transformer / BGE / rankers

### Closed vs earlier audit
- Plan §16: last-traded as-of quarter-end wrapper plus leak test (`v2/market/quarter_end_price.py`)
- Plan §33: Abans/CDB/Softlogic geometric fail-closed tests plus named PDFs when present; SDF/RENU stay out of the lock
- Phase 15 step 1: production default remains V1; V2 is `engine: v2` challenger only

V2 cutover is **not** authorized. Certification is **NOT CERTIFIED — BLOCKED ON ENGINEERING**.

Extraction investigation status: `docs/v2/EXTRACTION_INVESTIGATION_STATUS.md`. Production engine stays V1.
