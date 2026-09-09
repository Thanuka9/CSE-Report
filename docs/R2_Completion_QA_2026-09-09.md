# R2 completion QA — 9 September 2026

This change builds on the user's latest `4e66c539a5a1addf9781d402270230827558023e` commit. It preserves that compiler architecture and completes the outstanding integration work identified in its checklist. The earlier experimental fix branch is not merged.

## Changes delivered

| Remaining item | Implemented behavior |
|---|---|
| Real-PDF tests skipped in CI | Six original PDFs are included under `tests/fixtures/pdf/`, with SHA-256/source manifest. CI requires all six acceptance cases; absence is a failure. |
| Search settings not driving Resolver C | The filing's ResourceBudget now reaches the candidate search. Shared iteration/time limits and beam width are enforced. Width one cannot erase a conflicting runner-up and fabricate certainty. Budget-stopped candidates stay withheld through final arbitration. |
| StageCache not called | Native ingestion reads/writes versioned geometry JSON using source hash, extractor source-code digest and PDF-library versions. Accounting decisions are recomputed; changed source bytes invalidate the cache. |
| Accuracy_Quality not called | Every generated workbook receives the sheet. Coverage uses issuer × requested period × nine metric cells, including missing cells. Independent accuracy, coverage and uncalibrated certainty are separate measures. |
| Optional MiniLM dependency | Removed the sentence-transformers extra and corrected README/setup instructions. No language-model service is introduced. |
| CI patched and pushed its own code | Replaced with read-only checks on Linux and Windows, a locked environment, lint, type checks, tests and mandatory six-PDF acceptance. No auto-patching, commits or pushes. |
| Gold context / accuracy denominator | Manual financial fixtures now include expected scope/date/role/currency/scale and flow duration. Context is checked with the numeric value. Only MANUAL_QA contributes to headline accuracy; seeded values remain separate regression anchors. |
| Multi-file gold promotion | Each run writes an immutable generation. One atomic `CURRENT.json` pointer switches the complete gold set. Consumers resolve the pointer once. Interrupted/incomplete activation retains the preceding generation. Existing flat snapshots remain readable until the first generation is activated. |
| Build defects | Fixed typing errors, an invalid OCR-quality attribute, and string/int filing ID comparisons in replacement persistence. Updated two obsolete tests to the new absence and manual-sample semantics. |

## Verification

Local Python 3.12 validation: **185 tests passed, 19 skipped, 15 subtests passed**. Ruff passes; mypy reports no issues in 125 source files under the existing project configuration. The 19 skipped legacy tests still require raw filing-lake paths; some overlap the bundled reports. All six dedicated bundled-PDF acceptance cases ran. Windows CI is configured but has not been executed in this local environment. See [validation.json](../reports/r2_completion_2026-09-09/validation.json).

## Source checks

The six-PDF compiler acceptance passes for JAT, Commercial Bank, Dialog, John Keells, Hayleys Fibre and Merchant Bank. These tests require compiler-origin core metrics, correct standalone Company/Bank scope, current reporting date and exact three-month flow context, with no explicit fallback.

The separate golden comparison passes **38/38 manual reference checks**: **34 financial values plus four filing-disclosed quarter-end prices**, across the four manually annotated reports. Its output is [source_comparison.json](../reports/r2_completion_2026-09-09/source_comparison.json). Two additional filings are structural acceptance cases, not independently annotated numeric accuracy samples. Four supplied PDFs were retained unchanged; the two missing acceptance PDFs were downloaded from CSE's CDN for this work.

These results do not establish 100% accuracy across listed companies, reporting periods, scans or restatements. This change does not include a fresh full-universe run. The production minimum-gold-sample gate remains in force; reducing an integration-test denominator from seeded issuers to the actual manual sample does not relax that release gate.

## Run locally

```powershell
uv sync --locked --group dev
uv run ruff check src
uv run mypy src
uv run pytest
$env:CSE_REQUIRE_FIXTURES = "1"
uv run pytest tests/regression/redesign/test_compiler_real_pdfs.py
uv run cse-etl validate-golden --project-root . --as-of 2026-09-09
uv run cse-etl run --project-root .
```

Full live runs need access to CSE endpoints. The bundled native PDF checks need no CSE download. OCR tools remain optional external prerequisites for scans.

## Remaining acceptance work

Institutional reviewer identities, authenticated approval integration and human adjudication of the wider issuer sample are external acceptance requirements. A nonempty reviewer ID in the existing local decision API is not proof of authentication; this change does not certify that API as an institutional identity service. Confidence calibration, wider scan/layout validation and a fresh full-universe run remain necessary before claiming production accuracy. Resource limits bound the resolver's work; they are not operating-system memory limits or cancellation of a blocked PDF/OCR process. Cache support added here covers native ingestion, not resumability of every ETL stage. Atomicity covers the gold generation; the separate silver/history writes are not one transaction.
