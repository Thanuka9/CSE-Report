# V2 Release Contract

## ReleaseContext (Day One)

```text
generation_id
run_id
mode: DRAFT | OFFICIAL
code_sha
policy_hash
source_snapshot_id
```

Pass it explicitly into publication, release-view, workbook reconciliation, and (later) rendering.

Forbidden as V2 design: `set_release_mode(...)` / process-global `_release_mode`.

## Publication cells

Workbook financial cells contain a numeric value or blank/null.

Never write `ENTITY_NOT_RESOLVED`, `REVIEW_REQUIRED`, `PERIOD_NOT_RESOLVED`, or other status strings into numeric fields. Status belongs on dedicated sheets.

## Reconciliation

```text
eligible release facts
→ facts selected for pivot (exclusions explicit)
→ expected displayed fact instances
→ actual numeric workbook cells
```

Unexpected mismatch raises `WORKBOOK_RECONCILIATION_FAILED` and the workbook must not be released.

## Coverage floors

`configs/coverage_baseline.yml` may stay unchanged or rise.

It may not fall without `ACKNOWLEDGED_REGRESSION` plus the required governance metadata.

Historical lock: `min_draft_publishable = 8924`. `2,394` is not an acceptable production floor.
