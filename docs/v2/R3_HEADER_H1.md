# R3 — H1 Header Engine (V1 geometry adapter)

**Status:** BUILT / MEASURED / **NOT PROMOTED**  
**Default production header engine:** **H0** (`bind_column_context` default)  
**Production extraction:** `engine: v1` / floor `8924`

## What landed

- `v2/resolution/header_h1.py` — adapts V1 `compile_header` onto V2 `CanonicalStatement`
- `header_engine="H0"|"H1"` on `bind_column_context` and `run_filing_pipeline`
- Bake-off emits both `h0` and `h1` metrics (`pipeline_bakeoff`)
- Unit tests: `tests/v2/unit/test_header_h1_bakeoff.py`
- Rejects table-title/caption silent fills; does not copy query-target metadata

## Bake-off signal (LITE real PDF)

| Engine | entity_resolved | period_resolved | duration_resolved | SourceFacts |
|---|---:|---:|---:|---:|
| H0 | 18/23 | 18 | 14 | 72 |
| H1 | 8/23 | 9 | 8 | 0 |

H1 does **not** beat H0. Stop-condition from recovery strategy applies: do not promote.

## Hard stops

- Do not set H1 as default until it beats H0 on DEV + LITE/SFCL + locked-33 resolution rates without critical wrong facts.
- Do not invent clean-sheet H2.
- Do not lower 8924 / promote V2 production engine.

## Next (R3.1)

Improve H1 period/date leaf binding on V2 reconstructed column geometry (income statements currently resolve entity/duration but miss period → admission fails). Re-run H0 vs H1 on LITE/SFCL + locked-33 before any promotion decision.
