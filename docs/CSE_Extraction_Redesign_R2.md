# CSE Quarterly Financial Data Platform
## Extraction Redesign Specification — Revision 2 / Implementation Baseline
### Statement Compiler, Diverse Structural Readings, Bounded Constraint Resolution and Governed Publication

**Status:** Frozen implementation baseline, Revision 2 — implementation and independent acceptance pending  
**Supersedes:** Revision 1 and `CSE_ETL_Final_Extraction_Redesign_Specification.md` (including the uploaded `(1)` copy).  
**Revision 2 changes:** Align Resolver C terminology in the module structure, production logging and coding-agent instruction.  
**Scope:** Redesign and replace the current extraction core only; retain the existing CSE discovery/download/storage/export/validation framework unless explicitly changed below.  
**Environment:** Python, local Windows/VS Code, CPU-only (~16 GB baseline), no paid CSE account, no database, no LLM/SLM or generative VLM inference, no external AI API, no production self-learning.

---

# 1. Purpose

The current extraction layer is too template-sensitive and too willing to stop at labels such as:

- `NOT_FOUND_BY_PARSER`
- `VALUE_CONTEXT_UNRESOLVED`
- `UNIT_NOT_RESOLVED`
- `CUMULATIVE_ONLY`
- `LOW_CERTAINTY`
- `ENTITY_NOT_RESOLVED`
- `COLUMN_AMBIGUOUS`

The problem is not primarily PDF access. The reviewed run demonstrates that successful PDF acquisition can coexist with serious context-selection failures. Support both native and scanned PDFs and measure reconstruction fidelity. The main demonstrated problem is **financial-statement interpretation**.

The new extraction system must therefore stop behaving like a target-value scraper and instead behave like a **financial-statement compiler**.

The required design is:

```text
Official CSE Filing
        ↓
Known Filing Context
        ↓
Source-Preserving Document Reconstruction
        ↓
Full Financial Statement Understanding
        ↓
Two Diverse Structural Interpretations + Bounded Constraint Resolution
        ↓
Candidate Ledger + Accounting Constraint Graph
        ↓
Global Resolution + Evidence Arbitration
        ↓
Targeted Failure Recovery Loops
        ↓
Canonical Financial Statement
        ↓
Target Fact Query
        ↓
Final Validation
        ↓
Independent Source Review + Release Approval
        ↓
Publish Approved Values / Explicit Exceptions
```

The goal is not merely to fill cells.

The goal is:

> **Fill the correct cell, with the correct value, for the correct issuer/entity, period, duration, unit, and accounting concept, while maximizing recoverable coverage and preserving complete audit evidence.**

---

# 2. Non-Negotiable Design Principles

## 2.1 Primary extraction must already be excellent

Tunnel A is not a weak first attempt.

The primary compiler must support, with evidence and resource bounds:

- known filing context
- whole-document reconstruction
- statement discovery
- table reconstruction
- header hierarchy
- column ownership
- entity resolution
- period resolution
- duration resolution
- unit detection
- normalization
- all-row extraction
- high-recall semantic candidate generation
- accounting ontology
- formula/constraint reasoning
- subtotal detection
- cross-column reasoning
- cross-period reasoning
- cross-filing reasoning
- global statement solving
- validation
- local repair

B provides a materially different structural reading; C resolves bounded ambiguity over observed evidence. C is not an independent third witness, and shared financial rules create correlated-error risk.

---

## 2.2 Never start from the number

The system should resolve known dimensions first:

```text
WHO?
→ Company / Group / Bank / Separate / Consolidated

WHEN?
→ Exact target reporting date

WHICH PERIOD ROLE?
→ Current / Comparative

HOW LONG?
→ 3M / 6M / 9M / 12M

WHAT STATEMENT?
→ Profit & Loss / Financial Position / Cash Flow / Equity / Notes / Share Information

WHAT UNIT?
→ Currency + scale

WHAT ROW / ACCOUNTING CONCEPT?
→ PAT / PBT / Revenue / Operating Profit / Assets / etc.

THEN:
WHAT VALUE?
```

The selected number should be the last unresolved dimension.

---

## 2.3 Reconstruct the whole statement, not only the 14 targets

The internal extraction layer must preserve all rows and all numeric cells from the financial statements.

Do not only search for:

- PAT
- PBT
- EPS
- NAVPS
- Operating Profit
- Total Equity
- Total Assets
- Total Liabilities
- Revenue / Gross Income
- Market Price
- D/E
- ROE
- ROA
- NPM

The system must extract enough surrounding accounting structure to understand the statement.

A 55-row P&L should remain a 55-row P&L internally.

A 90-row SOFP should remain a 90-row SOFP internally.

The final 14-field dataset is only a downstream projection.

---

## 2.4 Never discard useful candidates early

Forbidden pattern:

```text
semantic_score < 0.84
→ drop candidate forever
```

Required pattern:

```text
candidate uncertain
→ retain
→ attach competing hypotheses
→ pass to structural + accounting + global resolver
→ discard only when disproven or dominated by stronger evidence
```

Candidate generation should prioritize **high recall**.

Publication should prioritize **high precision**.

---

## 2.5 Formulas are evidence first, derivation second

Accounting equations are used in three modes.

### Mode A — identify an existing printed number

Example:

```text
PBT = 2,500
Tax = (600)
Unknown printed row = 1,900
```

Equation:

```text
2,500 - 600 = 1,900
```

supports identifying the printed `1,900` row as PAT.

This is still source extraction.

### Mode B — resolve between multiple printed candidates

Example:

```text
Profit from continuing operations = 1,750
Profit for the period = 1,900
```

The PBT-tax bridge supports the correct total PAT row.

This is source extraction.

### Mode C — create a number not printed in the source

Example:

```text
PBT = 2,500
Tax = 600
PAT not printed
```

Calculating `1,900` is a **derived value**, not an extracted value.

Derived values must never be silently labeled as source-extracted facts.

If derivation is not explicitly permitted by the methodology, do not publish it.

---

# 3. Existing Pipeline Components to Retain

Retain CSE universe/issuer discovery, filing catalog and download, SHA-256 archive, bounded execution, file-based Parquet/JSONL/JSON storage, review views, Excel export, price/ratio subsystems and release manifests where they meet their contracts.

Do not rebuild unrelated components. Make narrow integration fixes where proven defects would undermine extraction:

- Correct fiscal-calendar filing selection; exact calendar-date matching must not silently omit a legitimate off-calendar reporting period.
- Correct EPS/NAVPS validation, zero/sign handling and denominator applicability.
- Make comments metric-specific and generate all outputs after final gate evaluation from one release manifest.
- Parameterize run dates/periods; CI must execute reviewed source, not modify source during execution.

This scope introduces no database, web framework, cloud service or new orchestration platform.

---
# 4. Core Output Contract

The system ultimately publishes these 14 visible fields:

1. PAT
2. PBT
3. EPS — Diluted if valid, else Basic
4. NAVPS
5. Operating Profit
6. Total Equity
7. Total Assets
8. Total Liabilities
9. Revenue / Gross Income
10. Market Price per Share at Quarter End
11. Debt to Equity
12. ROE — Quarter
13. ROA — Quarter
14. NPM — Quarter

No TTM.

Ratios:

```text
D/E = Total Liabilities / Total Equity
ROE_Q = quarter PAT / quarter-end Total Equity
ROA_Q = quarter PAT / quarter-end Total Assets
NPM_Q = quarter PAT / quarter top line
```

Banks use quarterly Gross Income as the top-line denominator where appropriate.

Missing ratio input: retain `INSUFFICIENT_INPUT` only if needed for compatibility, and attach a metric-specific dependency issue, for example `ROA blocked: PAT quarter context unresolved`.

The D/E output must explicitly say it uses total liabilities / equity. This formula is retained; it must not be described as interest-bearing debt / equity. Zero is distinct from missing; negative denominators require the approved ratio policy, not a generic parser failure.

---

# 5. Quarter Truth Rules

For flow metrics:

- exact standalone current quarter / exact 3M is required
- Q1 can naturally be 3M
- Q2 filing may contain 3M and 6M
- Q3 filing may contain 3M and 9M
- Q4 must be an explicitly reported standalone final-quarter 3M value
- never use FY as Q4
- never publish FY - 9M as Q4
- never publish 9M as Q3
- never publish 6M as Q2
- cumulative figures may be used as validation evidence, not silently substituted

For stock metrics:

- use exact period-end balance-sheet values
- entity must be correct
- units must be resolved

---

# 6. Filing Context: Expectations and Observations

Build `KnownContext` before interpreting financial meaning, but treat discovery metadata as expected context, not an infallible header.

Required fields include stable issuer/security IDs and aliases; security-class applicability; sector profile; evidenced fiscal calendar; requested display bucket; actual candidate reporting start/end; required standalone entity; target duration; expected current/comparative dates; source publication/first-seen timestamps; knowledge cutoff; and source/version IDs for all prior or later filing references.

Maintain separate `expected_context`, `observed_context`, `context_evidence` and `conflicts`. A PDF's explicit dates or issuer headers that contradict metadata require resolution; never force the expected quarter onto an incompatible column.

Fiscal quarter is issuer-specific. Preserve actual off-calendar dates and an explicitly approved display-quarter mapping. June 25 must not become June 30 internally or in an unqualified output header. If policy requires exact calendar dates, disclose a calendar mismatch rather than pretending the filing is absent.

Use actual dates, scope, duration and basis to match facts across reports. Source-column role CURRENT/COMPARATIVE is separate from the target reporting period. Later evidence cannot enter an as-known historical release after its knowledge cutoff.

---
# 7. Canonical Raw Document Reconstruction

## 7.1 Goal

Create a high-fidelity representation of what is physically in the filing without making accounting decisions.

The output should preserve:

- page order
- text
- characters/words
- coordinates
- fonts where available
- lines
- images
- numeric strings
- raw date strings
- table-like spatial structure
- repeated headers
- page headings

## 7.2 Native PDF route

Primary tools:

- PyMuPDF
- pdfplumber

Optional structural route:

- Docling only after qualifying a specifically configured non-language-model layout/table pipeline. No VLM or language-model components; model artifacts and dependencies must be pinned and approved. It is not required for phase one.
- PyMuPDF deployment must pass license review; PDFium/pypdfium2 is a candidate alternative rendering/reading adapter, subject to the same corpus qualification.
- Preserve original PDF bytes as the authoritative source. Reconstructed text/OCR is not guaranteed lossless; quantify and expose reconstruction gaps.

## 7.3 OCR route

OCR is for:

- scanned PDFs
- image-only pages
- severely corrupted text extraction
- targeted local recovery regions

OCR should feed the same downstream IR.

```text
Native PDF ──────────────┐
                        ├──> CanonicalDocumentIR
OCR / Scanned PDF ──────┘
```

## 7.4 Suggested IR

```python
@dataclass
class TokenIR:
    text: str
    bbox: BBox
    page_number: int
    font_name: str | None
    font_size: float | None
    is_bold: bool | None
    source_method: str

@dataclass
class LineIR:
    tokens: list[TokenIR]
    bbox: BBox
    text: str

@dataclass
class TableCellIR:
    row_idx: int
    col_idx: int
    raw_text: str
    bbox: BBox
    rowspan: int = 1
    colspan: int = 1

@dataclass
class TableIR:
    page_number: int
    bbox: BBox
    cells: list[TableCellIR]
    header_rows: list[int]
    source_method: str

@dataclass
class PageIR:
    page_number: int
    width: float
    height: float
    tokens: list[TokenIR]
    lines: list[LineIR]
    tables: list[TableIR]

@dataclass
class CanonicalDocumentIR:
    pages: list[PageIR]
    quality: DocumentQuality
    source_sha256: str
```

---

# 8. Normalization Must Happen Before Target Fact Selection

Normalization is not just multiplying values at export time.

Create multiple normalization layers.

## 8.1 Text normalization

Preserve raw text while creating a normalized search form.

## 8.2 Numeric normalization

Examples:

```text
(1,245) → -1245
1 245 → 1245
1,245.50 → 1245.50
```

Store both `raw_text` and `parsed_numeric`.

## 8.3 Sign normalization

Handle:

- parentheses
- minus signs
- trailing minus
- accounting presentation
- OCR dash variants

## 8.4 Date normalization

Normalize multiple source date forms to ISO dates.

## 8.5 Duration normalization

Map phrases such as:

```text
Three months ended
Quarter ended
For the quarter
3 months to
```

to:

```text
duration_months = 3
```

Likewise for 6M, 9M and 12M.

## 8.6 Unit normalization

Normalize:

```text
Rs.'000
Rs. ' 000
LKR 000
In Rs thousands
Rs Mn
LKR million
```

to explicit currency and scale.

Per-share metrics must not inherit statement-wide scale incorrectly.

Resolve applicability before precedence: explicit metric/cell/row, column, table, statement, applicable page declaration, then report default. A nearby declaration from another region is ineligible. Adjacent-page inheritance needs an evidenced continuation. Equal-authority conflicts remain unresolved; unknown scale is not silently 1.

Separate currency, monetary scale, quantity scale and dimension. Explicit cents per share normalize to currency units; counts never inherit monetary scale but explicitly stated shares in thousands do scale. Explicit percentages normalize to decimal ratios with their raw notation retained. A foreign currency never silently becomes LKR.

Use Decimal/integer factors. Preserve zero, signs and raw text. A dash is not zero without an established source convention; join split digits only when their geometry proves they belong to the same cell.

## 8.7 Entity normalization

Normalize presentation terms such as Group/Consolidated and Company/Separate/Bank to explicit entity semantics.

Do not map `GROUP` as a fallback for required standalone Company/Bank facts.

---

# 9. Statement Discovery Engine

Before extracting metrics, identify the entire report structure.

Possible statement/region types:

```text
COVER
FINANCIAL_HIGHLIGHTS
PROFIT_LOSS
COMPREHENSIVE_INCOME
FINANCIAL_POSITION
CASH_FLOW
CHANGES_IN_EQUITY
NOTES
SHARE_INFORMATION
SEGMENT_INFORMATION
RELATED_PARTY
OTHER
```

Use:

- headings
- accounting row vocabulary
- table structure
- page continuity
- repeated headers
- numeric density
- known statement order
- cross-page continuation cues

Do not rely on fixed page numbers.

---

# 10. Full Table Reconstruction

The system must reconstruct actual table structure rather than only visual rows.

Required capabilities:

- header-row detection
- multi-row headers
- merged cells
- split labels
- split numeric tokens
- repeated table headers on continuation pages
- row indentation
- subtotal formatting
- blank spacer rows
- parent/child sections
- multi-entity columns
- multi-duration columns
- current/comparative columns
- repeated labels

---

# 11. Header Tree Compiler

Compile multi-row headers into explicit semantic columns.

Example:

```text
C1 = GROUP   / CURRENT     / 9M / 2026
C2 = GROUP   / COMPARATIVE / 9M / 2025
C3 = GROUP   / CURRENT     / 3M / 2026
C4 = GROUP   / COMPARATIVE / 3M / 2025
C5 = COMPANY / CURRENT     / 9M / 2026
C6 = COMPANY / COMPARATIVE / 9M / 2025
C7 = COMPANY / CURRENT     / 3M / 2026
C8 = COMPANY / COMPARATIVE / 3M / 2025
```

Represent the hierarchy explicitly so each numeric cell inherits a structural parent.

Do not primarily depend on nearest-header scoring after the table is compiled.

---

# 12. Compile Column Schemas Per Stable Header Region

Compile one column schema for each stable table/header region and reuse it for the governed rows. Do not assume a whole statement or page has one schema.

Recompile or explicitly validate continuity when a new table, repeated header, page break, scope block, period block, currency declaration or footnote changes applicability. A continuation link must be evidenced before inheriting previous-page headers.

Each cell references its effective context and evidence. Row/cell units and per-share/count exceptions override ordinary monetary table scale when explicitly applicable. Conflicting ownership remains unresolved; nearest physical proximity alone is insufficient.

---
# 13. Complete Statement Extraction

Once table structure is known, extract every row.

Do not restrict internal extraction to target metrics.

---

# 14. Canonical Financial Statement IR

Suggested representation:

```python
@dataclass
class StatementColumn:
    column_id: str
    entity: str | None
    period_end: date | None
    period_start: date | None
    temporal_type: str | None
    accounting_basis: str | None
    context_evidence_ids: list[str]
    duration_months: int | None
    comparison_role: str | None
    currency: str | None
    scale_factor: Decimal | None

@dataclass
class StatementCell:
    raw_text: str
    raw_numeric: Decimal | None
    normalized_value: Decimal | None
    source_page: int
    source_bbox: BBox
    column_id: str
    effective_unit_evidence_ids: list[str]
    unit_override: dict | None
    coordinate_transform_id: str | None

@dataclass
class ConceptHypothesis:
    concept: str
    semantic_score: float
    structural_score: float
    accounting_score: float
    total_score: float
    evidence: list[str]

@dataclass
class StatementRow:
    row_id: str
    raw_label: str
    normalized_label: str
    indentation_level: int
    parent_section: str | None
    cells: dict[str, StatementCell]
    hypotheses: list[ConceptHypothesis]

@dataclass
class CanonicalFinancialStatement:
    issuer_id: str
    source_sha256: str
    statement_type: str
    columns: list[StatementColumn]
    rows: list[StatementRow]
    unit_evidence: list[dict]
    compilation_evidence: dict
```

---

# 15. Financial Accounting Ontology

Use a richer accounting ontology rather than mapping arbitrary labels directly to the final 14 outputs.

## 15.1 Profit & Loss concepts

```text
TOP_LINE
REVENUE
GROSS_INCOME
INTEREST_INCOME
INTEREST_EXPENSE
NET_INTEREST_INCOME
FEE_INCOME
TRADING_INCOME
INSURANCE_REVENUE
COST_OF_SALES
GROSS_PROFIT
OTHER_OPERATING_INCOME
DISTRIBUTION_EXPENSE
ADMINISTRATIVE_EXPENSE
OTHER_OPERATING_EXPENSE
IMPAIRMENT
OPERATING_PROFIT
FINANCE_INCOME
FINANCE_COST
ASSOCIATE_JV_RESULT
PBT
INCOME_TAX
CONTINUING_OPERATIONS_RESULT
DISCONTINUED_OPERATIONS_RESULT
PAT
ATTRIBUTION_OWNERS
ATTRIBUTION_NCI
EPS_BASIC
EPS_DILUTED
WEIGHTED_AVG_SHARES
```

## 15.2 Financial Position concepts

```text
NON_CURRENT_ASSETS
CURRENT_ASSETS
TOTAL_ASSETS
SHARE_CAPITAL
RESERVES
EQUITY_ATTRIBUTABLE_TO_OWNERS
NCI_EQUITY
TOTAL_EQUITY
NON_CURRENT_LIABILITIES
CURRENT_LIABILITIES
TOTAL_LIABILITIES
ORDINARY_SHARES
NAVPS
```

Add supporting concepts needed for formula reconciliation and sector-specific statements.

---

# 16. Sector / Issuer Profiles

Profiles define semantic expectations and equation applicability, not fixed page templates.

Suggested profiles:

```text
GENERAL_CORPORATE
BANK
FINANCE_LEASING
INSURANCE
INVESTMENT_HOLDING
OTHER
```

Profiles may influence:

- top-line concept selection
- expected statement concepts
- formula applicability
- unusual terminology

They must never define hardcoded page or column templates.

---

# 17. High-Recall Semantic Candidate Generation

Every row may have multiple concept hypotheses.

Signals:

- exact regex aliases
- normalized aliases
- RapidFuzz
- optional qualified TF-IDF plus linear classifier for unresolved semantic labeling only
- statement type
- row position
- neighboring rows
- indentation
- subtotal formatting
- parent section
- issuer profile
- accounting relationships

No MiniLM, sentence-transformer embeddings, LLMs, SLMs or generative VLMs are permitted. Local execution is not an exception.

Optional classical classifiers use explicitly versioned features, independent training/evaluation labels and calibrated scores. They cannot override hard source/context eligibility or generate a financial value. No production training or automatic model downloads are permitted.

---

# 18. Row Sequence and Structural Semantics

Interpret labels in context.

Use:

```text
row label
+
previous rows
+
next rows
+
parent section
+
position
+
subtotal behavior
+
equation relationships
```

Do not interpret rows in isolation.

---

# 19. Accounting Constraint Graph

Nodes include:

- statement rows
- numeric cells
- concept hypotheses
- columns
- entity labels
- periods
- durations
- units
- statement regions

Edges include:

```text
ABOVE
BELOW
CHILD_OF
SIBLING_OF
SUBTOTAL_OF
SAME_COLUMN
SAME_ENTITY
SAME_PERIOD
SAME_DURATION
SAME_UNIT
CANDIDATE_CONCEPT
RECONCILES_WITH
CONTRADICTS
```

---

# 20. Conditional Equation Registry

Equations support interpretation of observed printed candidates. They never manufacture a source-extracted value.

Examples, when complete and financially applicable: assets = liabilities + equity; assets = current + non-current assets; liabilities = current + non-current liabilities; gross profit = revenue minus cost of sales; PBT = the applicable operating/non-operating bridge; and PAT = PBT less the applicable tax charge. Attribution and consolidated equity bridges apply only to the appropriate scope/basis.

Every equation declares required concepts, compatible entity/period/currency/accounting basis, signed-term convention, rounding tolerance, completeness conditions and applicability. If an expense is already parsed as negative, do not subtract it a second time. Missing terms and unknown presentation mean UNTESTED, not FAIL or PASS.

EPS requires the applicable attributable earnings numerator and independent weighted-average eligible shares, with diluted adjustments where relevant. NAVPS requires matching equity and eligible period-end shares. These denominators are not interchangeable. Preserve negative signs and zero; never use absolute-value comparison to hide a sign error or a truthiness fallback to replace zero.

Rounding tolerance derives from disclosed precision and compatible operands. No universal 5% tolerance or plausibility range establishes correctness. Equations are conditional support: a jointly wrong Group column or jointly wrong scale can still balance. Final validation must inspect independent source context and must not count the solver's own factor as independent confirmation.

---
# 21. Subtotal Hypotheses

Use reconciliation, row hierarchy, indentation, formatting and labels to propose that an existing printed row is a subtotal. Preserve competing interpretations. Numerical equality alone cannot prove a concept because coincidences and omitted components occur.

Do not derive an absent printed subtotal for publication under a source-only metric. Unknown non-target row concepts may remain unknown without blocking independently resolved targets.

---
# 22. Cross-Column Reasoning

Check relationships across all compatible columns:

```text
Current 3M
Comparative 3M
Current 9M
Comparative 9M
Group
Company
```

Repeated equation consistency across columns is strong semantic evidence.

---

# 23. Cross-Duration Reasoning

Use cumulative values as supporting evidence.

For example:

```text
9M - 6M ≈ printed standalone Q3
```

can confirm a printed Q3 candidate.

Do not silently derive Q3.

---

# 24. Cross-Filing Evidence Without Temporal Leakage

Match actual period start/end, duration, entity, metric basis, currency and restatement basis, not a filing's quarter name or column position.

For example, a later report may repeat a specific earlier three-month period. That repeated value is comparable only when the full temporal and accounting tuple matches. A Q3 comparative column is usually not the immediately preceding Q2; never assume that relationship.

Q1 + Q2 + Q3 versus 9M, or 9M minus 6M versus an explicitly printed Q3, is corroborating evidence only when operands share scope, fiscal-year start, basis and compatible revisions. Do not publish a derived quarter.

Keep as-known and latest-restated modes distinct. Later sources beyond the run's knowledge cutoff cannot change the historical release. In this strict reported-current-column profile, cross-filing comparative values support validation only; publication from a later comparative disclosure requires a separate approved backfill policy and explicit lineage.

---
# 25. Diverse Structural Readings and Shared Financial Contracts

Use A and B as materially different structural interpretations of the same immutable filing. C is a bounded resolution engine over their evidence, not an independent third source observation.

Share immutable raw source and explicit financial contracts. Do not share A's resolved rows/headers into B and then claim independent reconstruction. Record engines, tokenization, layout decisions, context dependencies and shared rules so correlated failures are visible.

All paths preserve the same hard source-truth rules. No majority voting or agreement-based probability multiplication is permitted. Shared equations/ontology/context can produce shared mistakes.

---
# 26. Tunnel A — Native Geometry Financial Compiler

Primary path.

Must include:

1. PyMuPDF geometry
2. visual row reconstruction
3. table detection
4. multi-row header reconstruction
5. statement classification
6. known-context binding
7. column schema compilation
8. entity ownership
9. duration ownership
10. current/comparative ownership
11. unit resolution
12. complete statement extraction
13. numeric normalization
14. semantic concept candidates
15. accounting ontology
16. row sequence reasoning
17. subtotal discovery
18. formula constraints
19. cross-column reasoning
20. cross-duration reasoning
21. cross-filing reasoning
22. global statement solving
23. internal validation
24. local repair
25. full evidence output

Tunnel A should solve the overwhelming majority of clean native filings.

---

# 27. Tunnel B — Independent Table Reconstruction Compiler

Use materially different structural mechanics, for example:

- pdfplumber character/word geometry
- independent line grouping
- independent table-boundary inference
- independent header-tree construction
- Docling structural representation where useful

Then perform the same complete financial intelligence stack.

Tunnel B must not simply call Tunnel A with different flags.

---

# 28. Resolver C — Bounded Constraint Resolution

C jointly evaluates unresolved row grouping, column ownership, concept and subtotal hypotheses over observed candidates. It uses the common financial ontology and conditionally applicable equations.

It is not a third independent extraction witness. It cannot invent a number, overwrite stronger explicit source evidence, or force a complete interpretation when several remain possible. Always retain an unresolved assignment.

Partition the graph into connected ambiguity components. Bound candidate count, beam width, iterations, memory and elapsed time per component. An incomplete search yields SEARCH_BUDGET_EXHAUSTED with preserved candidates, not proof that no valid candidate exists. A beam-search winner is not proof of unique correctness.

---
# 29. Candidate Ledger

Every tunnel must emit a candidate ledger.

Nothing useful is permanently dropped during initial interpretation.

The ledger must retain:

- accepted candidates
- rejected candidates
- unresolved candidates
- alternative labels
- alternative columns
- alternative units
- alternative periods
- reasons for rejection
- tunnel source
- source coordinates

---

# 30. Evidence Arbitration

Hard eligibility precedes scoring: issuer, source scope, actual period/duration, source-column role, currency/unit applicability and required concept must be compatible. Explicitly incompatible candidates remain in the audit ledger with rejection reasons but cannot win via a large aggregate score.

Rank eligible alternatives using structural support, direct label evidence, independently reconstructed agreement and applicable accounting relationships. Preserve an unresolved result for conflict, insufficient evidence or indistinguishable alternatives. Reevaluate eligible alternatives if the initial selection later fails.

Do not count A/B/C outputs as independent votes. C is a solver; A/B may share correlated parser and ontology failures. A chosen printed number must retain evidence that establishes both its numeric transcription and its financial meaning.

---
# 31. Failure Diagnoser

If the arbiter cannot resolve a fact, create an exact failure ticket.

Recommended internal failure families:

```text
STATEMENT_REGION_CONFLICT
TABLE_BOUNDARY_CONFLICT
ROW_RECONSTRUCTION_CONFLICT
HEADER_TREE_CONFLICT
ENTITY_CONFLICT
PERIOD_CONFLICT
DURATION_CONFLICT
CURRENT_COMPARATIVE_CONFLICT
UNIT_CONFLICT
NUMERIC_PARSE_CONFLICT
SEMANTIC_CONFLICT
SUBTOTAL_CONFLICT
FORMULA_CONTRADICTION
CROSS_COLUMN_CONTRADICTION
CROSS_FILING_CONTRADICTION
OCR_QUALITY_FAILURE
SOURCE_DISCLOSURE_REVIEW_REQUIRED
```

Failures must be dimension-specific.

---

# 32. Recovery, Review and Publication States

Maintain orthogonal extraction state, validation outcome, review state and publication state.

Extraction moves through reconstruction, context binding, concept resolution and normalization. Validation returns PASS, FAIL, UNTESTED or NOT_APPLICABLE for each applicable check. Source-fact approval is independent of those states.

Initial official publication requires independent review of value, sign, unit, entity and period for every unique source fact, including explicit security-class applicability where relevant. Corrections require a different authorized checker. Derived ratios reference approved source facts and tested formula versions; they do not masquerade as printed source values.

Unresolved affected facts enter review/recovery. Unrelated resolved facts are not invalidated solely because a distant non-target row is unknown. No confidence threshold, equation score or parser agreement directly publishes a fact.

---
# 33. Failure-Directed Recovery Loops

Recovery only starts after strong normal interpretation.

It must not be a rerun of the same extractor with boolean flags.

## 33.1 Structural recovery

Try:

- alternate line grouping
- character-level geometry
- pdfplumber reconstruction
- Docling reconstruction
- different table-boundary thresholds
- continuation-page stitching
- localized region reconstruction

## 33.2 Semantic recovery

Use:

- widened ontology candidates
- row ordering
- parent sections
- neighboring concepts
- accounting equations
- cross-column consistency
- sector profile
- optional qualified classical TF-IDF classifier
- global re-solve

Do not merely lower fuzzy thresholds.

## 33.3 Unit recovery

Search unit evidence at:

```text
cell
row
column
table
statement
page
adjacent statement pages
report
```

Then re-normalize affected cells.

## 33.4 Numeric corruption recovery

Try:

- character-level parse
- alternate PDF parser
- source-region reread
- local OCR crop
- multiple OCR preprocessing variants

## 33.5 Entity recovery

Rebuild the complete multi-row entity header hierarchy.

Never relax Company into Group.

## 33.6 Period/duration recovery

Use:

- KnownContext
- fiscal calendar
- explicit dates
- duration blocks
- current/comparative years
- cumulative relationships
- prior/later filings

Never relax exact 3M into cumulative YTD.

## 33.7 Formula contradiction recovery

Identify the weakest evidence node and repair that node first.

Do not blindly rerun all related facts.

---

# 34. Uncertainty Graph

Each candidate/fact should expose uncertainty by dimension.

Example:

```text
PAT
├── statement      RESOLVED
├── concept        RESOLVED
├── entity         RESOLVED
├── period         RESOLVED
├── duration       CONFLICT
├── column         CONFLICT
├── unit           RESOLVED
├── numeric        RESOLVED
└── accounting     FAIL
```

Recovery should attack unresolved dimensions only.

---

# 35. Constrained Resolution With an Abstention Option

Resolve interdependent ambiguities together, within bounded connected regions. Use deterministic weighted factors and bounded search initially; no custom model training is required.

Hard constraints: Group cannot satisfy required Company/Bank; an incompatible actual period cannot satisfy the target; YTD/FY cannot satisfy a printed standalone 3M target; cash-flow numbers cannot substitute for income-statement targets; and notes follow an explicit source-authority policy.

Distinguish source-column role from target-period identity. The default strict profile queries the intended current filing column; later comparative disclosures are corroborating evidence under the cross-filing policy, not automatically substitute publications.

Accounting identities are conditional supporting factors, not universal hard equalities. Missing operands, incomparable restatements and legitimate sector exceptions must not force the solver to select a wrong concept. Keep unresolved hypotheses and return conflicting evidence when no unique supported result exists.

High recall means retaining raw tokens and candidate/rejection evidence, not unlimited active hypotheses in RAM. Bound active search and persist dominated alternatives. Preserve the distinction between proven ineligibility and unsearched candidates.

---
# 36. Target Fact Query Layer

After the canonical statement is resolved, target extraction becomes a query.

Example:

```text
PAT:
statement_type = PROFIT_LOSS
concept = PAT
entity = COMPANY
duration = 3
comparison_role = CURRENT
period_end = target_period
```

The system should no longer think of itself as “finding PAT in the PDF”.

It should query a compiled financial statement.

---

# 37. Total Liabilities Policy

Retain the strict source policy unless methodology explicitly changes.

For the visible Total Liabilities field:

- publish explicit Total Liabilities source row only
- do not publish `Assets - Equity`
- do not silently publish `Current Liabilities + Non-current Liabilities`
- formulas may validate or identify an existing printed total row
- derived liabilities must remain distinctly marked and non-published unless policy explicitly allows them

---

# 38. EPS Policy

Extract EPS_BASIC and EPS_DILUTED separately. Select diluted when eligible and valid; otherwise basic when eligible and valid, with an explicit fallback reason. A valid zero is not missing. A rejected diluted candidate and its issue remain in lineage.

Bind both to the correct entity, actual three-month period and share class. Use explicit per-share units; do not inherit ordinary monetary statement scale. Explicit cents or another applicable per-share scale require dimensional conversion.

For independent reconciliation, use applicable earnings attributable to eligible ordinary holders and the corresponding weighted-average shares; diluted EPS may require adjusted numerator and denominator. Do not blindly use PAT / any available share count. Missing independent inputs leave reconciliation UNTESTED; they do not automatically invalidate a clearly reported EPS.

---
# 39. NAVPS Policy

Extract explicit, eligible NAVPS. Reconcile only with the matching equity definition, security-class applicability and independent eligible period-end shares. Do not prioritize weighted-average EPS shares or infer a circular pass from implied shares.

Preserve signs, zero and the local per-share unit. Lack of independent denominator evidence means UNTESTED, not automatic approval or rejection.

---
# 40. Historical Price Subsystem

Retain the separate price subsystem. First establish price type, security class, currency, actual price/trade date and adjustment basis. A filing's high/low price or a later live price is not a quarter-end last-traded price.

Use an eligible explicit official class-specific filing disclosure or an authorized official historical source. Last valid trade on/before period end is allowed only under an approved staleness and trading-calendar policy; expose its actual date. Never look forward.

Preserve raw responses, historical aliases, corporate actions, suspensions, source availability and query attempts. A free source's inaccessibility is not proof that no historical price exists. Record unavailable access separately from a verified absence of a trade.

---
# 41. Understanding-Time Checks and Independent Final Checks

Use equations, subtotal relationships and compatible cross-column/cross-filing evidence during interpretation. They guide a hypothesis; they do not certify it.

Final checks independently establish source identity, printed numeric text, scope, actual period/duration, source-column role, unit ownership and normalization. Recheck eligibility against governing headers rather than merely rerunning the solver's own score. Financial reconciliation is applicability-gated; UNTESTED is visible.

Preserve source contradictions. Do not alter a correctly transcribed issuer number to make an equation balance. Material source inconsistencies require an attributed exception decision. Publication additionally requires the review and release policy, not only accounting validation.

---
# 42. Terminal Outcomes Describe a Bounded Search

Do not finalize missing statuses after the first failure. Execute the applicable, materially different recovery routes under explicit resource limits, recording attempts, skipped routes and stop reasons.

Exhausting configured routes means the system did not resolve a fact; it does not prove the source omitted it. Distinguish SEARCH_INCOMPLETE, SEARCH_BUDGET_EXHAUSTED and NOT_LOCATED_AFTER_CONFIGURED_RECOVERY from an independently reviewed non-disclosure.

Confirmed absence is specific to metric, scope, period and reviewed source set. Reopen it when a source revision or newly discovered eligible filing changes that evidence. Terminal describes this run/version, not eternal unavailability.

---
# 43. Metric-Level Issue Taxonomy

Use explicit issues for statement/table/header conflicts; unresolved entity, period, duration, units or concepts; numeric/OCR corruption; source contradictions; incomplete discovery; budget exhaustion; and blocked derived inputs.

Automated observations include ONLY_CUMULATIVE_CANDIDATES_LOCATED and ONLY_GROUP_CANDIDATES_LOCATED. They must not be rendered as confirmed whole-quarter absence. REVIEW_CONFIRMED_NOT_DISCLOSED requires attributed evidence review for the exact metric/scope/period.

Retain existing codes at an adapter boundary if required by consumers, but attach precise semantics, applicability and review state. INSUFFICIENT_INPUT must expose dependency fact IDs and reasons. Non-positive denominator issues must follow the actual formula policy; a legitimate loss or negative equity is not a parser error.

Quarter-level summaries aggregate facts honestly: for example, assets/equity approved, PAT unresolved and ROA blocked by PAT. A verified quarterly row is evidence for its table/column context, not proof that every other metric is disclosed.

---
# 44. Evidence and Lineage Contract

Every published fact must retain:

- issuer
- symbol/security
- source filing id
- source path
- source SHA-256
- page
- bounding box
- raw label
- raw value
- parsed numeric
- currency
- scale
- normalized value
- statement type
- row id
- column id
- entity
- period
- duration
- current/comparative role
- semantic concept
- tunnel results
- competing candidates
- rejected alternatives
- equation checks
- cross-column checks
- cross-filing checks
- arbiter decision
- recovery attempts
- validation result
- review status
- separate value/label/entity/period/unit evidence regions
- original coordinate system and rendering transforms
- source publication/first-seen time and knowledge cutoff
- actual period start/end and accounting/restatement basis
- interpretation dependency hashes, rule/model/config versions
- validation applicability and unresolved-search budgets
- authenticated approval events, superseded versions and release ID

---

# 45. Proposed Module Architecture

```text
src/cse_financial_etl/

  ingestion/
    native_pdf.py
    ocr_pdf.py
    quality_router.py

  document/
    document_ir.py
    geometry.py
    region_detector.py
    table_reconstructor.py
    logical_rows.py
    continuation.py

  compiler/
    known_context.py
    statement_detector.py
    header_tree.py
    column_compiler.py
    structure_normalizer.py
    statement_compiler.py
    canonical_statement.py

  accounting/
    ontology.py
    sector_profiles.py
    semantic_candidates.py
    row_context.py
    concept_rules.py

  constraints/
    graph.py
    equation_registry.py
    subtotal_discovery.py
    balance_sheet.py
    profit_loss.py
    eps.py
    navps.py
    temporal.py
    cross_column.py
    cross_filing.py

  tunnels/
    tunnel_a_geometry.py
    tunnel_b_table.py
    common_financial_engine.py

  resolution/
    constraint_resolver.py
    candidate_ledger.py
    factor_scores.py
    global_resolver.py
    beam_search.py
    arbiter.py
    uncertainty.py

  recovery/
    failure_diagnoser.py
    recovery_router.py
    structural_recovery.py
    semantic_recovery.py
    unit_recovery.py
    numeric_recovery.py
    entity_recovery.py
    period_recovery.py
    ocr_recovery.py

  facts/
    query_engine.py
    target_metrics.py
    derived_facts.py

  validation/
    final_validator.py
    publication_gates.py
```

Reuse existing source/download/orchestration/output modules where practical.

---

# 46. Recommended Implementation Strategy for the AI Agent

Do not rewrite everything in one uncontrolled change.

## Phase 1 — Freeze contracts and regression baseline

1. Run current test suite.
2. Run existing golden tests.
3. Preserve current full-universe output as baseline.
4. Record:
   - fact coverage
   - wrong-publish observations
   - review reasons
   - runtime
   - parser failures
5. Add explicit regression fixtures.

## Phase 2 — Introduce new IRs without changing publication

Implement:

- `CanonicalDocumentIR`
- `TableIR`
- `CanonicalFinancialStatement`
- `KnownContext`
- `CandidateLedger`
- `FailureTicket`
- `UncertaintyGraph`

Run side-by-side with current extractor.

## Phase 3 — Build strong Tunnel A

Implement the complete primary compiler before depending on B/C.

## Phase 4 — Add full Tunnel B

Build a materially independent structural path and record agreement/disagreement statistics.

## Phase 5 — Add bounded Resolver C

Build component-level constraint resolution with an explicit abstention result; do not count it as independent extraction evidence.

## Phase 6 — Build Arbiter + Failure Diagnoser

Implement:

- evidence arbitration
- dimension-specific diagnosis
- uncertainty graph
- terminal status logic

## Phase 7 — Build targeted recovery loops

Implement:

- structural
- semantic
- unit
- numeric
- entity
- period
- OCR
- cross-filing recovery

## Phase 8 — Integrate target fact queries and final validation

Replace current target row matcher with canonical-statement queries.

## Phase 9 — Full-universe hardening

For every remaining missing core fact:

1. inspect terminal failure family
2. confirm all expected recovery routes ran
3. determine if value is genuinely absent
4. add regression fixture
5. improve the correct component
6. rerun universe
7. ensure precision did not regress

Continue until unresolved cases are explainable and coverage improvements flatten.

---

# 47. Tests That Must Exist

## 47.1 Document fidelity

Check:

- all pages preserved
- rows not lost
- numeric tokens not dropped
- bounding boxes preserved
- OCR/native paths produce compatible IRs

## 47.2 Table reconstruction

Fixtures:

- Group/Company side-by-side
- Company/Group reversed
- multi-row headers
- split labels
- split numbers
- continuation pages
- repeated headers
- no grid lines
- multiple tables
- footnotes
- percentage columns

## 47.3 Period

Cases:

- Q1 3M
- Q2 3M + 6M
- Q3 3M + 9M
- Q4 explicit 3M + FY
- current/comparative swapped
- non-calendar fiscal year
- year-only headers
- full-date headers

## 47.4 Entity

Cases:

- Group and Company same table
- separate Group/Company pages
- Bank vs Group
- Consolidated vs Separate
- ambiguous header spans
- Group only
- Company only

## 47.5 Units

Cases:

- Rs.'000
- Rs 000
- Rs Mn
- LKR millions
- bare Rs
- table/page/statement units
- conflicting units
- EPS/NAVPS scale exception

## 47.6 Semantics

Include unusual labels for all important concepts and require ambiguous candidates to remain retained until resolved.

## 47.7 Formulas

Verify:

- formulas identify existing printed totals
- formulas resolve candidate labels
- formulas do not silently generate source facts
- tolerance behavior
- sign conventions
- negative values
- sector applicability

## 47.8 Recovery

For each failure family:

- trigger the failure
- ensure correct recovery route runs
- recover the correct value
- ensure unrelated facts are unchanged

## 47.9 Structural diversity and correlated failures

Cases:

- A succeeds, B differs
- B succeeds, A fails
- C resolves A/B conflict
- two tunnels agree and one is wrong
- all paths disagree and the final result remains review
- all paths agree because a shared rule is wrong; independent source review catches it
- solver timeout preserves unresolved candidates rather than declaring absence

## 47.10 No-overpublication

Must prove:

- Group never populates required Company
- 9M never populates 3M
- comparative never populates current
- FY never populates Q4 3M
- Assets-Equity never becomes extracted liabilities
- formula-derived PAT never becomes source-extracted PAT
- later live market price never becomes quarter-end price

---

# 48. Accuracy and Coverage Evaluation

Track separately:

```text
Document reconstruction accuracy
Statement classification accuracy
Header/column ownership accuracy
Entity accuracy
Duration accuracy
Current/comparative accuracy
Unit accuracy
Semantic row-label accuracy
Numeric exact accuracy
Wrong-populated-cell rate
Core metric coverage
Recovery success rate
Tunnel agreement rate
Terminal unresolved rate
```

Do not collapse everything into one “accuracy” percentage.

---

# 49. Independent Benchmark and Release Acceptance

Build an independently adjudicated benchmark across sectors, issuers, layouts, fiscal calendars and OCR quality. A 100-issuer corpus is a useful starting target, not a guarantee or sufficient statistical justification by itself. Include missed disclosures and false absence decisions, not only candidates the pipeline already found.

Keep training/tuning data, pipeline-seeded regressions, held-out issuers/layout families and later-period tests separate. Report precision, eligible-disclosure recall, abstention, wrong-publication observations and uncertainty by metric and stratum. Define every numerator/denominator and sample-selection method.

Development diagnostics may report percentage scores. They are not permission to publish wrong values. Initial official release gates are:

- 100% of published facts have resolvable source or permitted derivation evidence.
- 100% of unique published source facts receive independent source review; reused class applicability is checked separately.
- Zero known unresolved critical defects in proposed published facts.
- Zero critical failures in the adjudicated high-risk regression corpus.
- Zero unauthorized Group substitutions, FY/YTD quarter publications, future historical prices or formula-generated source facts.
- Every omission has a truthful, scoped issue or approved exception; no silent zero-filling.
- All final artifacts reconcile to the same approved release manifest.

Coverage >=95% of independently confirmed eligible disclosures can be a development objective, never a reason to weaken these gates. A statistical model score, a selected zero-error sample and a human-review process do not prove absolute 100% population accuracy. Source transcription correctness is distinct from whether the issuer's filing is itself correct.

---
# 50. Production Logging

Each filing should produce a structured extraction report:

```json
{
  "filing_sha": "...",
  "known_context": {},
  "document_quality": {},
  "statements_detected": [],
  "tunnel_a": {},
  "tunnel_b": {},
  "resolver_c": {},
  "arbiter": {},
  "failure_tickets": [],
  "recovery_attempts": [],
  "final_facts": [],
  "terminal_unresolved": []
}
```

---

# 51. CPU and Memory Strategy

Run A on all filings. Run B on all benchmark filings, risky/unresolved facts and a stratified sample of apparently successful A outputs. Invoke C on bounded ambiguity components. Record incremental recovery and correlated errors, not just agreement.

Start with one or two isolated document processes on the 16 GB development machine, then qualify concurrency with measured peak RAM and runtime on the largest PDFs. Do not promise this capacity before testing. Keep OCR crop resolution and engine threads bounded; release page images and graphs after checkpointing.

Retain raw evidence and all candidate/rejection metadata on disk; bound active hypotheses, graph size, beam width, iterations and elapsed time. Stop with an explicit budget issue and resumable checkpoint rather than crash, loop forever or invent a result.

---
# 52. File-Based Caching, Reproducibility and Atomic Release

Cache keys include source hash, parser/native/OCR/model versions, configuration, text-normalization version, ontology/equations, unit/metric policy, fiscal-calendar/context version and all cross-filing/price dependency versions that affect interpretation. Source hash plus a generic extractor version is insufficient when external evidence changes.

Invalidate only affected downstream stages. Preserve prior results and approvals for their original versions. Replay frozen inputs deterministically with stable ordering and recorded seeds; do not let filesystem order or current clock time decide a candidate.

Use immutable JSON manifests, JSONL events and Parquet partitions in versioned directories. One writer owns a run/release; enforce locks and idempotency keys. Write complete artifacts to temporary paths, flush and validate them, then atomically promote the manifest/pointer on the same filesystem. Readers consume only approved manifests. Test Windows interruption and filesystem behavior explicitly.

Application append-only files and hashes are not tamper-proof by themselves. Official releases need bank-managed access controls, retained versions and authenticated approval records. Restore drills must include source PDFs, decisions and manifests. No database is introduced in this implementation scope.

---
# 53. No Production Self-Learning

Do not automatically train from production outputs.

Do not allow self-confirmed labels to become future truth.

Improvements must come from:

- reviewed gold corrections
- explicit aliases
- deterministic ontology updates
- tested semantic models
- regression fixtures

---

# 54. Useful Review and Accuracy Views

Review shows the complete source page with the candidate value, label, scope/period/unit headers highlighted; competing candidates; failed dimensions; independent-reader dependencies; recovery attempts; and the precise reason publication is blocked. A value-only crop is insufficient.

Initially, independently check each unique published source fact. A different authorized person checks corrections. Authenticate reviewer identity through the approved operating workflow rather than trusting an editable name in CSV. Bind approval to source/evidence/fact/policy versions and invalidate affected eligibility after material changes.

Add Accuracy_Quality to the workbook and existing review view. Show universe/filing coverage, numeric coverage, independent review coverage, eligible-disclosure recall, measured publication precision, false-absence rate, unresolved issues and release status. Provide numerators, denominators and benchmark/sample provenance. Evidence confidence remains separate from measured accuracy.

All comments, review files, quality views and financial exports derive from the same finalized manifest. A partial official release needs an explicit exception list and authorized approval; an unresolved draft is not an approved release.

---
# 55. Definition of Done

The extraction redesign is complete only when it runs on the full universe; independently adjudicated printed facts are recovered without weakening scope/period/unit rules; A/B structural diversity is measured; C remains bounded and can abstain; raw rows/cells and candidate evidence are retained; header-region context and local overrides work; cross-filing dependencies are time/basis compatible; and recovery outcomes are honest.

All high-risk real-PDF regressions and release-policy tests must pass. Adjudicate every material difference from the frozen baseline, including newly numeric, changed and newly withheld facts. Measure accuracy/recall separately from confidence and coverage, including false non-disclosures.

Complete the local Windows/VS Code setup and resource qualification; failure/resume and atomic-output tests; authenticated review and independent correction approval; quality/report consistency; and evidence restoration. No design percentage substitutes for these demonstrations. No absolute infallibility claim is permitted.

---
# 56. AI Agent Execution Instructions

The coding agent must:

1. **Do not delete working source/download/export code unnecessarily.**
2. **Redo the extraction core around this compiler architecture.**
3. **Do not reduce Tunnel A to a cheap parser.**
4. **Do not use structural reader B or Resolver C as excuses for weakness in primary compiler A.**
5. **Do not drop candidates early.**
6. **Do not loosen Company/period/duration truth conditions to improve coverage.**
7. **Do not fill missing cells with formula-generated values unless explicitly allowed and distinctly marked as derived.**
8. **Do not claim accuracy from confidence scores. Use independent gold validation.**
9. **Every fixed bug must get a regression test.**
10. **Every terminal error must show which recovery paths ran.**
11. **Run real filings continuously, not synthetic tests only.**
12. **Run targeted real-PDF regressions continuously; run full-universe comparisons at integration milestones and release candidates on frozen inputs.**
13. **Prioritize recovery of real source values rather than cleaner error labels.**
14. **Never accept a coverage gain that increases wrong-populated cells.**
15. **Keep complete source lineage for every published fact.**

---

# 57. Final Architecture Summary

1. Reconcile discovery metadata with observed filing context and preserve original PDF/hash.
2. Construct inspectable document evidence and discover statement regions.
3. A compiles native geometry; B independently reconstructs difficult or audited regions.
4. Compile stable header-region schemas; retain all printed rows/cells and context hypotheses.
5. Apply hard eligibility; use bounded C to resolve compatible ambiguities with conditional accounting support.
6. Recover unresolved dimensions using materially different methods, or stop with explicit evidence and budget status.
7. Query canonical target facts; verify source context independently; obtain required review approval.
8. Calculate only permitted ratios from approved inputs and obtain one frozen release manifest.
9. Publish consistent Excel, quality, review and machine-readable outputs from that manifest.

The price subsystem remains separate and date/class-aware. No LLM/SLM or database is introduced. Current official source-only quarterly rules are preserved.

---
# 58. Final Principle

Generate candidates with high recall, preserve source evidence, resolve financial context before ranking, and publish only supported facts. Interpret the surrounding statement without requiring every non-target concept to be solved. Use diverse structural readings and bounded constraints; do not mistake shared-rule agreement for independent proof.

Improve recovery of real printed values. Keep uncertainty visible and metric-specific. Source absence requires appropriate evidence review; exhausted search means exhausted search. Independent review and tested release controls make outputs defensible, but cannot honestly guarantee infallibility.

Revision 2 is the frozen implementation baseline. It incorporates the architecture review and the three Resolver C terminology cleanups, and supersedes Revision 1 and the original extraction redesign specification. Implementation and qualification against the preserved real-PDF corpus remain required before official use.
