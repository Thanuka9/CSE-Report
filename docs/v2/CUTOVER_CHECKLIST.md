# V2 Cutover Checklist

Do not mark institutional cutover complete because code exists. Engineering extraction is on V2; human/artefact gates below still block `ready=True` and V1 deletion.

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
12. [ ] Golden corpus quality gates pass on institutional CSE filings (synthetic §37 gates pass; locked 33 probe is 236/238 recall 99.16%, 0 critical-wrong, duration/unit 100% on labeled gold; not newly human-re-adjudicated, not §37).
13. [ ] Frozen-universe acceptance passes.
14. [x] Repeated fixed-input runs are deterministic.
15. [ ] Current-universe run succeeds.
16. [x] V2 DRAFT workbook contains correct numeric data (synthetic e2e).
17. [x] OFFICIAL remains gated by required institutional review.

Production extraction engine is **V2** (`configs/app.yml` `extraction.engine: v2`). V1 `extract_filing` stays importable as `engine: v1`. Do not delete V1. Do not set cutover `ready=True` until items 12, 13, and 15 plus OFFICIAL human review.

Phase 15 remaining:

1. [x] Make V2 extraction the default.
2. [x] Keep V1 extraction for replay/challenger only.
3. [ ] Run another full frozen-universe acceptance.
4. [ ] Run the current snapshot.
5. [ ] Generate DRAFT output.
6. [ ] Complete required human checks (re-adjudicate the 25–40 gold set).
7. [ ] Remove obsolete V1 extraction paths only after the rollback window closes.
