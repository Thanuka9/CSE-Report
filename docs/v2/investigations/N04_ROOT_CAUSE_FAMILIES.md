# N04 — Generalized root-cause classification (LITE + SFCL)

After N02/N03 CandidateTrace diagnosis and N06 F1 fix.

## Families

| ID | Family | Status | Evidence | Priority |
|---|---|---|---|---|
| F1 | **Header graph / column ownership** — entity-bearing statement subtitles dropped from heading-band context | **FIX LANDED** (`column_context._is_entity_bearing_subtitle`) | N02 LITE; regressions `test_lite_group_header_ownership.py` | Done |
| F2 | **Header graph / evidence propagation** — CandidateTrace should retain Company/Group banner text | **PARTIAL** — entity_evidence now prefers banner texts | N03 SFCL | P1 |
| F3 | **Duration ownership / merged quarter–YTD spans** | **OPEN** | N02 LITE latent: quarter cells can still be labeled 9M | P0 next |
| F4 | **Holdout truth authoring** | **CORRECTED** | N03 SFCL Company values mislabeled GROUP → COMPANY | Done |

## N07 score rerun (dirty SHA; inspected holdout)

| Split | TP | FN | Critical wrong | Entity-resolved recall |
|---|---|---|---|---|
| DEV (T10) | 31 | 0 | 0 | 1.0 |
| HOLDOUT (T25, after F1 + SFCL truth fix) | 16 | 0 | 0 | 1.0 |

**Not certification.** Failed T25 set was inspected and partially corrected; do **not** reuse as final unseen holdout (recovery plan §5/§14).

## Artefacts

- `docs/v2/investigations/N02_LITE_TRACE.md`
- `docs/v2/investigations/N03_SFCL_TRACE.md`
- `tests/v2/universe/n02_lite_trace.json`
- `tests/v2/universe/n03_sfcl_trace.json`
- `tests/v2/regression/test_lite_group_header_ownership.py`
- `tests/v2/regression/test_sfcl_company_group_ownership.py`
- `tests/v2/universe/t10_score.json` / `t25_holdout_score.json` (N07 rerun)
