# N04 — Generalized root-cause classification (LITE + SFCL)

After N02/N03 CandidateTrace diagnosis. No issuer-specific patches.

## Families

| ID | Family | Evidence | Affects | Priority |
|---|---|---|---|---|
| F1 | **Header graph / column ownership** — entity-bearing statement subtitles dropped from heading-band context | N02 LITE: `Comprehensive Income - Group 31st December 2025` excluded (`_ACCOUNT_LINE` + year); all target columns `ENTITY_UNRESOLVED` → FN | LITE TOP_LINE / PAT / OPERATING_PROFIT | **P0 extract** |
| F2 | **Header graph / evidence propagation** — Company/Group banners resolve positionally but CandidateTrace `header_evidence` only shows statement title | N03 SFCL: banners correct; trace not auditable | Auditability; H0/H1/H2 bake-off | **P1** |
| F3 | **Duration ownership / merged quarter–YTD spans** | N02 LITE latent: truth cells get `duration_months=9` while adjacent col gets 3 | LITE after F1 fixed | **P0 after F1** |
| F4 | **Holdout truth authoring** (not V2 left/right swap) | N03 SFCL: Company-column values labeled GROUP; V2 matched PDF | T25 “critical wrong” count | **P0 truth correction** (done in items.jsonl) |

## Not first-failure for these cases

Page routing, statement/table/row reconstruction, concept matching, unit/scale, SourceFact admission after entity resolves (LITE never reached admission).

## Next engineering (N05–N06)

1. Permanent real-PDF regressions for LITE (expect GROUP SourceFacts once F1 fixed) and SFCL (COMPANY values or GROUP sibling values per corrected truth).
2. Generalized fix for F1: keep entity-bearing subtitles in heading context / entity banners without issuer constants.
3. Then duration span ownership (F3); header evidence propagation (F2) for H bake-off.
4. Do **not** reuse the failed T25 12-file set as final holdout.

## Artefacts

- `docs/v2/investigations/N02_LITE_TRACE.md`
- `docs/v2/investigations/N03_SFCL_TRACE.md`
- `tests/v2/universe/n02_lite_trace.json`
- `tests/v2/universe/n03_sfcl_trace.json`
