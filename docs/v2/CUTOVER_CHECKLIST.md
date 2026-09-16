# V2 Cutover Checklist

Do not mark institutional cutover complete because code exists. Production extraction stays on V1; V2 is the challenger (`engine=v2`).

**Verified path:** `docs/v2/VERIFIED_OPEN_WORK_AND_FINAL_ENGINEERING_PATH.md` (F3 checkpoint `a537f8f`; N12 freeze `ef4b200`). V2 is **NOT CERTIFIED** and **NOT** ready for cutover. OFFICIAL is **not** the only open blocker.

## First T25 holdout (retired)

```text
FAILED initially → investigated → LITE F1/F3 fixed → SFCL truth corrected
→ rescored 1.0 on inspected entity-resolved facts → permanently retired
```

Final holdout path: **N16 identity locked → N17 blind truth pending → N18 scoring pending**.

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
12. [ ] Golden corpus quality gates pass on institutional CSE filings (T10 DEV useful; locked 33 probe 209/237; first T25 **retired** after repair; **N16/N17/N18** is the final holdout path — not §37 yet).
13. [ ] Frozen-universe acceptance passes. (Sept-10 artefacts missing; Sept-05 pin is **diagnostic only**.)
14. [x] Repeated fixed-input runs are deterministic (N11/N12 clean-SHA locked-33: `all_deterministic=true`).
15. [ ] Current-universe run succeeds. (Prior V2 challenger 3,684 vs floor **8,924** predates F1/F3; fresh N14 required.)
16. [x] V2 DRAFT workbook contains correct numeric data (synthetic e2e).
17. [ ] OFFICIAL human review — only after engineering acceptance (N17–N18 pass, N13–N14, certification). Not the sole open gate.

18. [x] Production OCR runtime packaging proven (`t18_ocr_docker_smoke.json`).
19. [x] Source accounting-regime lineage on SourceFact (engineering).
20. [x] Production V2 publication path wired for opt-in `engine=v2` (default remains V1).

Production extraction engine is **V1**. Do not set `extraction.engine: v2` or cutover `ready=True` until engineering gates and OFFICIAL review pass.

## Open engineering (before OFFICIAL)

See `docs/v2/VERIFIED_OPEN_WORK_AND_FINAL_ENGINEERING_PATH.md`:

- **N17** blind adjudication — package ready: `docs/v2/N17_BLIND_ADJUDICATION.md` + `n17_blind_review_queue.json` (human; no V1/V2 peeking)
- **N18** score new holdout without retuning mid-score
- **N11/N12** DONE (clean-SHA locked-33 + canonical regen)
- **N13** CI green / PR (branch on origin; open compare URL if needed)
- **N14** fresh current-universe V2 challenger
- G02/G04–G08 source-truth decisions if material; H1/H2 only if needed after F1/F3
- **N20** Sept-10 exact replay when artefacts exist

## Phase 15 remaining

1. [ ] Make V2 extraction the default (blocked on engineering + OFFICIAL).
2. [x] Keep V1 extraction as the production default; V2 is challenger-only.
3. [ ] Full frozen-universe acceptance (needs Sept-10 artefacts).
4. [ ] Current snapshot passing acceptance (floor 8924).
5. [ ] DRAFT from a passing current-universe run.
6. [ ] OFFICIAL human review (after engineering completion).
7. [ ] Remove obsolete V1 paths only after rollback window closes.
