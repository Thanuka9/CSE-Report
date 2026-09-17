# R4 — Scoped UnitEvidenceResolver (U1)

**Status:** BUILT / MEASURED / **NOT PROMOTED**  
**Default unit engine:** **U0** (column `parse_unit`)  
**Production extraction:** `engine: v1` / floor `8924`

## What landed

- `v2/resolution/unit_u1.py` — V1 `resolve_unit` ROW→COLUMN→TABLE→PAGE on V2 candidates
- `unit_engine="U0"|"U1"` on `build_candidates` / `run_filing_pipeline` / `run_pdf_pipeline`
- Unit tests: `tests/v2/unit/test_unit_resolver_u1.py`
- Per-share rows do not inherit statement `Rs '000` scale

## Bake-off (LITE)

| Engine | SourceFacts | per_share candidates | per_share×thousands |
|---|---:|---:|---:|
| U0 | 72 | 0 | 0 |
| U1 | 72 | 12 | 0 |

Same publishable/source fact count on LITE; U1 correctly dimensions EPS/NAVPS-style rows. Not promoted solely on parity — needs locked-33 + broader bake-off before replacing U0.

## Decision

```text
unit_engine = U0 (keep default)
replace_u0_with_u1 = false (for now)
```

## Next

R5 structural differential shows V1 recovers more tables/cells — prioritize generalized table/continuation ports where V2 under-segments, then remeasure U1/H1.
