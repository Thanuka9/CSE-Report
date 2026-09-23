# Hybrid V2 Release Contract

There are two finish lines.

## 1. V2 DRAFT production cutover — APPROVED 2026-09-22

Recorded human cutover approval: **APPROVED**.

Production extraction is now:

```yaml
extraction:
  engine: v2
publication:
  release_mode: DRAFT
```

V1 remains the rollback backend (`--engine v1`). V1 is not deleted.
Cutover `ready=True` (institutional gold / V1 deletion) is still false.

Extraction proof remains the SHA-pinned 829 same-input hybrid parity:

- 829/829 files
- 3,183 V1 TARGET facts: 3,048 preserved, 135 quarantined, **0 unexplained losses**
- Conflicts quarantined, not published
- Coverage floor remains **8,924**

N17/N18 stay superseded as a pre-cutover extraction holdout and remain required
before deleting V1 or certifying V2-native extraction.

## 2. OFFICIAL data publication — NOT YET HUMAN-CERTIFIED

`validate_golden()` counts only `MANUAL_QA`. Current committed fixture:

- MANUAL_QA: 4
- MANUAL_OR_PRIOR: 3
- PIPELINE_SEEDED: 93

Do **not** relabel `UNADJUDICATED` / `PIPELINE_SEEDED` as `MANUAL_QA`.
The 2026-09-23 AI/evidence QA package is a reviewer dossier, not human gold.

| Measure | Result |
|---|---|
| 100-issuer evidence precheck | 95 PASS / 5 REVIEW |
| 281-issuer universe precheck | 260 PASS / 21 REVIEW |
| Existing MANUAL_QA issuers | 4 |
| Independent human MANUAL_QA still required | 96 |

Dossier: `reports/gold_gate/AI_QA_DOSSIER.md` and
`reports/gold_gate/CSE_V2_AI_QA_100plus_Production_Gate.xlsx`.
Use the Priority Review Queue for targeted source-PDF sign-off rather than
redoing the engineering exercise.

DRAFT production is **not** blocked on `min_gold_issuers: 100`. Those floors
fire only when `release_mode` is OFFICIAL.

OFFICIAL also requires enough APPROVED/CURATED native facts to satisfy
`min_official_publishable: 8924`. Signed review must already be on native
`SourceFact` / `DerivedFact` objects before the V2 workbook is rendered.

## Non-negotiable

- Do not rewrite extractors for cutover.
- Do not roll V2 DRAFT back to V1 on this QA evidence.
- Do not block DRAFT production on the old gold requirement.
- Do not set `release_mode: OFFICIAL` until 100 MANUAL_QA issuers and the
  8,924 APPROVED/CURATED floor are actually met.
- Do not invent gold.
- Do not lower 8,924.
- Do not delete V1.
