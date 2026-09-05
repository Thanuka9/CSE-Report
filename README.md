# CSE Financial Data Platform

Production-oriented, local-first Python ETL for the Colombo Stock Exchange. One command discovers the live CSE security universe, downloads each issuer's quarterly filings, extracts standalone Company/Bank facts, normalizes units, validates the results, persists audit lineage, and creates a rolling three-quarter Excel workbook.

The pipeline processes every security returned by the official CSE market-capitalization endpoint. It never invents missing figures: unresolved cells contain a typed reason and the underlying evidence appears in `Review_Queue`.

## What the completed run does

```text
CSE market capitalization + issuer filing metadata
  -> immutable PDF cache and SHA-256 hashes
  -> coordinate-preserving document IR + visual-row/column clustering
  -> fuzzy metric / entity / exact-quarter / unit resolution
  -> normalized issuer facts + symbol-specific quarter prices
  -> validation and typed review queue
  -> Parquet/JSONL file store + CSV extracts + 52-column XLSX snapshot
```

Every displayed quarter contains exactly 14 fields:

1. PAT
2. PBT
3. EPS selected (diluted when reported, otherwise basic)
4. NAVPS
5. Operating profit
6. Total equity
7. Total assets
8. Total liabilities
9. Revenue / gross income
10. Market price at quarter end
11. Debt to equity (`Total liabilities / Total equity`), as a multiple
12. ROE
13. ROA
14. NPM

Both basic and diluted EPS remain in audit storage. Flow facts use only an explicitly reported standalone three-month/quarter column, including `4Q`. Cumulative 6M/9M/YTD/FY values remain review evidence and are never converted into a quarter.

## Run in VS Code on Windows

Prerequisites:

- Windows 10/11, macOS, or Linux
- internet access to `www.cse.lk` and `cdn.cse.lk`
- `uv` (manages Python 3.12 and dependencies)
- no database server or JavaScript runtime
- Tesseract/OCRmyPDF only for scanned filings; not required for normal digital PDFs

Open the extracted project folder in VS Code, open a PowerShell terminal, and run:

```powershell
./scripts/bootstrap.ps1
uv run cse-etl run --project-root .
```

On macOS/Linux:

```bash
./scripts/bootstrap.sh
uv run cse-etl run --project-root .
```

The command automatically uses today's market date and the latest three completed calendar-quarter ends. To reproduce the supplied completed run:

```powershell
uv run cse-etl run --as-of 2026-09-04 --periods 2025-12-31,2026-03-31,2026-06-30 --project-root .
```

Generated files appear under `outputs/`:

- `CSE_Financial_Snapshot_<date>.xlsx`
- `normalized_facts_<date>.csv`
- `quarter_end_prices_<date>.csv`
- `review_queue_<date>.csv`
- `pipeline_errors_<date>.json`
- `manifests/run_manifest_<date>.json`

Raw PDFs and API payloads are cached under `data/raw/`; run staging, immutable evidence, partitioned history, current views and review records live under `data/`. Parquet promotion is atomic, so re-running is restartable and reuses cached source files.

VS Code also exposes these tasks through **Terminal -> Run Task**:

- `CSE ETL: Setup`
- `CSE ETL: Test`
- `CSE ETL: Full Run`
- `CSE ETL: Smoke Run (4 issuers)`

## Commands

```bash
uv run cse-etl --help
uv run cse-etl discover-securities
uv run cse-etl detect-unit "all amounts are in Sri Lanka Rupees thousands" --value 16621006
uv run cse-etl run --project-root .
uv run cse-etl run --issuer-limit 4 --project-root .  # safe smoke test
```

## Technology stack

| Layer | Implementation |
|---|---|
| Language/runtime | Python 3.12, managed by `uv` |
| Public-source adapter | Python standard-library HTTP with bounded retries; official CSE endpoints and CDN |
| PDF extraction | PyMuPDF word coordinates, measured pdfplumber coordinate fallback; optional OCRmyPDF/Tesseract for scans |
| Document understanding | Visual-row reconstruction, numeric-column clustering, RapidFuzz aliases; optional local MiniLM semantic matching |
| Transformation | `Decimal` arithmetic and deterministic exact-quarter/entity/unit rules |
| File store | Polars + Parquet partitions, JSONL evidence, atomic staging/promotion and CSV interoperability |
| Reporting | `openpyxl` for the locally generated Excel workbook |
| CLI | Typer |
| Testing/quality | pytest, Ruff, mypy, golden filing fixtures |
| Deployment | Native VS Code/PowerShell first; optional Docker |

Python is the complete runtime. There is no Node application, local/cloud database, paid market-data API, or required AI service. Embeddings are optional and transient; the default extractor runs fully with deterministic coordinate and fuzzy-label logic. Scanned filings trigger OCRmyPDF only when both digital-text engines fail a quality gate, and the original PDF is never overwritten.

## Data rules that fail closed

- Financial scope: Company for ordinary issuers, Bank for banks; Group/Consolidated is not silently substituted.
- Units: closest explicit metric/column/table/statement/page/report unit wins. Currency and scale are stored separately.
- Per-share metrics, counts, percentages, ratios, and ranks never inherit a normal statement scale.
- Exact quarter: flows recognize three-month, quarter and `1Q`-`4Q` headers. Cumulative-only 6M/9M/YTD/FY values remain review evidence and are never published as a quarter.
- Liabilities: publish only the explicit standalone Total Liabilities value. `Assets - Equity` is a reconciliation check only.
- Price: exact security class and filing-disclosed quarter-end/last-traded price first. If official history is unavailable, retain `HISTORICAL_PRICE_NOT_AVAILABLE`.
- ROE, ROA, NPM: same-quarter PAT divided by that quarter's equity, assets, or top line. No prior-period history is required.
- Balance sheet: validate `Assets ≈ Liabilities + Equity` within tolerance.
- Revisions: the current filing is selected for reporting; prior hashes and facts remain in partitioned history.

## Repository structure

```text
cse-financial-data-platform/
├── .vscode/                 # runnable VS Code tasks and debugger profile
├── configs/                 # metric, unit, issuer and validation rules
├── data/
│   ├── raw/                 # CSE JSON and immutable filing cache
│   ├── bronze/              # transient/document-intermediate artifacts
│   ├── silver/              # partitioned filings, facts, derived ratios, prices and evidence
│   ├── gold/                # current Parquet views and extraction scorecards
│   ├── staging/             # atomic per-run write area
│   ├── review/              # typed review queue
│   ├── curated/             # approved manual corrections
│   └── quarantine/          # recoverable failed/corrupt artifacts
├── docs/                    # specification, architecture and operator runbook
├── outputs/                 # generated workbook, CSVs and run manifests
├── scripts/                 # Windows and POSIX setup helpers
├── src/cse_financial_etl/
│   ├── documents/           # coordinate IR and measured PDF fallbacks
│   ├── domain/              # enums and data contracts
│   ├── extraction/          # statements, units and quarter prices
│   ├── orchestration/       # complete restartable pipeline
│   ├── reporting/           # 14-field rolling-quarter workbook
│   ├── sources/             # CSE API/CDN adapter
│   ├── storage/             # Parquet/JSONL repository and CSV exports
│   ├── transformation/      # normalization rules
│   └── validation/          # validation package boundary
└── tests/                   # unit and regression tests
```

See `docs/production_specification.md` for the frozen contract and `docs/operator_runbook.md` for operating and review steps.
