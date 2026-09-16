# V2 Cutover Checklist

Do not mark institutional cutover complete because code exists. Production extraction stays on V1; V2 is the challenger (`engine=v2`).

**Status correction (recovery plan):** V2 is **NOT** engineering-complete and **NOT** blocked on OFFICIAL review only. First unseen holdout (T25) **FAILED** (entity-resolved recall 68.75%; 2 critical wrong facts). Fail-closed diagnostics are safe behavior, **not** acceptance passes.

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
12. [ ] Golden corpus quality gates pass on institutional CSE filings (T10 DEV useful; locked 33 probe 209/237 recall 88.19%; T25 holdout **FAILED** — not §37 institutional gold).
13. [ ] Frozen-universe acceptance passes. (Sept-10 artefacts missing; Sept-05 pin + `t26_frozen_universe_diagnostic.json` are **diagnostic only**, not acceptance.)
14. [x] Repeated fixed-input runs are deterministic.
15. [ ] Current-universe run succeeds. (2026-09-09 V2 challenger: 3,684 draft-publishable vs floor **8,924**; `ENGINEERING_FAILURES_PRESENT`. Fail-closed signal — **not** a pass.)
16. [x] V2 DRAFT workbook contains correct numeric data (synthetic e2e).
17. [ ] OFFICIAL human review — required **after** engineering completion (holdout pass + healthy universe + certification). Not the sole open gate today.

18. [x] Production OCR runtime packaging proven (Dockerfile + `cse-etl:ocr-smoke-v2` smoke PASS; `tests/v2/universe/t18_ocr_docker_smoke.json`).
19. [x] Source accounting-regime lineage on SourceFact (engineering). Generic INSURANCE does not fabricate SLFRS4/SLFRS17. Human gold regime checks remain under item 12 / OFFICIAL.
20. [x] Production V2 publication path wired for opt-in `engine=v2` (`production_workbook` / `run_production_pipeline`; default remains V1).

Production extraction engine is **V1** (`configs/app.yml` `extraction.engine: v1`). Do not delete V1. Do not set `extraction.engine: v2` or cutover `ready=True` until engineering gates 12/13/15 and OFFICIAL review (17) pass.

## Engineering recovery (before OFFICIAL)

See `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`:

- T24 REOPENED; T25 FAILED; diagnose LITE FN + SFCL critical wrong
- Promote failed holdout cases into DEV/regression; select a **new** unseen holdout
- Header H0/H1/H2 bake-off; finish G02/G04–G08 experiments
- Clean-SHA baseline + CI + current-universe challenger rerun

## Phase 15 remaining

1. [ ] Make V2 extraction the default (blocked on engineering + OFFICIAL).
2. [x] Keep V1 extraction as the production default; V2 is challenger-only.
3. [ ] Run another full frozen-universe acceptance (needs Sept-10 artefacts).
4. [ ] Run the current snapshot to a passing acceptance (floor 8924).
5. [ ] Generate DRAFT output from a passing current-universe run.
6. [ ] Complete required OFFICIAL human review (after engineering completion).
7. [ ] Remove obsolete V1 extraction paths only after the rollback window closes.
