# V2 Cutover Checklist

Do not mark institutional cutover complete because code exists. Production extraction stays on V1; V2 is the challenger (`engine=v2`). Human/artefact gates below still block `ready=True`, a V2 default, and V1 deletion.

1. [x] One canonical document representation is used by the V2 core.
2. [x] Source context is owned by columns, not reconstructed after metric matching.
3. [x] All required source facts retain exact provenance.
4. [x] Quarter-flow semantics are enforced (`duration_months == 3`, current, target period end).
5. [x] Q4 is reported-only (`FY - 9M` forbidden).
6. [x] Total Liabilities is explicit-source-only.
7. [x] Unresolved entity/period/unit facts cannot publish.
8. [x] Source and derived facts remain distinct.
9. [x] Release mode is explicit `ReleaseContext`.
10. [x] Coverage floors cannot silently decrease.
11. [x] Workbook output reconciles to release facts.
12. [ ] Golden corpus quality gates pass on institutional CSE filings (synthetic §37 gates pass; locked 33 probe is 209/237 recall 88.19%, 0 critical-wrong, duration/unit 100% on labeled gold; not newly human-re-adjudicated, not §37; recall is below 0.97 because unlabeled-entity and missing-line facts stay unpublished).
13. [ ] Frozen-universe acceptance passes.
14. [x] Repeated fixed-input runs are deterministic.
15. [ ] Current-universe run succeeds. (2026-09-09 V2 challenger `--engine v2`: 3,684 draft-publishable vs floor 8,924; EXTRACTED+DERIVED 3,993 vs 8,932; `ENGINEERING_FAILURES_PRESENT`. That count is not an accepted baseline.)
16. [x] V2 DRAFT workbook contains correct numeric data (synthetic e2e).
17. [x] OFFICIAL remains gated by required institutional review.

18. [ ] Production OCR runtime packaging proven (Dockerfile installs Tesseract + `ocr` extra; container smoke still required).
19. [x] Source accounting-regime lineage on SourceFact (engineering). Generic INSURANCE does not fabricate SLFRS4/SLFRS17. Still required on the 25–40 human gold set.
20. [ ] Production V2 publication path (`publish_production_workbook` + explicit `ReleaseContext`) adopted by `cse-etl run` after engine promotion.

Production extraction engine is **V1** (`configs/app.yml` `extraction.engine: v1`). V2 stays available as `engine=v2` for shadow/challenger runs. Do not delete V1. Do not set `extraction.engine: v2` or cutover `ready=True` until items 12, 13, 15, 18, 19, and 20 plus OFFICIAL human review.

Phase 15 remaining:

1. [ ] Make V2 extraction the default (blocked until items 12, 13, and 15).
2. [x] Keep V1 extraction as the production default; V2 is challenger-only.
3. [ ] Run another full frozen-universe acceptance.
4. [ ] Run the current snapshot to a passing acceptance (2026-09-09 V2 challenger ran and failed coverage floors; see item 15).
5. [ ] Generate DRAFT output from a passing current-universe run.
6. [ ] Complete required human checks (re-adjudicate the 25–40 gold set).
7. [ ] Remove obsolete V1 extraction paths only after the rollback window closes.
