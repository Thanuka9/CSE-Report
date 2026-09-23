# N02 — LITE.N0000 CandidateTrace diagnosis

**Status:** DIAGNOSED (not fixed)  
**Branch:** `v2/extraction-investigation`  
**Constraint check:** production `extraction.engine` remains `v1`; no config/engine change; no issuer-specific constants; V1 not used as truth.

## Identity

| Field | Value |
| --- | --- |
| Issuer | `LITE.N0000` / LAXAPANA PLC |
| Filing | `LITE.N0000-2025-12-31` |
| PDF | `data/raw/filings/LAXAPANA_PLC/2025-12-31_498_1770114354483.pdf` |
| pdf_sha256 | `20151678333c62bbb416d9dfb8bdd2e1def27a181d38fc152be0ffbcdc1845f4` |
| Blind truth | `tests/v2/source_truth/items.jsonl` (split=HOLDOUT) |
| Holdout score | `tests/v2/universe/t25_holdout_score.json` (3× FN) |

## How this run was produced

Holdout scoring path (`scripts/v2_score_t10.py` → `collect_holdout_v2_facts`) runs `read_document` + `run_filing_pipeline` from `holdout_manifest.json` local paths. For N02, the same pipeline was invoked for this PDF only with CandidateTrace persistence:

```text
run_pdf_pipeline(
  pdf=data/raw/filings/LAXAPANA_PLC/2025-12-31_498_1770114354483.pdf,
  issuer_id=LITE.N0000,
  filing_version_id=LITE.N0000-2025-12-31,
  issuer_name=LAXAPANA PLC,
  issuer_type=GENERAL,
  candidate_trace_path=outputs/v2_n02_lite/candidate_trace.parquet,
)
```

Artefacts:

- `outputs/v2_n02_lite/candidate_trace.parquet` (365 candidates)
- `tests/v2/universe/n02_lite_trace.json` (compact target-cell extract)

Run summary from trace: statements detected on pages 5–9; page 5 income statement reconstructed; target cells exist as candidates; **no SourceFact** created for the three blind REPORTED metrics.

## Blind source truth (page 5, Group quarter CURRENT)

| Metric | Raw label | Raw value | Normalized | Entity | Duration |
| --- | --- | --- | --- | --- | --- |
| TOP_LINE | Revenue | 889,239 | 889239000 | GROUP | 3 |
| OPERATING_PROFIT | Profit from Operating Activities | 156,042 | 156042000 | GROUP | 3 |
| PAT | Net Profit for the Period | 79,190 | 79190000 | GROUP | 3 |

Scale truth: `Rs.'000` → ×1000.

## Exact CandidateTrace rows (target cells)

All three target numerics are present on **page 5**, concept-resolved, unit-resolved (scale 1000), period-resolved (`2025-12-31`), comparison CURRENT — then blocked before SourceFact admission.

### TOP_LINE

| Field | Trace evidence |
| --- | --- |
| source page | 5 |
| row label | Revenue |
| source value | `889,239` (parsed `889239`) |
| candidate ID | `p0005-INCOME_STATEMENT-r0002-p0005-INCOME_STATEMENT-c00-cand` |
| concept | RESOLVED → `TOP_LINE` (EXACT_ALIAS “Revenue”) |
| first failure stage | **entity ownership** (`ENTITY_UNRESOLVED`) |
| reason code | `ENTITY_NOT_RESOLVED` |
| SourceFact | false (`production_selection_reason=SOURCE_FACT_NOT_CREATED`) |
| header_evidence on trace | `Statement of Profit or Loss and Other` only |
| secondary (not first) | `duration_months=9` on this cell (truth is 3M quarter) |

### OPERATING_PROFIT

| Field | Trace evidence |
| --- | --- |
| source page | 5 |
| row label | Profit from Operating Activities |
| source value | `156,042` (parsed `156042`) |
| candidate ID | `p0005-INCOME_STATEMENT-r0008-p0005-INCOME_STATEMENT-c00-cand` |
| concept | RESOLVED → `OPERATING_PROFIT` |
| first failure stage | **entity ownership** (`ENTITY_UNRESOLVED`) |
| reason code | `ENTITY_NOT_RESOLVED` |
| SourceFact | false |
| secondary (not first) | `duration_months=9` (truth 3M) |

### PAT

| Field | Trace evidence |
| --- | --- |
| source page | 5 |
| row label | Net Profit for the Period |
| source value | `79,190` (parsed `79190`) |
| candidate ID | `p0005-INCOME_STATEMENT-r0012-p0005-INCOME_STATEMENT-c00-cand` |
| concept | RESOLVED → `PAT` |
| first failure stage | **entity ownership** (`ENTITY_UNRESOLVED`) |
| reason code | `ENTITY_NOT_RESOLVED` |
| SourceFact | false |
| secondary (not first) | `duration_months=9` (truth 3M) |

### Stages that did **not** fail first

For all three targets, CandidateTrace shows:

- page routing: `NATIVE`
- statement detection: `DETECTED` (`INCOME_STATEMENT`)
- table detection: `DETECTED`
- table reconstruction: `RECONSTRUCTED`
- row reconstruction: `RECONSTRUCTED`
- concept matching: `RESOLVED`
- period / comparison / unit: resolved on the candidate
- SourceFact admission / publication / production selection: never reached (blocked by entity)

## Root-cause hypothesis (trace-grounded)

Page 5 native line text includes an explicit entity subtitle:

```text
Comprehensive Income - Group 31st December 2025
```

In-run column context for `p0005-INCOME_STATEMENT` shows:

- every monetary column `entity_scope=None`, `entity_evidence=[]`
- `context_blob(...).find("group")` → absent
- `_entity_banners(...)` → `[]`

Diagnostic probe of `_heading_context_lines` on page 5:

| Line | kept in heading band? | Why |
| --- | --- | --- |
| `Statement of Profit or Loss and Other` | yes | matches `_STATEMENT_TITLE` |
| `Comprehensive Income - Group 31st December 2025` | **no** | `_ACCOUNT_LINE` hits “Income”, token `2025` parses numeric, not `_STATEMENT_TITLE` → dropped as account-like heading-band line |

Therefore Group never enters the header/context graph used by `bind_column_context`, columns stay entity-unresolved, `source_admission_failure` returns `ENTITY_UNRESOLVED`, and T25 scores FN.

### Latent next failure (same family; not first)

Duration banners resolved as roughly `(x=76→9), (x=262→3), (x=439→9), (x=511→9)`, so column `c00` (holding the blind quarter values 889,239 / 156,042 / 79,190) is labeled `duration_months=9` while `c01` gets `3`. After entity ownership is fixed, **duration ownership** from merged quarter/YTD header spans is the likely next defect on these same cells.

## One generalized root-cause family

**Header graph / column ownership** — page-level entity subtitles (e.g. “Comprehensive Income - Group …”) are excluded from heading-band context when they contain account-ish tokens plus a year, so entity scope never binds to reconstructed columns.

Not an issuer-specific patch. Fix direction (for later engineering, not done here): preserve entity-bearing statement subtitles in heading context / entity banners without copying query targets or hard-coding Laxapana values.

## Suggested permanent regression path (after fix)

- Promote LITE TOP_LINE / PAT / OPERATING_PROFIT into DEV/regression per recovery plan §5
- Real-PDF regression asserting SourceFact admission with `entity_scope=GROUP` for the three page-5 cells (and separately duration=3 once entity is fixed)
- Candidate path: `tests/v2/regression/test_lite_group_header_ownership.py` (not created in N02)

## First-failure-stage one-liners

- TOP_LINE → entity ownership (`ENTITY_UNRESOLVED` / `ENTITY_NOT_RESOLVED`)
- PAT → entity ownership (`ENTITY_UNRESOLVED` / `ENTITY_NOT_RESOLVED`)
- OPERATING_PROFIT → entity ownership (`ENTITY_UNRESOLVED` / `ENTITY_NOT_RESOLVED`)
