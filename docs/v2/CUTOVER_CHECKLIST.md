# V2 Cutover Checklist

Do not mark institutional OFFICIAL publication complete because AI QA exists.

**Verified path:** `docs/v2/HYBRID_RELEASE_CONTRACT.md`. Production extraction is **V2** after recorded DRAFT cutover approval 2026-09-22. Publication remains **DRAFT**. OFFICIAL is **NOT YET HUMAN-CERTIFIED**. V1 remains the rollback backend. DRAFT is not blocked on the old 100 MANUAL_QA gold floor.

Hybrid 829 same-input parity is the extraction proof. N17/N18 are superseded as a **pre-cutover extraction** holdout and remain required before deleting V1 or certifying V2-native extraction. See the contract.

## First T25 holdout (retired)

```text
FAILED initially → investigated → LITE F1/F3 fixed → SFCL truth corrected
→ rescored 1.0 on inspected entity-resolved facts → permanently retired
```

Final holdout path for hybrid cutover: **829 SHA-pinned same-input parity (passed)**. Independent 100 MANUAL_QA issuers remain an **OFFICIAL** gate, not a DRAFT rollback trigger. N17/N18 remain a V2-native / V1-retirement package, not a silent skip.

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
12. [ ] OFFICIAL golden corpus quality gates pass (`min_gold_issuers: 100` counts MANUAL_QA only; committed fixture currently has 4 MANUAL_QA issuers). AI/evidence dossier covers all 100 benchmark issuers plus 281-universe precheck: `reports/gold_gate/AI_QA_DOSSIER.md`. Do not relabel PIPELINE_SEEDED / UNADJUDICATED. DRAFT production is not blocked on this item.
13. [ ] Frozen-universe acceptance passes. (Sept-10 artefacts missing; Sept-05 pin is **diagnostic only**.)
14. [x] Repeated fixed-input runs are deterministic (N11/N12 clean-SHA locked-33: `all_deterministic=true`).
15. [x] Hybrid V2 production smoke (`scripts/v2_production_smoke.py`, 6/6 real PDFs, signed JKH PAT on native facts, DRAFT 56 / OFFICIAL 1). Not a full-universe 8,924 run.
16. [x] V2 DRAFT workbook contains correct numeric data (synthetic e2e).
17. [ ] OFFICIAL human review — 100 MANUAL_QA issuers and 8,924 APPROVED/CURATED native facts. Not implied by the DRAFT engine cutover.

18. [x] Production OCR runtime packaging proven (`t18_ocr_docker_smoke.json`).
19. [x] Source accounting-regime lineage on SourceFact (engineering).
20. [x] Production V2 publication path is the DRAFT default (`engine: v2`). V1 remains rollback.

Production extraction engine is **V2** (DRAFT). Do not set `release_mode: OFFICIAL` or cutover `ready=True` until 100 MANUAL_QA issuers and the 8,924 APPROVED/CURATED floor pass. V1 rollback remains.

## Open engineering (before OFFICIAL)

See `docs/v2/HYBRID_RELEASE_CONTRACT.md`:

- **100 MANUAL_QA issuers** — AI QA dossier ingested; humans still must sign remaining gold. Do not invent MANUAL_QA.
- **OFFICIAL output completeness gate** — `min_official_publishable: 8924` when `release_mode` is OFFICIAL
- DRAFT cutover approved 2026-09-22 (`engine: v2`); V1 rollback retained

## Phase 15 remaining

1. [x] Make V2 extraction the DRAFT production default (approved 2026-09-22).
2. [x] Keep V1 extraction as the rollback backend; do not delete V1.
3. [ ] Full frozen-universe acceptance (needs Sept-10 artefacts).
4. [ ] Current snapshot passing acceptance (floor 8924).
5. [ ] DRAFT from a passing current-universe run.
6. [ ] OFFICIAL human review (100 MANUAL_QA issuers + 8,924 APPROVED/CURATED facts).
7. [ ] Remove obsolete V1 paths only after rollback window closes.
