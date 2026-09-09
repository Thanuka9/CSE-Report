# R3 Production Hardening

## Status and scope

R3 hardens the production boundary around the existing quarterly CSE extraction design. It does **not** redesign the financial extraction/compiler/resolver or change the established quarter model.

The following invariants are retained:

- Financial facts remain quarter-based.
- Flow context continues to distinguish exact 3-month quarter values from 6/9/12-month cumulative contexts.
- Q1/Q2/Q3/Q4 handling and the existing current/comparative rules remain in the core extractor.
- A/B evidence generation and Resolver C remain the extraction/resolution architecture.
- Unresolved evidence remains fail-closed; no model or correction path may manufacture a publishable value.

Production runs must use:

```bash
uv run python scripts/run_production_pipeline.py --as-of YYYY-MM-DD --tunnel-b-always
```

The legacy resilient runner remains available for research, regression and explicit replay compatibility. It is not the governed production release entrypoint.

## Production release boundary

A production run now follows this order:

1. Fetch/verify CSE sources.
2. Execute the existing resilient quarterly ETL.
3. Write an immutable staging generation; do **not** move the gold pointer.
4. Run per-filing validation and universe acceptance.
5. Classify only explicitly known pathological filing timeouts as quarantine exceptions.
6. Check universe cardinality, global coverage, per-metric coverage and sector × metric coverage.
7. Move `data/gold/CURRENT.json` only if production acceptance permits promotion.

DRAFT may be promoted after engineering acceptance while independent human proof is pending. OFFICIAL cannot be promoted until both engineering acceptance and the configured external proof gates pass.

## Manual corrections

`data/curated/manual_corrections.parquet` is a legacy research mechanism and is blocked when non-empty in the governed production runner. It cannot convert an unsigned manual value into `CURATED/PASSED` production data.

Official release decisions remain source-bound to the exact filing SHA-256 and authenticated through the review-decision contract. A value correction must therefore be resolved at the source/extraction layer and rerun through validation, rather than mutating gold after the equations and gates have run.

## Source integrity

Online production execution requires `--as-of` to equal the current calendar date in `Asia/Colombo`. This prevents a live market observation from being stored under a historical date. Historical backfills must be explicit offline/historical replays.

Online filing metadata is strict: a failed live CSE metadata request cannot silently fall back to an old cache and pretend to be fresh production input.

Filing PDFs are verified online and stored as immutable content-addressed versions using the filing ID and SHA-256. A current-pointer JSON records source URL/path, CSE upload/authorization times, hash and verification time. If CSE revises a filing, the old bytes remain preserved and the new hash receives a new version.

Quarter-end price recovery in production does not use a current/live market-cap snapshot as historical evidence. It accepts explicit historical CSE price data on or before the target quarter end; otherwise the price remains unavailable/reviewable.

## CSE request discipline

The production runtime enforces the configured `http.requests_per_second` rate across CSE API POST requests and retains bounded retries, exponential backoff, jitter and `Retry-After` handling. The configuration is no longer informational/dead state.

## Coverage contract

The accepted 2026-09-09 universe is the initial R3 regression baseline:

- 281 issuers
- 829 downloaded filings
- at least 826 successfully extracted filings, with exactly three known timeout-quarantined filing identities
- 9,023 DRAFT-publishable facts

The 9,023 aggregate floor is not sufficient by itself. `configs/coverage_baseline.yml` also contains per-metric and sector × metric floors derived from the same accepted evidence. This prevents improvement in one metric or sector from hiding a regression in another.

The three known timeout quarantines are explicitly identified by issuer, symbol and period. A newly timing-out filing is an engineering failure even if the total number of timeouts is no more than three.

## Issuer classification

Each production run writes `outputs/issuer_master_<as_of>.json`, recording every observed issuer/symbol, the issuer type and standalone scope actually used, and whether that classification came from an explicit configuration or deterministic inference. This makes the remaining heuristic classification visible and auditable instead of implicit.

## Leverage metric semantics

The historical internal code `DEBT_TO_EQUITY` is retained for schema compatibility. Its implemented formula is:

```text
TOTAL_LIABILITIES / TOTAL_EQUITY
```

Therefore production human-facing output labels it **Liabilities / Equity**, not generic corporate Debt / Equity. `outputs/metric_definitions_<as_of>.json` records this definition and explicitly states that the metric is neither interest-bearing corporate debt/equity nor the Basel bank leverage ratio.

## CI and supply-chain controls

Deterministic CI continues on both Ubuntu and Windows and now includes the production-hardening test contract. GitHub Actions used by the production workflows are pinned to reviewed commit SHAs and the uv tool version is pinned. The locked Python environment remains mandatory.

## Remaining institutional prerequisites for OFFICIAL release

Code can enforce the contract, but some controls remain operational/institutional by design:

- complete the configured 100-issuer independent human adjudication;
- provision and control reviewer signing keys outside the repository;
- enable GitHub branch protection/rules for `main` with required deterministic CI checks and review policy appropriate to the institution;
- maintain the explicit issuer classification master as CSE issuer/sector metadata becomes available;
- add a CSE XBRL adapter when the exchange exposes stable production XBRL access, without removing PDF provenance or the existing validation layer.

Until the independent human proof gates are complete, production DRAFT is engineering-accepted but is not an OFFICIAL governed financial release.
