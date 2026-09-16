# SOURCE_VALIDATED_BASELINE (investigation)

Provisional source-validated target-fact baseline from blind PDF review.
**Not** a replacement for `min_draft_publishable = 8924`. **Not** certification.
**Not** the September-10 frozen universe. **Not** engineering completion.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.
Recovery: `docs/v2/NEXT_ENGINEERING_STEPS_AND_PROJECT_RECOVERY_PLAN.md`.

## Scope

| Split | Items | Evidence | Outcome |
|---|---|---|---|
| DEV (T10) | 40 | `items.jsonl` Reviewer `t10-blind-pdf-review` | Useful; entity-resolved recall 1.0 after GWP fix |
| HOLDOUT (T25) | 24 | Same file, Reviewer `t25-blind-pdf-review` | **FAILED** — recall 68.75%; 2 critical wrong |
| Full universe | — | Not adjudicated | — |

## Counts from items.jsonl

- REPORTED: 59
- AMBIGUOUS: 5
- NOT_REPORTED: 0 in this sample

## Scoring (V2 SourceFacts vs truth)

See:

- `tests/v2/universe/t10_score.json` (DEV)
- `tests/v2/universe/t25_holdout_score.json` (HOLDOUT — FAILED)
- `tests/v2/universe/t25_failed_holdout_freeze.json` (freeze after inspection)

Unlabeled REPORTED rows are G01 withheld, not value errors.
Publication gates are not applied to truth.

T25 failed cases (LITE FN; SFCL critical wrong) are promoted to DEV/regression evidence and **must not** be reused as the final unseen holdout.

## What this baseline is for

- Gate KEEP evidence (G01/G03/G09)
- Holdout milestone evaluation after rules frozen
- Future governed coverage floor redesign (only after a **passing** new holdout + full-universe evidence)

## What this baseline is not

- Plan §37 institutional gold completion
- Authority to lower 8924
- Authority to set `extraction.engine: v2`
- September-10 frozen-universe A/B substitute
- Proof that OFFICIAL review is the only remaining blocker
