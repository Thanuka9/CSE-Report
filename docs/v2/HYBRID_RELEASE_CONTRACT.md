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
The 2026-09-23 AI/evidence QA package and the 2026-09-28 900-row
`CSE_100_Issuer_Manual_QA_Final` CSV are reviewer dossiers, not human gold.
The final CSV reviewer is `OPENAI_ASSISTANT_MANUAL_SOURCE_REVIEW`. That packet
was not imported into `golden_financial_facts.json`.

| Measure | Result |
|---|---|
| 100-issuer evidence precheck | 95 PASS / 5 REVIEW |
| 281-issuer universe precheck | 260 PASS / 21 REVIEW |
| Sept-28 source-review rows | 900 COMPLETED; 676 PASS / 224 FAIL |
| FAIL backlog hybrid V2 rerun | 56 recovered; 10 true ambiguities; 21 OCR; 137 withheld |
| Human sign-off set | `CSE_100_Issuer_FAIL_Backlog_Signoff.xlsx` sheet `Signoff_Exceptions` (10 rows) |
| Existing MANUAL_QA issuers | 4 |
| Independent human MANUAL_QA still required | 96 |

Dossier: `reports/gold_gate/AI_QA_DOSSIER.md`.
Use `CSE_100_Issuer_FAIL_Backlog_Signoff.xlsx` / `manual_qa_signoff_exceptions.csv`
for the remaining human decisions. Do not re-inspect the 56 recovered rows or
the 137 unlabeled-entity / admission withholds before development continues.

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
