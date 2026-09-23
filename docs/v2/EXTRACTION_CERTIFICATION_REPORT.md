# V2 Extraction Certification Report

**Status: V2 DRAFT CUTOVER APPROVED — OFFICIAL PUBLICATION NOT YET HUMAN-CERTIFIED**

Production extraction is **V2** (`configs/app.yml` `extraction.engine: v2`).
Publication remains **DRAFT**. Coverage floor remains **8924**.
V1 remains the rollback backend. Do not delete V1.
Contract: `docs/v2/HYBRID_RELEASE_CONTRACT.md`.

Remote CI run #241 passed on Ubuntu and Windows at
`ef30bc0bda4815eaea74ed231b4f0f44617dda92`, including the fail-closed
native-governance propagation and OFFICIAL native-release completeness tests.

OFFICIAL data publication is **NOT YET HUMAN-CERTIFIED**.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.

## Two finish lines

**V2 DRAFT production cutover:** approved 2026-09-22. Engine is `v2`.
Final production smoke: `reports/v2_production_smoke/smoke_summary.json`.
No software rollback to V1 is indicated.

**OFFICIAL data publication:** NOT YET HUMAN-CERTIFIED. Independent MANUAL_QA
is still 4 / 100. The 2026-09-23 AI/evidence QA package audited all 100
benchmark issuers (95 PASS / 5 REVIEW) plus the 281-issuer universe
(260 PASS / 21 REVIEW). That package is a reviewer dossier, not MANUAL_QA.
PIPELINE_SEEDED / UNADJUDICATED rows must not be relabeled. DRAFT production
is not blocked on the old gold floor.

## Current release decision

| Gate | Result |
|---|---|
| 829 pinned-file hybrid parity | PASS — 0 unexplained V1 TARGET losses/mismatches |
| Unresolved V1/V2 conflicts | QUARANTINED |
| Coverage floor | 8,924 unchanged |
| Remote deterministic production CI | PASS — run #241, Ubuntu + Windows, head `ef30bc0` |
| Native signed-review propagation | PASS — exact identity/value match only; conflicts fail closed |
| OFFICIAL native-release completeness guard | PASS — cannot publish below governed 8,924 floor |
| Production engine | V2 (DRAFT cutover) |
| Configured publication mode | DRAFT |
| V2 DRAFT cutover | APPROVED 2026-09-22 |
| OFFICIAL data publication | NOT YET HUMAN-CERTIFIED |

The investigation sections below are retained as historical chronology and do not
override the current release-decision gates above.

## Remaining human-only gates

These are not extraction-engine defects and must not be manufactured by software.

- Independent MANUAL_QA issuer gate: **4 / 100** currently counts under the committed
  golden fixture. PIPELINE_SEEDED, MANUAL_OR_PRIOR, and AI_QA_PRECHECK_PASS do not
  satisfy this gate. Reviewer dossier: `reports/gold_gate/AI_QA_DOSSIER.md`.
- OFFICIAL publication uses only APPROVED/CURATED native facts. The native OFFICIAL
  release view now has a hard 8,924 completeness floor; a thin signed subset cannot
  certify itself.
- V1 remains the rollback backend during the observation period.

The first two bullets govern **OFFICIAL data publication**. They do not invalidate
V2 **DRAFT** production.

## Extraction proof (complete)

```text
829/829 hybrid parity
3,183 V1 TARGET: 3,048 preserved, 135 quarantined, 0 unexplained
Conflicts quarantined
V1 rollback backend retained
```

## Holdout contract

N16 identity (13/13) remains the identity-preservation check.

**N17 blind truth / N18 scoring are superseded as a pre-cutover extraction
requirement** because production `engine=v2` is the V1-baseline hybrid union,
already measured on the full SHA-pinned 829 cohort. They are **not** deleted:
they remain required before deleting V1, ending the observation period, or
claiming V2-native extraction is certified. Package:
`docs/v2/N17_BLIND_ADJUDICATION.md`.

## Still open before OFFICIAL publication

| Gate | Result |
|---|---|
| Native V2 signed-review propagation | PASSED |
| OFFICIAL output completeness (`min_official_publishable: 8924`) | CODE GATE; not met until enough APPROVED/CURATED facts exist |
| 100 MANUAL_QA issuers | 4 of 100 human-signed; AI QA dossier in `reports/gold_gate/` |
| V2 DRAFT production smoke | PASSED 6/6 PDFs |
| Recorded DRAFT cutover approval | APPROVED 2026-09-22; `engine: v2` |
| OFFICIAL publication | NOT YET HUMAN-CERTIFIED |

## What passed (engineering)

| Gate | Result |
|---|---|
| Hybrid 829 same-input parity | PASSED |
| Unexplained V1 TARGET losses | 0 |
| Remote CI Ubuntu + Windows | GREEN (run #241) |
| Engine default | V2 (DRAFT cutover) |
| Release mode | DRAFT |
| Coverage floor | 8924 unchanged |
| V1 rollback | retained |

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

- Do not set `release_mode: OFFICIAL` / lower 8924 / delete V1.
- Do not invent MANUAL_QA / bulk-relabel PIPELINE_SEEDED or UNADJUDICATED.
- Do not treat DRAFT publishable count as OFFICIAL workbook completeness.
- Do not roll V2 DRAFT back to V1 on the 2026-09-23 AI QA evidence.
- Do not score N16 as unseen gold; do not reuse first T25 as final holdout.
- Do not treat Sept-05 diagnostic as Sept-10 acceptance.

## Artefacts

- `docs/v2/HYBRID_RELEASE_CONTRACT.md`
- `reports/gold_gate/AI_QA_DOSSIER.md`
- `docs/v2/VERIFIED_OPEN_WORK_AND_FINAL_ENGINEERING_PATH.md`
- `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`
- `docs/v2/EXTRACTION_INVESTIGATION_STATUS.md`
- `tests/v2/source_truth/holdout_v2_identity_manifest.json`
- `tests/v2/universe/t25_failed_holdout_freeze.json`
- `tests/v2/universe/n08_gate_experiment_summary.json`
- `tests/v2/universe/n09_header_bakeoff.json`
