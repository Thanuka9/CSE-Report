# CSE Quarterly Financial Data Platform
## Final Frozen Architecture — Laptop-Friendly, No Database, No LLM

**Status:** Final architecture for implementation  
**Operating target:** Windows laptop / VS Code / local Python execution  
**Database:** None  
**LLM:** None  
**Model training / fine-tuning:** None  
**Primary storage:** Parquet + JSONL/JSON  
**Primary output:** Auditable Excel workbook  
**Core intelligence:** NLP + pretrained transformer embeddings + transient vectors + clustering + spatial/evidence graph + deterministic financial validation

---

# 1. Core principles

The ETL must not assume that all CSE quarterly PDFs have the same format.

The system must not depend on:

- a fixed number of columns;
- fixed column order;
- fixed header line positions;
- fixed table layouts;
- fixed page locations;
- one PDF extraction library;
- one issuer-specific template;
- positional rules such as `values[0]`, `values[-2]`, `values[3]`;
- a database;
- an LLM;
- model training or fine-tuning.

The output schema is fixed, but the input layout is dynamic.

The ETL must discover the structure of every filing independently and prove the meaning of every published value.

---

# 2. Final quarterly metrics

For every requested quarter, the output contains:

1. PAT
2. PBT
3. EPS — Diluted if valid and available, otherwise Basic
4. NAVPS
5. Operating Profit
6. Total Equity
7. Total Assets
8. Total Liabilities
9. Revenue / Gross Income
10. Market Price per Share — Last Traded at Quarter End
11. Debt to Equity
12. ROE — Quarter
13. ROA — Quarter
14. NPM — Quarter

There is **no TTM calculation** in this project.

---

# 3. Final ratio definitions

All ratios are calculated for the exact requested quarter.

## Debt to Equity

```text
Debt to Equity = Total Liabilities / Total Equity
```

Uses quarter-end standalone values.

## ROE — Quarter

```text
ROE_Q = Quarter PAT / Quarter-End Total Equity
```

No annualization and no TTM history.

## ROA — Quarter

```text
ROA_Q = Quarter PAT / Quarter-End Total Assets
```

No annualization and no TTM history.

## NPM — Quarter

```text
NPM_Q = Quarter PAT / Quarter Revenue or Gross Income
```

For banks, the denominator is Gross Income.

These ratios must use facts from the same issuer, entity scope, quarter and approved extraction context. If the denominator is missing or invalid, the ratio remains blank with an explicit reason.

---

# 4. Final extraction architecture

```text
                         CSE
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
       Market Sources            Quarterly PDFs
             │                         │
             │                         ▼
             │                 Document Reader
             │                         │
             │          PyMuPDF primary extraction
             │                         │
             │                 Quality assessment
             │                 /              \
             │              good              weak
             │               │                 │
             │               │        pdfplumber / Docling
             │               │                 │
             │               │            OCR if needed
             │               └─────────┬───────┘
             │                         ▼
             │              Universal Document IR
             │        words + blocks + coordinates
             │                         │
             │        ┌────────────────┼────────────────┐
             │        ▼                ▼                ▼
             │    Clustering      Spatial Graph        NLP
             │        │                │                │
             │        └────────────────┼────────────────┘
             │                         ▼
             │             Transformer Embeddings
             │                  MiniLM / local CPU
             │                         │
             │                         ▼
             │                 Fact Candidates
             │                         │
             │                         ▼
             │                   Hard Rules
             │                         │
             │                         ▼
             │                 Evidence Scoring
             │                         │
             │                         ▼
             │              Financial Validation
             │                         │
             │                         ▼
             │          Cross-Metric / Cross-Filing QA
             │                         │
             └──────────────┬──────────┘
                            ▼
                     Approved Facts
                            │
                            ▼
                Parquet + JSONL / JSON
                            │
                            ▼
                     Excel Snapshot
```

---

# 5. Universal Document Representation

The primary PDF reader must preserve layout. Each extracted token should contain text, page, x/y coordinates and optional font information.

Flattened text is a fallback source only. Flattened-text fallback must never reintroduce positional assumptions such as `values[-2]`. If column meaning cannot be proven, the value goes to review rather than being guessed.

---

# 6. Dynamic clustering

Use DBSCAN for structure discovery.

Clustering is used to discover:

- visual rows;
- repeated numeric X-regions;
- header regions;
- value groups;
- table-like regions;
- nearby key/value regions.

The ETL never assumes a fixed number of columns. Cluster IDs have no financial meaning until resolved by headers and graph relationships.

---

# 7. Spatial and evidence graph

Use NetworkX or a lightweight in-memory custom graph. No graph database is required.

Possible edges include:

```text
SAME_ROW
ABOVE
BELOW
LEFT_OF
RIGHT_OF
NEAREST_HEADER
PARENT_HEADER
X_OVERLAP
Y_OVERLAP
BELONGS_TO_REGION
HEADER_FOR
UNIT_FOR
ENTITY_FOR
PERIOD_FOR
```

The graph must connect a value to its metric, entity, period, comparison role and unit evidence.

---

# 8. NLP layer

The NLP pipeline uses:

1. normalization;
2. exact aliases;
3. RapidFuzz;
4. pretrained transformer embeddings only when needed.

Normalize case, punctuation, broken whitespace, line breaks, Unicode, OCR noise and common financial abbreviations.

---

# 9. Transformer and vector use

Use a small pretrained Sentence Transformer such as a MiniLM-class model.

- No fine-tuning.
- No model training.
- No external API.
- No LLM.
- No vector database.

The transformer is used only for semantic similarity. It identifies likely financial meaning; it does not choose the financial number.

Vectors remain temporary in RAM and are discarded after processing. Permanent storage contains only the semantic method, semantic target and score.

---

# 10. Candidate-first extraction

The parser preserves all possible candidates before final selection.

For the JKH-style comparison layout, candidates must be classified as CURRENT, COMPARATIVE, CURRENT_YTD, COMPARATIVE_YTD, etc., before selection.

Only the candidate matching the exact target quarter, target year, current role and required standalone entity can be published.

---

# 11. Hard blocking rules

A flow fact is invalid if:

- target period does not match;
- source year does not match target year;
- duration is not exactly 3 months;
- comparison role is not CURRENT;
- entity is not required standalone Company/Bank;
- a cumulative 6M/9M/YTD value is used;
- FY is used as a quarter;
- Q4 is calculated as FY minus 9M;
- unit evidence is missing for absolute monetary facts;
- security class is wrong for security-level market price.

These conditions cannot be overridden by semantic confidence.

---

# 12. Current versus comparative protection

Every candidate must contain:

```text
target_period_end
source_period_end
source_header_year
duration_months
comparison_role
source_header_text
source_region
```

Only `CURRENT` is valid for published quarterly flow facts.

---

# 13. Cross-metric structural consistency

Revenue, Operating Profit, PBT, PAT and EPS for the same quarter should normally resolve through the same semantic context:

```text
COMPANY/BANK
QUARTER_3M
CURRENT
TARGET_YEAR
TARGET_DATE
```

If one metric resolves through a different header/period path, flag `CROSS_METRIC_CONTEXT_INCONSISTENT`.

---

# 14. Unit detection

Unit search order:

```text
cell
↓
row
↓
column/header region
↓
table
↓
statement
↓
page
↓
report
```

Per-share metrics do not inherit ordinary statement thousand/million scaling unless explicitly stated.

If no reliable unit is found, use `UNIT_NOT_RESOLVED`; never silently assume scale 1.

---

# 15. Entity resolution

Entity scope is determined from spatial and semantic evidence.

Supported scopes:

```text
COMPANY
BANK
GROUP
CONSOLIDATED
UNKNOWN
```

Never infer that the right-most column is Company, and never classify an entire page as consolidated-only merely because the word Group appears somewhere.

---

# 16. Multiple presentation styles

The ETL must support:

- table layouts;
- key/value layouts;
- narrative/inline disclosures.

Do not force every page into a traditional table model.

---

# 17. PDF fallback path

```text
PyMuPDF
↓
pdfplumber
↓
Docling when needed
↓
OCRmyPDF + Tesseract when needed
↓
Poppler / pypdf text fallback
```

Fallback changes the extraction technique. It must never relax the financial meaning of the required fact.

---

# 18. Adaptive retry engine

Failures should be diagnosed before retries.

Examples:

```text
PERIOD_NOT_RESOLVED
ENTITY_NOT_RESOLVED
UNIT_NOT_RESOLVED
TABLE_STRUCTURE_UNRESOLVED
COLUMN_CONTEXT_UNRESOLVED
METRIC_NOT_LOCATED
PRICE_LOOKUP_FAILED
```

Each failure triggers the relevant alternate extraction path rather than a generic guess.

---

# 19. Proof of absence

Distinguish:

```text
NOT_FOUND_BY_PARSER
```

from:

```text
SOURCE_CONFIRMED_NOT_REPORTED
```

A source-confirmed missing status can be used only after the correct filing, statement, entity and period were inspected and applicable fallbacks were exhausted.

---

# 20. EPS logic

Extract separately:

```text
EPS_BASIC
EPS_DILUTED
```

Then:

```text
if valid diluted exists for exact current 3M period:
    EPS_SELECTED = EPS_DILUTED
elif valid basic exists for exact current 3M period:
    EPS_SELECTED = EPS_BASIC
else:
    missing
```

Never use 6M, 9M, FY, comparative-year or derived annual-minus-9M EPS.

---

# 21. Quarter-end market price

Priority:

```text
1. Explicit official filing value
2. Official CSE historical value
3. Last valid trading price on or before quarter end
```

Store security symbol, target quarter-end date, actual price date, price and source.

Never substitute the current market snapshot price for a historical quarter-end price.

---

# 22. Quarterly ratio engine

There is no TTM logic.

```text
ROE_Q = Quarter PAT / Quarter-End Equity
ROA_Q = Quarter PAT / Quarter-End Assets
NPM_Q = Quarter PAT / Quarter Revenue or Gross Income
```

For banks, NPM uses quarter Gross Income as the denominator.

All inputs must be approved and belong to the same issuer, entity scope and target quarter.

Possible missing statuses:

```text
INSUFFICIENT_INPUT
ZERO_EQUITY
NON_POSITIVE_DENOMINATOR
INCOMPATIBLE_SCOPE
INCOMPATIBLE_CURRENCY
```

`INSUFFICIENT_HISTORY` is not used for ROE, ROA or NPM.

---

# 23. Validation layers

Every fact goes through:

```text
Extraction validation
↓
Structural validation
↓
Financial validation
↓
Cross-period validation
↓
Cross-filing validation
↓
Publication decision
```

Mandatory checks include correct issuer, statement, metric, entity, target date, target year, exact 3-month duration, current role, unit, numeric sign and evidence lineage.

Financial checks include Assets ≈ Liabilities + Equity and other compatible reconciliations.

---

# 24. Cross-filing validation

Use duplicate evidence across filings where available.

Example:

```text
2024 filing → 2024 current
2025 filing → 2024 comparative
```

These should normally agree unless there is a restatement/reclassification.

A mismatch triggers investigation rather than automatic acceptance.

---

# 25. Confidence and evidence

Store component scores such as:

```text
metric_confidence
layout_confidence
entity_confidence
period_confidence
year_confidence
comparison_role_confidence
unit_confidence
numeric_confidence
validation_confidence
overall_certainty
evidence_completeness
```

Hard-rule failures always override confidence.

---

# 26. File-based storage — no database

Use only:

```text
Parquet
JSONL
JSON
```

Structured datasets live under `data/silver/` and `data/gold/`. Nested evidence and diagnostics use JSONL/JSON.

Temporary parser artifacts live under:

```text
data/tmp/<run_id>/<filing_hash>/
```

Approved high-certainty runs may delete large temporary files. Review/failure cases retain diagnostics.

---

# 27. Atomic file promotion

Every run writes first to:

```text
data/staging/<run_id>/
```

Only after validation passes does staging promote to silver/gold.

Use atomic replacement so failed runs cannot corrupt the last valid output.

---

# 28. Run manifest

Each run records:

```text
run_id
as_of_date
code_version
configuration_hash
start/end timestamps
security count
filing counts
candidate count
approved facts
review facts
confirmed missing facts
parser failures
unit failures
period failures
entity failures
status
```

---

# 29. Final storage layout

```text
data/
├── raw/
│   ├── filings/
│   ├── market/
│   └── manifests/
├── staging/
│   └── <run_id>/
├── bronze/
│   ├── document_metadata/
│   └── extracted_text/
├── silver/
│   ├── issuers/issuers.parquet
│   ├── securities/securities.parquet
│   ├── filings/filings.parquet
│   ├── financial_facts/year=YYYY/
│   ├── market_prices/year=YYYY/
│   └── evidence/year=YYYY/*.jsonl
├── curated/
│   ├── manual_corrections.parquet
│   └── extraction_hints.json
├── gold/
│   ├── current_financial_facts.parquet
│   ├── current_market_prices.parquet
│   ├── derived_metrics.parquet
│   ├── extraction_coverage.parquet
│   └── accuracy_certainty.parquet
├── review/
│   ├── review_queue.parquet
│   └── diagnostics/
└── tmp/
    └── <run_id>/

outputs/
├── workbooks/
├── manifests/
└── logs/
```

---

# 30. Final workbook sheets

The published workbook contains exactly one sheet, `Snapshot_YYYY-MM-DD`. Coverage, review, lineage, prices, gold and definitions are in `dashboard.html` for that run.

The quarterly ratio columns must be labelled:

```text
ROE (Quarter)
ROA (Quarter)
NPM (Quarter)
```

not TTM.

---

# 31. Accuracy, certainty and coverage

These are separate concepts.

- **Coverage:** how much of the required dataset was resolved.
- **Certainty:** how strong the evidence is for each published fact.
- **Accuracy:** how often the system matches manually verified source facts.

Benchmark current/comparative selection, exact-quarter selection, entity selection, unit selection, exact numeric match, market-price resolution, false-missing rate and wrong-populated-value rate.

Wrong populated values are more dangerous than blanks and should receive the strongest QA attention.

---

# 32. Final technology stack

| Area | Technology |
|---|---|
| PDF primary | PyMuPDF |
| PDF secondary | pdfplumber |
| Complex layout fallback | Docling |
| OCR fallback | OCRmyPDF + Tesseract |
| Text fallback | Poppler / pypdf |
| Clustering | scikit-learn DBSCAN |
| Graph | NetworkX or lightweight custom in memory |
| NLP | regex + RapidFuzz |
| Transformer | Sentence Transformers / MiniLM |
| Vectors | NumPy / RAM only |
| Structured storage | Parquet |
| Evidence | JSONL |
| Diagnostics | JSON / JSONL |
| Processing | Polars + PyArrow |
| Numeric | Decimal |
| Output | openpyxl |
| Tests | pytest |
| Database | NONE |
| LLM | NONE |
| Model training | NONE |
| Fine-tuning | NONE |
| GPU required | NO |

---

# 33. Final production principle

The ETL never asks a model: **“What is the PAT?”**

Instead:

```text
NLP / transformer
→ identifies what a label probably means

Clustering
→ discovers visual structure dynamically

Graph
→ connects values to labels, headers, periods, entities and units

Period resolver
→ proves exact current standalone quarter

Entity resolver
→ proves Company/Bank scope

Unit resolver
→ proves currency and scale

Financial rules
→ determine whether the candidate is allowed

Validation
→ checks structural, financial and historical consistency
```

Only then is the fact approved.

## Frozen architecture

> **NLP + pretrained transformer embeddings + transient vectors + DBSCAN clustering + spatial/evidence graph + adaptive PDF fallbacks + deterministic quarterly financial validation + Parquet/JSONL file storage.**

The design is fully local, laptop-friendly, auditable and explainable, and requires no database, LLM, custom model training, fine-tuning or GPU.
