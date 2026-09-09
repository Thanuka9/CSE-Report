# CSE Financial Data Platform

Production-oriented, local-first Python ETL for the Colombo Stock Exchange. The governed production entrypoint discovers the live CSE security universe, verifies issuer filing metadata and PDF revisions, extracts standalone Company/Bank quarterly facts, normalizes units, validates the results, persists audit lineage, runs full-universe acceptance, and only then activates an accepted gold generation.

The pipeline processes every security returned by the official CSE market-capitalization endpoint. It never invents missing figures: unresolved cells contain a typed reason and the underlying evidence appears in the review outputs.

## Production data flow

```text
CSE market capitalization + fresh issuer filing metadata
  -> immutable revision-safe PDF versions + SHA-256 provenance
  -> coordinate-preserving document IR + visual-row/column clustering
  -> A/B evidence + metric/entity/exact-quarter/unit resolution
  -> bounded Resolver C for compatible ambiguities
  -> normalized issuer facts + symbol-specific quarter prices
  -> accounting validation + typed review queue
  -> immutable staging generation
  -> full-universe acceptance (cardinality + global + metric + sector/metric gates)
  -> accepted DRAFT/OFFICIAL gold pointer promotion
  -> Parquet/JSONL + CSV + optional XLSX outputs
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
11. Liabilities / Equity (`Total liabilities / Total equity`), as a multiple
12. ROE
13. ROA
14. NPM

The historical internal metric code for field 11 remains `DEBT_TO_EQUITY` for schema compatibility, but production metadata and human-facing output state its actual accounting definition explicitly. It is not an interest-bearing corporate debt/equity measure and is not the Basel bank leverage ratio.

Both basic and diluted EPS remain in audit storage. The core quarter model is unchanged: flow facts use only an explicitly reported standalone three-month/quarter context, including `4Q`. Cumulative 6M/9M/YTD/FY evidence remains separately identified and is never silently published as a three-month quarter.

## Governed production run

Prerequisites:

- Windows 10/11, macOS, or Linux
- internet access to `www.cse.lk` and `cdn.cse.lk`
- `uv` and Python 3.12
- Tesseract/OCRmyPDF for the complete universe because scanned filings exist

Bootstrap the locked environment using the platform helper, then run the governed production entrypoint. For a live run, `--as-of` must be the actual `Asia/Colombo` observation date; historical backfills must use explicit offline/historical inputs.

```bash
uv run python scripts/run_production_pipeline.py \
  --as-of YYYY-MM-DD \
  --process-timeout-seconds 480 \
  --tunnel-b-always
```

The GitHub **Full universe acceptance** workflow invokes this production entrypoint and resolves a blank date to the current `Asia/Colombo` date.

Production-specific protections include:

- configured CSE request-rate enforcement, bounded retries, jitter and `Retry-After` handling;
- no silent stale metadata fallback during online production;
- immutable content-addressed filing revisions;
- no live market snapshot masquerading as historical quarter-end price evidence;
- process-isolated PDF/OCR extraction with exact known-timeout quarantine only;
- unsigned legacy manual corrections blocked from production;
- universe/cardinality/global/per-metric/sector×metric regression gates;
- gold pointer promotion only after universe acceptance;
- DRAFT allowed after engineering acceptance while external proof is pending;
- OFFICIAL blocked until independent proof and authenticated review requirements pass.

Generated production evidence under `outputs/` includes:

- `CSE_Financial_Snapshot_<date>.xlsx` when Excel generation is enabled
- `normalized_facts_<date>.csv`
- `quarter_end_prices_<date>.csv`
- `review_queue_<date>.csv`
- `pipeline_errors_<date>.json`
- `universe_acceptance_<date>.json`
- `issuer_master_<date>.json`
- `metric_definitions_<date>.json`
- `manifests/run_manifest_<date>.json`

Raw PDFs and API payloads are stored under `data/raw/`; run staging, immutable evidence, partitioned history, current views and review records live under `data/`. Gold snapshots use immutable generation directories selected through `data/gold/CURRENT.json` only after acceptance.

## Research, regression and smoke execution

The original CLI and resilient runner remain available for development, tests, explicit replay and smoke runs. They are not the governed production release boundary.

```bash
uv run cse-etl --help
uv run cse-etl discover-securities
uv run cse-etl detect-unit "all amounts are in Sri Lanka Rupees thousands" --value 16621006
uv run cse-etl run --issuer-limit 4 --project-root .
uv run python scripts/run_resilient_pipeline.py --as-of YYYY-MM-DD --offline
```

This separation preserves backward-compatible research workflows while making the release-authoritative path unambiguous.

## Technology stack

| Layer | Implementation |
|---|---|
| Language/runtime | Python 3.12, managed by `uv` |
| Public-source adapter | Python standard-library HTTP; governed production rate limiter/retries over official CSE endpoints and CDN |
| PDF extraction | PyMuPDF word coordinates, measured pdfplumber coordinate fallback; OCRmyPDF/Tesseract for scans |
| Document understanding | Visual-row reconstruction, numeric-column clustering, RapidFuzz aliases; no LLM publication path |
| Resolution | A/B evidence plus bounded constraint-based Resolver C with abstention |
| Transformation | `Decimal` arithmetic and deterministic exact-quarter/entity/unit rules |
| File store | Polars + Parquet partitions, JSONL evidence, immutable staging/promotion and CSV interoperability |
| Reporting | `openpyxl` for the locally generated Excel workbook |
| CLI | Typer plus governed production script |
| Testing/quality | pytest, Ruff, mypy, real/golden filing fixtures, Linux + Windows CI |
| Deployment | Native Python/VS Code; optional Docker |

Python is the complete runtime. There is no Node application, required local/cloud database, paid market-data API, vector database, or required AI service. The extractor uses deterministic coordinates and fuzzy-label matching; scanned filings trigger OCR only through the document-quality recovery path and the original verified PDF version is preserved.

## Data rules that fail closed

- **Quarter context:** flows distinguish three-month/quarter/`1Q`-`4Q` values from cumulative 6M/9M/YTD/FY contexts. Existing Q1/Q2/Q3/Q4 and 3/6/9/12-month handling remains the core contract.
- **Financial scope:** Company for ordinary issuers, Bank for banks; Group/Consolidated is not silently substituted.
- **Units:** closest explicit metric/column/table/statement/page/report unit wins. Currency and scale are stored separately.
- **Per-share metrics:** counts, percentages, ratios and ranks never inherit a normal statement scale.
- **Liabilities:** publish only an explicit standalone Total Liabilities value. `Assets - Equity` is a reconciliation check only.
- **Price:** filing-disclosed quarter-end/last-traded price first; governed historical fallback uses explicit CSE historical evidence on or before quarter end, never a later live market snapshot.
- **ROE, ROA, NPM:** same-quarter PAT divided by that quarter's equity, assets or top line according to the existing deterministic rules.
- **Balance sheet:** validate `Assets ≈ Liabilities + Equity` within tolerance.
- **Revisions:** current CSE filing metadata selects the reporting version; production verifies the PDF bytes and retains prior content hashes rather than overwriting them.
- **Manual overrides:** unsigned `manual_corrections.parquet` values cannot become production `CURATED/PASSED` facts.
- **Release:** unresolved/failed evidence cannot publish; OFFICIAL additionally requires governed review/proof.

## Repository structure

```text
cse-financial-data-platform/
├── .github/workflows/       # deterministic CI and dispatch-only full-universe production acceptance
├── configs/                 # metric, unit, issuer, validation and coverage contracts
├── data/
│   ├── raw/                 # CSE JSON and immutable/versioned filing sources
│   ├── bronze/              # document intermediates and OCR artifacts
│   ├── silver/              # partitioned filings, facts, derived ratios, prices and evidence
│   ├── gold/                # immutable accepted snapshots + CURRENT pointer
│   ├── staging/             # per-run candidate generations before acceptance
│   ├── review/              # review queue and governed review decisions
│   ├── curated/             # legacy corrections file; non-empty file is blocked in production
│   └── quarantine/          # failed/corrupt/reviewable artifacts
├── docs/                    # specification, architecture, QA and operator contracts
├── outputs/                 # run artifacts and acceptance evidence
├── scripts/                 # bootstrap, research runners and governed production runner
├── src/cse_financial_etl/
│   ├── compiler/            # canonical statement compilation
│   ├── constraints/         # accounting/structural constraints
│   ├── documents/           # coordinate IR and measured PDF fallbacks
│   ├── extraction/          # source facts, units and quarter prices
│   ├── orchestration/       # stable restartable quarterly pipeline
│   ├── production/          # production-only safety/release boundary
│   ├── resolution/          # bounded Resolver C
│   ├── reporting/           # workbook/dashboard generation
│   ├── sources/             # CSE source adapters
│   ├── storage/             # Parquet/JSONL repository and atomic gold generations
│   ├── transformation/      # normalization and derived metrics
│   └── validation/          # validation, calibration and universe acceptance
└── tests/                   # unit, integration and real-PDF regression tests
```

See `docs/production_specification.md` for the frozen extraction contract, `docs/operator_runbook.md` for operating/review steps, and [R3 Production Hardening](docs/R3_PRODUCTION_HARDENING.md) for the governed production boundary. R2 completion evidence remains documented in [Completion QA](docs/R2_Completion_QA_2026-09-09.md).
