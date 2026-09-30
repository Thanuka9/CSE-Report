# R5 — Statement / Table Structural Differential

**Status:** MEASURED (diagnostic) — ports not yet selected  
**Evidence:** `tests/v2/universe/r5_structural_differential.json`  
**Harness:** `scripts/v2_structural_differential.py`

## Spot check

| Filing | V1 regions | V2 regions | V1 tables | V2 stmts | V1 cells | V2 cells |
|---|---:|---:|---:|---:|---:|---:|
| LITE 2025-12-31 | 13 | 7 | 15 | 5 | 782 | 409 |
| SFCL 2025-12-31 | 10 | 10 | 21 | 8 | 2073 | 734 |

## Interpretation

- Statement **page discovery** is closer on SFCL (10=10); LITE V2 under-detects regions (7 vs 13).
- V1 table reconstruction yields more tables/cells — candidate substrate for BEST-OF ports (continuation, multi-table pages).
- Do **not** blindly merge V1 region_detector (KEEP_V2 heading-band discipline from R1 matrix). Prefer porting evidenced continuation + missed statement pages with SourceRef.

## Decision

```text
No automatic port in this step.
Ranked follow-ups:
1) missed income/continuation pages on LITE-like layouts
2) denser table/cell recovery where V2 rows collapse
3) then re-run H1/U1 bake-offs
```

## Hard stops

- No issuer-specific page lists
- No V2 production promotion
- Floor stays 8924
