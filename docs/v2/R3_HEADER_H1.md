# R3 — H1 Header Engine (V1 geometry adapter)

**Status:** R3.1 COMPLETE — BUILT / IMPROVED / **NOT PROMOTED**  
**Default production header engine:** **H0**  
**Production extraction:** `engine: v1` / floor `8924`

## What landed

- `v2/resolution/header_h1.py` — V1 `compile_header` adapted onto V2 statements
- `header_engine="H0"|"H1"` on bind + filing pipeline (default **H0**)
- R3.1: year-only columns complete from a **unique shared header DATE/day-month** phrase; comparison roles assigned after period completion; percent/note columns respected
- Rejects table-title/caption silent fills; no query-target copy

## Bake-off (post R3.1)

### LITE.N0000-2025-12-31

| Engine | entity | period | duration | comparison | SourceFacts | Group CURRENT TOP_LINE/OP/PAT |
|---|---:|---:|---:|---:|---:|---|
| H0 | 18/23 | 18 | 14 | 18 | **72** | yes |
| H1 | 8/23 | 16 | 8 | 16 | 40 | yes |

### SFCL.N0000-2025-12-31

| Engine | entity | period | SourceFacts |
|---|---:|---:|---:|
| H0 | 32/40 | 32 | **56** |
| H1 | 26/40 | 30 | **56** |

## Decision

```text
header_engine = H0 (keep)
replace_h0_with_h1 = false
```

H1 recovered from 0→40 LITE facts and matches SFCL fact count, but still trails H0 on LITE coverage/entity resolution. Recovery stop-condition: do not promote until H1 **beats** H0 without critical wrong facts.

## Next recovery step

**R4** — port V1 scoped `UnitEvidenceResolver` into V2 (cell-level ROW→COLUMN→TABLE→PAGE), while H1 remains challenger-only pending further header entity parity.

N17 blind adjudication remains parallel and independent.
