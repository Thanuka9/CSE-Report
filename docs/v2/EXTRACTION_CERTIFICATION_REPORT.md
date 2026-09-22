# V2 Extraction Certification Report

**Status: ENGINEERING COMPLETE FOR V2 DRAFT CUTOVER — OFFICIAL DATA RELEASE NOT CERTIFIED; HUMAN-PROOF GATES PENDING**

Production extraction remains **V1** until a recorded human cutover approval.
The configured publication mode remains **DRAFT**. The 8,924 floor is unchanged.

Remote CI run #241 passed on Ubuntu and Windows at
`ef30bc0bda4815eaea74ed231b4f0f44617dda92`, including the new fail-closed
native-governance propagation and OFFICIAL native-release completeness tests.

Production extraction remains **V1** until recorded OFFICIAL approval.
Coverage floor remains **8924**. Do not set `configs/app.yml` `extraction.engine: v2`.
Header production default remains **H0**. H1 is challenger-only. Hybrid cutover uses
proven V1 extraction as the baseline backend, so H2 is not a hold item.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.
Verified engineering checkpoint: `a537f8fd83663b1d21a70b400428869256e882bf`.
N11/N12 clean locked-33 SHA: `2ff5d1ff1b04d0fbe559dc33d438e9072d030879` (freeze `ef4b200`).

Final path: `docs/v2/VERIFIED_OPEN_WORK_AND_FINAL_ENGINEERING_PATH.md`.
N17 package: `docs/v2/N17_BLIND_ADJUDICATION.md`.

## Verdict

829 pinned-file hybrid parity passed (3,183 V1 TARGET facts: 3,048 preserved, 135
quarantined, 0 unexplained). Remote GitHub CI passed on both Ubuntu and Windows in
Deterministic production checks run #238
(`35729229940`, head `282fe57af8d3d0bebbf007e06d83eb26e54c4774`).
The technical pack is READY FOR OFFICIAL DECISION. Do not flip `engine: v2` before
recorded OFFICIAL approval. V1 remains the fallback backend.

## Current release decision

| Gate | Result |
|---|---|
| 829 pinned-file hybrid parity | PASS — 0 unexplained V1 TARGET losses/mismatches |
| Unresolved V1/V2 conflicts | QUARANTINED |
| Coverage floor | 8,924 unchanged |
| Remote deterministic production CI | PASS — run #241, Ubuntu + Windows, head `ef30bc0` |
| Native signed-review propagation | PASS — exact identity/value match only; conflicts fail closed |
| OFFICIAL native-release completeness guard | PASS — cannot publish below governed 8,924 floor |
| Production engine | V1 — intentionally unchanged |
| Configured publication mode | DRAFT |
| V2 DRAFT cutover | ENGINEERING COMPLETE; requires recorded human cutover approval |
| OFFICIAL data publication | BLOCKED on independent human proof + signed/curated coverage |

After approval only: set `configs/app.yml` `extraction.engine: v2`, run the governed
production smoke, and retain V1 as the rollback backend during the observation period.

The investigation sections below are retained as historical chronology and do not
override the current release-decision gates above.

## Remaining human-only gates

These are not extraction-engine defects and must not be manufactured by software.

- Independent MANUAL_QA issuer gate: **4 / 100** currently counts under the committed
  golden fixture. PIPELINE_SEEDED and MANUAL_OR_PRIOR do not satisfy this gate.
- OFFICIAL publication uses only APPROVED/CURATED native facts. The native OFFICIAL
  release view now has a hard 8,924 completeness floor; a thin signed subset cannot
  certify itself.
- A recorded human cutover approval is required before changing
  `configs/app.yml` from `extraction.engine: v1` to `v2`.
- V1 remains the rollback backend during the observation period.

The first two bullets govern **OFFICIAL data publication**. They do not invalidate a
governed V2 **DRAFT** production run, which may activate after engineering acceptance
and recorded cutover approval.

## First T25 holdout (retired)

```text
FAILED initially (entity-resolved recall 68.75%; 3 FN LITE; 2 critical wrong SFCL)
→ investigated (N02/N03)
→ LITE extraction defects fixed (F1 entity subtitle + F3 duration)
→ SFCL truth-label error corrected (Company values mislabeled Group)
→ rescored 1.0 on entity-resolved inspected facts (TP 16 / FN 0 / critical 0)
→ permanently retired from final holdout use
```

Do **not** present the repaired first holdout as final certification evidence.

## Final holdout path

```text
N16 identity locked (13 filings) — holdout_v2_identity_manifest.json
→ N17 blind truth pending
→ N18 scoring pending
```

## What passed (engineering / investigation)

| Gate | Result |
|---|---|
| T00–T10 investigation harness | DONE |
| T10 DEV source truth | DONE (entity-resolved recall 1.0) |
| F1 / F3 LITE fixes + regressions | DONE |
| SFCL PDF ownership + truth correction | DONE |
| G01 / G03 / G09 | KEEP |
| N08 gate diagnostics | DONE (G02/G04–G08 still UNTESTED) |
| N09 header diagnostic | H0 MEASURED only (H1/H2 not built) |
| Checklist 18 OCR packaging | DONE |
| Checklist 20 V2 publish path | DONE (opt-in `engine=v2`) |
| Engine default | V1 |

## Historical investigation gates retained for chronology

| Gate | Result |
|---|---|
| N17 / N18 new unseen holdout | PACKAGE READY / BLOCKED ON human blind gold |
| N11 clean-SHA locked-33 baseline | DONE (`2ff5d1f…`, deterministic) |
| N12 canonical artefact regen | DONE |
| N13 CI green | DONE — PR #35, Deterministic production checks run #238, Ubuntu + Windows |
| N14 current-universe V2 challenger | DONE fail-closed (3,748 vs 8,924; +64 vs prior; 43 OCR unavailable) |
| G02 / G04–G08 | UNTESTED vs source truth |
| H1 / H2 | not built |
| N20 Sept-10 exact replay | OPEN (artefacts missing) |
| T28 / T29 | BLOCKED ON ENGINEERING (+ OFFICIAL later) |

## Hard stops

- Do not promote V2 / lower 8924 / delete V1.
- Do not score N16 before blind truth.
- Do not reuse first T25 as final holdout.
- Do not claim OFFICIAL approval until a human approval record exists.
- Do not treat Sept-05 diagnostic as Sept-10 acceptance.

## Artefacts

- `docs/v2/VERIFIED_OPEN_WORK_AND_FINAL_ENGINEERING_PATH.md`
- `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`
- `docs/v2/EXTRACTION_INVESTIGATION_STATUS.md`
- `tests/v2/source_truth/holdout_v2_identity_manifest.json`
- `tests/v2/universe/t25_failed_holdout_freeze.json`
- `tests/v2/universe/n08_gate_experiment_summary.json`
- `tests/v2/universe/n09_header_bakeoff.json`
