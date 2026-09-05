# Operator runbook

## First setup in VS Code

1. Extract the project ZIP and open `cse-financial-data-platform` as the VS Code folder.
2. Install `uv`. The locked Python environment includes both coordinate-aware PDF engines. OCRmyPDF/Tesseract are optional; when installed, the pipeline OCRs a filing only if both digital-text engines fail the quality gate, and it never overwrites the original PDF.
3. Run **Terminal -> Run Task -> CSE ETL: Setup**, or execute `./scripts/bootstrap.ps1` on Windows.
4. Confirm all tests and Ruff checks pass.
5. Run **CSE ETL: Smoke Run (4 issuers)** before the first full run.
6. Run **CSE ETL: Full Run**.

## Normal run

```powershell
uv run cse-etl run --project-root .
```

The command uses today's market snapshot and the latest three completed calendar-quarter ends. Prior quarters are downloaded only when needed to derive an exact Q4 flow from compatible cumulative filings.

To specify dates:

```powershell
uv run cse-etl run `
  --as-of 2026-09-04 `
  --periods 2025-12-31,2026-03-31,2026-06-30 `
  --project-root .
```

## What to check after every run

1. Open `outputs/manifests/run_manifest_<date>.json` and confirm `pipeline_error_count` is zero.
2. Open the workbook's `Accuracy_Certainty` and `Checks` sheets.
3. Confirm golden-fixture accuracy is 100% and `UNIT_NOT_DETECTED` has not regressed.
4. Review `Review_Queue`; filter blocking reasons first.
5. Confirm high-value issuers in `Audit_Lineage`, especially entity scope, period, page, unit and normalized value.
6. Review `Price_Lineage` for voting/non-voting class selection.
7. Archive the workbook, manifest and review queue together.

`REVIEW` is expected only when the filing genuinely does not expose an approved standalone Company/Bank value, a compatible exact/derivable quarter, or a filing-disclosed class-specific quarter-end price. It is not permission to guess a number.

## Important rules

- Never copy a full-year value into a Q4 field.
- Derive a cumulative-only Q4 only when all normalized inputs have the same issuer, entity scope, currency, accounting period basis and validated three-month predecessors; never derive EPS.
- Never substitute Group/Consolidated for Company/Bank silently.
- Never multiply EPS, NAVPS, prices, counts, percentages, ratios or ranks by a statement scale.
- Never use today's price for a historical quarter-end price.
- Never turn a missing source value into zero.
- Do not manually edit generated facts and then use the workbook as the next run's source.

## Restart and cache behavior

Downloaded PDFs are content-hashed and cached. A rerun reuses them. Current filing versions drive the report, while prior run partitions and source hashes remain in `data/silver/` and `data/raw/`.

If a machine stops during a run, keep `data/raw/`, move only the affected run directory from `data/staging/<run-id>/` into a dated folder under `data/quarantine/`, and rerun. Gold files are promoted with a temporary-file replacement only after a successful run.

```text
data/staging/<incomplete-run-id>/
```

Do not delete `data/raw/filings`; it avoids repeating the network download.

## Output files

| File | Purpose |
|---|---|
| `CSE_Financial_Snapshot_<date>.xlsx` | User-facing 14-field rolling-quarter report |
| `normalized_facts_<date>.csv` | Long-form issuer facts and audit fields |
| `quarter_end_prices_<date>.csv` | Symbol-specific filing prices and evidence |
| `review_queue_<date>.csv` | Typed unresolved and validation states |
| `pipeline_errors_<date>.json` | Operational exceptions only |
| `manifests/run_manifest_<date>.json` | Counts, periods, run ID and output locations |
| `data/gold/current_financial_facts.parquet` | Current normalized issuer facts |
| `data/gold/current_market_prices.parquet` | Current class-specific historical prices |
| `data/gold/accuracy_certainty.parquet` | Coverage, certainty and measured fixture accuracy |
| `data/silver/` | Partitioned filing/fact/price/evidence history |

## Release checks

```powershell
uv run pytest
uv run ruff check src tests
uv run mypy src
```

The workbook may be distributed only with its manifest and review queue so recipients can distinguish extracted facts from unavailable or unapproved cells.
