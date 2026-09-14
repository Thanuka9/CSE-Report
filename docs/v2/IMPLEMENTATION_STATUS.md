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
- [ ] Production-image OCR smoke proven (`scripts/v2_ocr_runtime_smoke.py` on the built image)

Evidence:
- tests: `tests/v2/unit/test_native_reader.py`, `tests/v2/unit/test_ocr_scanned_sample.py`, `tests/v2/unit/test_ocr_runtime_packaging.py`
- remaining risks: OCR implementation rasterizes pages through Tesseract when installed. Missing Tesseract raises `OCR_REQUIRED_NOT_AVAILABLE`. The production `Dockerfile` now installs `tesseract-ocr`, `ghostscript`, and `--extra ocr`. Scanned-PDF support is not production-ready until the production-image OCR smoke in `.github/workflows/ocr-production-validation.yml` passes.

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
- [ ] 25–40 deeply re-adjudicated real CSE filings meeting plan §37 (not claimed)

Evidence:
- tests: `tests/v2/unit/test_synthetic_golden_corpus.py`, `tests/v2/unit/test_golden_shadow_cutover.py`, `tests/v2/unit/test_real_pdf_golden.py`, `tests/v2/unit/test_gold_lock.py`, `tests/v2/unit/test_adjudication_overlay.py`
- fixtures: `tests/v2/golden/corpus.py`, `tests/v2/golden/real_filings_lock.json`, `tests/v2/golden/adjudication_round1.json`, `tests/fixtures/golden_financial_facts.json`
- remaining risks: the lock is still not institutional gold. After heading-true overlay and fail-closed matching, the locked 33 scores **209/237** true positives, **0 critical-wrong**, recall **88.19%**, duration/unit **100%** on labeled gold. Recall stays below 0.97 because unlabeled-entity pages, missing lines (HDFC operating profit), and collapsed/unresolved rows remain unpublished. Plan §37 is **not** claimed. Production extraction engine is V1; V2 is challenger-only.

## Phase 14 — Full Universe Shadow Run
- [x] Fact-identity shadow diff with class counts by metric/reason/issuer/parser/sector
- [x] CLI: `scripts/v2_shadow_diff.py`, `scripts/v2_universe_shadow.py`
- [x] Pinned best-available V1 snapshot `outputs/normalized_facts_2026-09-05.csv` (`tests/v2/golden/universe_pin.json`)
- [ ] Frozen September-10 universe artefacts and V1/V2 acceptance

Evidence:
- tests: `tests/v2/unit/test_golden_shadow_cutover.py`, `tests/v2/unit/test_universe_shadow.py`
- remaining risks: the Sept-10 frozen snapshot is still not in-repo; the 2026-09-05 pin is a diagnostic shadow only

## Phase 15 — Cutover
- [x] Production extraction engine is **V1** (`configs/app.yml` `extraction.engine: v1`); `engine: v2` is the challenger until gold and universe gates pass
- [x] `assert_v1_remains_default` still refuses V1 deletion when `ready=True`
- [ ] Institutional sign-off / V2 default / V1 deletion (explicitly not done)

Evidence:
- tests: `tests/v2/unit/test_golden_shadow_cutover.py`, `tests/v2/unit/test_release_context.py`, `tests/v2/unit/test_production_engine.py`
- remaining risks: raising `ready=True` in a future change must not delete V1 production code

---

## Plan audit (2026-09-13)

Checked `CSE_V2_CURSOR_AGI_IMPLEMENTATION_PLAN.md` §§0–44 against the isolated V2 tree. Production extraction engine is V1; V2 is challenger-only. Coverage floor is still `min_draft_publishable = 8924`. V1 `extract_filing` remains importable. Cutover `ready` stays false until human gold, frozen universe, and OFFICIAL review.

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

### Human-ready leftovers (engineering is done)
- Plan §32 / Phase 13 / checklist 12: 25–40 **human re-adjudicated** CSE filings at §37 gates (bbox, unit, entity, period). Locked 33 probe is **209/237**, not newly human-adjudicated, not §37.
- Plan §14 / Phase 14 / checklist 13: frozen September-10 universe artefacts (2026-09-05 CSV is pinned as best-available only)
- Plan §15 / checklist 15: current-universe run that meets floors. 2026-09-09 V2 challenger (`--engine v2`, SHA `606c530`) is 3,684 draft-publishable vs 8,924 and `ENGINEERING_FAILURES_PRESENT`. Not an accepted baseline. Production default remains V1.
- Checklist 17 / Phase 15: OFFICIAL human review, then V1 deletion after the rollback window

### Deferred, not launch-blocking
- Plan §24: Paddle OCR is still deferred. Tesseract OCR is implemented and packaged in the production Dockerfile; scanned-PDF support is not production-ready until the container smoke passes.
- Plan §25–26: Table Transformer / BGE / rankers

### Closed vs earlier audit
- Plan §16: last-traded as-of quarter-end wrapper plus leak test (`v2/market/quarter_end_price.py`)
- Plan §33: Abans/CDB/Softlogic geometric fail-closed tests plus named PDFs when present; SDF/RENU stay out of the lock
- Phase 15 step 1: production default remains V1; V2 is `engine: v2` challenger only

V2 is **not** complete under plan §44 items 12, 13, and 15. Those are the human/artefact leftovers.

Extraction investigation status (T00–T29) is `docs/v2/EXTRACTION_INVESTIGATION_STATUS.md`. Engineering T00–T20 harnesses are in place. T10/T25–T29 remain human- or artefact-blocked. Production engine stays V1.
