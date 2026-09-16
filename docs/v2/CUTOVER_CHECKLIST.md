# V2 Cutover Checklist

Do not mark institutional cutover complete because code exists. Production extraction stays on V1; V2 is the challenger (`engine=v2`). **Only OFFICIAL human review remains** before any promote decision. Do not set `ready=True`, a V2 default, or delete V1 until that review completes.

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
12. [x] Investigation gold closed (T10 DEV 40 items + T25 HOLDOUT 24 items; G01/G03/G09 KEEP). Institutional §37 re-adjudication of 25–40 filings is deferred to **OFFICIAL review** (locked 33 probe remains 209/237, not newly human-re-adjudicated).
13. [x] Frozen-universe engineering closed **fail-closed**: September-10 artefacts missing in-repo; best pin is 2026-09-05 (`tests/v2/universe/t26_frozen_universe_diagnostic.json`: NEW 139 / LOST 22 / UNCHANGED 15). Not an accepted frozen-universe pass.
14. [x] Repeated fixed-input runs are deterministic.
15. [x] Current-universe engineering closed **fail-closed**: 2026-09-09 V2 challenger `--engine v2` reported 3,684 draft-publishable vs floor **8,924** (`ENGINEERING_FAILURES_PRESENT`). Floor not lowered; not an accepted baseline.
16. [x] V2 DRAFT workbook contains correct numeric data (synthetic e2e).
17. [x] OFFICIAL remains gated by required institutional review.

18. [x] Production OCR runtime packaging proven (Dockerfile installs Tesseract + `ocr` extra; `docker run … cse-etl:ocr-smoke-v2 …/v2_ocr_runtime_smoke.py` → `PASS native_tokens=0 ocr_tokens=21 parser_name=v2.ocr.tesseract`; evidence `tests/v2/universe/t18_ocr_docker_smoke.json`).
19. [x] Source accounting-regime lineage on SourceFact (engineering). Generic INSURANCE does not fabricate SLFRS4/SLFRS17. Still required on the 25–40 human gold set under OFFICIAL.
20. [x] Production V2 publication path (`publish_production_workbook` + explicit `ReleaseContext`) wired for opt-in `engine=v2` via `cse_financial_etl.reporting.production_workbook` / `run_production_pipeline` (default remains V1 in `configs/app.yml`).

Production extraction engine is **V1** (`configs/app.yml` `extraction.engine: v1`). V2 stays available as `engine=v2` for shadow/challenger runs. Do not delete V1. Do not set `extraction.engine: v2` or cutover `ready=True` until **OFFICIAL human review** accepts or rejects the fail-closed evidence above.

## Phase 15 remaining

1. [ ] Make V2 extraction the default (**blocked on OFFICIAL review**).
2. [x] Keep V1 extraction as the production default; V2 is challenger-only.
3. [ ] Run another full frozen-universe acceptance (**blocked on OFFICIAL + missing Sept-10 artefacts**).
4. [ ] Run the current snapshot to a passing acceptance (**blocked on OFFICIAL**; challenger already fail-closed below 8924).
5. [ ] Generate DRAFT output from a passing current-universe run (**blocked on OFFICIAL**).
6. [ ] **OFFICIAL human review** — sole remaining gate: re-adjudicate institutional gold / accept fail-closed T26–T27 outcomes / decide promote-or-hold.
7. [ ] Remove obsolete V1 extraction paths only after the rollback window closes (**blocked on OFFICIAL + promote**).
