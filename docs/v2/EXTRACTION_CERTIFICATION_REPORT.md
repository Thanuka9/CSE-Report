# V2 Extraction Certification Report

**Status: V2 DRAFT CUTOVER APPROVED — OFFICIAL PUBLICATION NOT CERTIFIED**

Production extraction is **V2** (`configs/app.yml` `extraction.engine: v2`).
Publication remains **DRAFT**. Coverage floor remains **8924**.
V1 remains the rollback backend. Do not delete V1.
Contract: `docs/v2/HYBRID_RELEASE_CONTRACT.md`.

OFFICIAL data publication is **NOT CERTIFIED**.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Branch: `v2/extraction-investigation`.

## Two finish lines

**V2 DRAFT production cutover:** approved 2026-09-22. Engine is `v2`.
Final production smoke: `reports/v2_production_smoke/smoke_summary.json`.

**OFFICIAL data publication:** NOT YET HUMAN-CERTIFIED. Independent MANUAL_QA
is still 4 / 100. The 2026-09-23 AI/evidence QA package audited all 100
benchmark issuers (95 PASS / 5 REVIEW) plus the 281-issuer universe
(260 PASS / 21 REVIEW). That package is a reviewer dossier, not MANUAL_QA.
PIPELINE_SEEDED / UNADJUDICATED rows must not be relabeled. DRAFT production
is not blocked on the old gold floor.

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
| OFFICIAL publication | NOT CERTIFIED |

## What passed (engineering)

| Gate | Result |
|---|---|
| Hybrid 829 same-input parity | PASSED |
| Unexplained V1 TARGET losses | 0 |
| Remote CI Ubuntu + Windows | GREEN (reported) |
| Engine default | V2 (DRAFT cutover) |
| Release mode | DRAFT |
| Coverage floor | 8924 unchanged |
| V1 rollback | retained |

## Hard stops

- Do not set `release_mode: OFFICIAL` / lower 8924 / delete V1.
- Do not invent MANUAL_QA / bulk-relabel PIPELINE_SEEDED.
- Do not treat DRAFT publishable count as OFFICIAL workbook completeness.
- Do not score N16 as unseen gold; do not reuse first T25 as final holdout.
