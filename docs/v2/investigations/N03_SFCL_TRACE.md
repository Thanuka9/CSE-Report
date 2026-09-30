# N03 — SFCL.N0000 (Senkadagala Finance) entity/value ownership

**Status:** DIAGNOSED (no engine patch in this ticket)  
**Branch:** `v2/extraction-investigation`  
**Constraints honored:** engine remains V1 default; floor 8924; no issuer-specific hardcodes; V1 not used as truth  
**PDF:** `data/raw/filings/SENKADAGALA_FINANCE_COMPANY_PLC/2025-12-31_441_1770976920300.pdf`  
**SHA256:** `3095172f49c02bacff501b3b320e5e2a60ac8d321361a298ede007f13d6f4285`  
**Filing:** `SFCL.N0000-2025-12-31` · issuer type `FINANCE_COMPANY` · page 2 income statement

## Blind truth (holdout items)

| Metric | Entity | Value | Duration | Role |
|---|---|---|---|---|
| TOP_LINE | GROUP | 2,572,716,568 | 3M | CURRENT |
| PAT | GROUP | 344,406,148 | 3M | CURRENT |

Source: `tests/v2/universe/t25_holdout_score.json` + `scripts/v2_write_t25_holdout_items.py`.

## T25 score rows

Both metrics scored `VALUE_OR_ENTITY_MISMATCH`.

- TOP_LINE truth `2572716568` / GROUP — V2 values include that number under **COMPANY**, and a different GROUP current `2664529998`.
- PAT truth `344406148` / GROUP — V2 values include that number under **COMPANY**, and a different GROUP current `390951093`.

## PDF source header (page 2)

Native text (PyMuPDF / pdfplumber agree):

```text
Statement of profit or loss
Company Group
For the three month period ended 31 December 2025 2024 Change 2025 2024 Change
Rs. Rs. % Rs. Rs. %
Gross income 2,572,716,568 2,652,539,436 (3) 2,664,529,998 2,748,482,811 (3)
...
Profit for the period 344,406,148 599,564,750 (43) 390,951,093 657,143,868 (41)
```

Column layout implied by source:

| Block | 2025 CURRENT | 2024 COMPARATIVE | Change % |
|---|---|---|---|
| **Company** | 2,572,716,568 / 344,406,148 | 2,652,539,436 / 599,564,750 | (3)/(43) |
| **Group** | 2,664,529,998 / 390,951,093 | 2,748,482,811 / 657,143,868 | (3)/(41) |

Fee-and-commission rows reinforce left=Company / right=Group (Company ~20M vs Group ~106M).

## V2 production vs truth

Run artifact: `outputs/n03_sfcl/` (`summary.json`, `relevant_traces.json`, `statements_columns.json`, `candidate_trace.parquet`).

| Metric | Blind truth | V2 production selected | Truth-value cell in V2 |
|---|---|---|---|
| TOP_LINE | GROUP **2572716568** | GROUP **2664529998** (c03) | COMPANY **2572716568** (c00), `ENTITY_SCOPE_MISMATCH` |
| PAT | GROUP **344406148** | GROUP **390951093** (c03) | COMPANY **344406148** (c00), `ENTITY_SCOPE_MISMATCH` |

Duration/period/role on the selected cells: `duration_months=3`, `period_end=2025-12-31`, `comparison_role=CURRENT`. Concept match OK (`Gross income` → TOP_LINE, `Profit for the period` → PAT).

## CandidateTrace / column_context evidence

### Entity banners (geometry)

From `column_context._entity_banners` on `p0002-INCOME_STATEMENT`:

- `Company` @ x≈309.05 → `COMPANY`
- `Group` @ x≈476.14 → `GROUP`

`_entity_for_position` with 4 monetary columns + 2 unique scopes uses midpoint split → c00/c01 COMPANY, c03/c04 GROUP. Matches PDF.

### Header evidence quality gap

Bound columns store `entity_evidence` / `period_evidence` / … as `statement.source_refs[:1]` only (`"Statement of profit or loss"`), **not** the `Company Group` banner line that is present later in `statement.source_refs`.

CandidateTrace therefore shows:

```text
header_evidence: "Statement of profit or loss | Statement of profit or loss"
```

for **every** monetary column — including both Company and Group. Ownership is therefore not auditable from trace `header_evidence` alone, even though positional banner logic assigned scopes correctly.

`header_path` / per-column header cells are empty on the reconstructed statement (no HeaderGraph path persisted).

### Other ownership checks

| Check | Result |
|---|---|
| Group / Company | Banner + midpoint: left Company, right Group (matches PDF) |
| Current / comparative | Years 2025/2024 from header blob; roles CURRENT/COMPARATIVE |
| 3M / cumulative | `For the three month period` → duration 3 on page-2 statement |
| Merged header propagation | Entity line is a single text run `Company Group`; scopes come from regex hits + x-order, not true span→column paths |
| Date ownership | Date banners found only one calendar date; period still filled via blob year tokens |
| Duplicate identity | Page-3 OCI restates PAT; duplicate GROUP PAT marked `DUPLICATE_METRIC` |
| Conflict resolution | No identity conflict on the selected GROUP quarter cells |
| Production selector | Prefers expected GROUP; rejects truth-value cells with `ENTITY_SCOPE_MISMATCH` |

## First failure stage (vs blind-truth identity)

Blind truth asks for **GROUP + Company-column value**. V2 admits that value as a SourceFact with `first_failure_stage=NONE`, but under **COMPANY**. Production then rejects it and selects the PDF Group sibling.

| Metric | First failure stage | Reason / status |
|---|---|---|
| TOP_LINE | **entity ownership** | Truth value on c00 tagged COMPANY; production reason `ENTITY_SCOPE_MISMATCH`; selected c03 GROUP=2664529998 |
| PAT | **entity ownership** | Truth value on c00 tagged COMPANY; production reason `ENTITY_SCOPE_MISMATCH`; selected c03 GROUP=390951093 |

Not failed at: page routing, statement/table/row reconstruction, concept matching, duration, comparison-role, unit/scale, SourceFact admission, or publication (selected facts are ELIGIBLE).

## PDF cross-check (critical)

Against the filing header text, **V2’s Company/Group value ownership matches the PDF**. The holdout items label the **Company** gross-income and PAT figures as **GROUP**:

- Item evidence `"Group Gross income 2,572,716,568"` contradicts the page-2 `Company | Group` band.
- Correct Group quarter current cells per PDF are TOP_LINE `2,664,529,998` and PAT `390,951,093` — exactly what V2 production selected.

Therefore the T25 “2 critical wrong facts” for SFCL are **not** explained by a V2 left/right entity swap on this filing. They are explained by **holdout truth entity mislabel** (Company cells authored as GROUP), compounded by weak CandidateTrace header evidence that hides the real Company/Group banners.

## Generalized root-cause family

1. **Primary for T25 SFCL mismatches:** holdout **source-truth authoring** (entity_scope on the wrong column relative to explicit `Company Group` headers). Fix path: correct HOLDOUT items to either (a) COMPANY + current values, or (b) keep GROUP but use PDF Group values `2664529998` / `390951093`. Re-score; do not treat this pair as an extraction defect until truth matches the PDF.
2. **Engineering family still justified (H0/H1/H2):** **header graph / column ownership evidence propagation** — entity banners exist, but column `entity_evidence` and CandidateTrace `header_evidence` do not retain Company/Group tokens or per-column header paths. Merged `Company Group` is not modeled as span→column ownership. That is the generalized defect family to pursue even though SFCL’s positional assignment happened to match the PDF.

## Evidence paths

- PDF: `data/raw/filings/SENKADAGALA_FINANCE_COMPANY_PLC/2025-12-31_441_1770976920300.pdf`
- T25 score: `tests/v2/universe/t25_holdout_score.json`
- Holdout identity: `tests/v2/source_truth/holdout_manifest.json`
- Holdout item authoring: `scripts/v2_write_t25_holdout_items.py` (SFCL TOP_LINE/PAT)
- Run dump: `outputs/n03_sfcl/summary.json`, `relevant_traces.json`, `statements_columns.json`, `candidate_trace.parquet`
- Compact fixture: `tests/v2/universe/n03_sfcl_trace.json`
- Column binder: `src/cse_financial_etl/v2/resolution/column_context.py` (`_entity_banners`, `_entity_for_position`, evidence `source_refs[:1]`)
