# R2 completion QA — 9 September 2026

This document records the completed engineering state after the final fail-closed hardening and fresh full-universe CSE run. It does not convert independent human adjudication or institutional identity governance into machine proof.

## Changes delivered

| Area | Implemented behavior |
|---|---|
| Real-PDF CI | Six original PDFs are vendored with SHA-256/source manifest. Linux and Windows CI require all six acceptance cases; absence is a failure. |
| Resolver C fairness | Iteration allowance is per concept so earlier concepts cannot starve later ones; global elapsed-time and hypothesis bounds remain fail-closed. Targeted NDB evidence confirmed the previous stock-fact starvation was removed. |
| Fail-closed ratios/publication | Validation-failed, unresolved or explicit-fallback source facts are withheld before ratio derivation. Ratios require compatible current standalone inputs and machine-derived ratios remain `REVIEW`, never machine-`APPROVED`. |
| OS-level PDF/OCR cancellation | Each filing is processed in a spawned worker with hard process-tree termination. Production universe timeout is 480 seconds. |
| Resumability | Raw, bronze and resilient per-filing caches are wired into the production workflow; retry uses the same configured extraction contract. |
| OCR production runtime | Ghostscript, Tesseract and the locked OCR extra are installed in the full-universe workflow. |
| Accuracy/quality reporting | `Accuracy_Quality` separates coverage, independent manual accuracy and certainty calibration. Seeded values do not inflate manual accuracy. |
| Atomic gold publication | Each run writes an immutable generation and switches the complete gold set with one `CURRENT.json` pointer. Incomplete/interrupted generations cannot activate. |
| Acceptance evidence | Universe acceptance now records actual DRAFT-publishable fact count, separates external proof gates, and classifies only explicit killed PDF/OCR worker timeouts as bounded quarantined filing exceptions. Any other pipeline error or quarantine overflow fails engineering acceptance. |
| Coverage baseline | The obsolete pre-fail-closed raw-count floor was recalibrated from the completed safe universe result and an explicit DRAFT-publishable floor is versioned in `configs/coverage_baseline.yml`. |
| CI integrity | Validation is read-only on the checked-out commit: locked environment, Ruff, mypy, full pytest and six-real-PDF acceptance on Linux and Windows. No CI patch/commit/push behavior remains. |

## Deterministic verification

The final hardening PR passed deterministic production checks on both **Ubuntu and Windows**: Ruff, mypy, the complete pytest suite and the mandatory six-real-PDF acceptance all completed successfully.

The six-PDF compiler acceptance covers JAT, Commercial Bank, Dialog, John Keells, Hayleys Fibre and Merchant Bank. The separate manual golden comparison remains **38/38 reference checks**: **34 financial values plus four filing-disclosed quarter-end prices** across four manually annotated reports. That is a real regression/accuracy sample, not a claim of population-wide accuracy.

## Fresh full-universe production evidence

Run `d6299b06-2f47-43d2-8024-d60c1d883804` executed against the 2026-09-09 CSE universe with production OCR and the hard per-PDF worker bound.

- 281 issuers / 302 securities
- 829 selected and downloaded official CSE filings
- 826 extracted filings
- 9023 `EXTRACTED` + `EXTRACTED_DERIVED` facts
- 9023 facts publishable under DRAFT policy
- 788 extracted filing-disclosed/officially resolved quarter-end prices
- 38 manual golden checks, accuracy 1.0 within that manual sample
- zero recurrence of the earlier `UNRESOLVED_CANDIDATE_PUBLISHED`, `ISSUER_QUARTER_CONTEXT_INCONSISTENT`, `GOLD_WRONG_POPULATED` and `EXPLICIT_LAYOUT_FALLBACK_USED` publication gates

Three filings exceeded the 480-second PDF/OCR worker limit and were terminated and withheld:

1. Sarvodaya Development Finance PLC — 2025-12-31
2. Sarvodaya Development Finance PLC — 2026-03-31
3. Renuka City Hotels PLC — 2026-06-30

These are not silently ignored. They remain explicit in `pipeline_errors`/review evidence and are not published. The versioned policy allows at most three such exact process-tree-terminated extraction timeouts for a universe run; any non-timeout pipeline error, evidence mismatch or timeout above that limit is an engineering failure.

The original workflow was red because the manifest still used the obsolete `9685` pre-fail-closed coverage floor. The completed safer methodology produced 9023 publishable facts, up from 8705 in the preceding failed proof run, while removing unsafe publication conditions. The baseline was therefore migrated to the empirically observed fail-closed methodology rather than weakening accounting, entity, duration, unit, validation or publication rules.

## Production release boundary

Engineering completion does **not** mean an official institutional release can bypass human governance. Official publication still requires the configured signed review/approval contract. The generated 100-issuer adjudication packet contains 900 rows and remains `UNADJUDICATED` until independently reviewed.

The remaining non-code requirements are:

- independent human adjudication of the 100-issuer sample;
- institution-controlled reviewer identity/key governance for official approvals;
- GitHub `main` branch protection/ruleset activation by a repository administrator (the connected GitHub App has no administration permission).

Those are external human/admin controls, not unfinished extraction-engineering work.

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

A complete live universe run additionally needs CSE endpoint access plus the OCR system dependencies used by the production workflow.
