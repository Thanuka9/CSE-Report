# R4 Regulatory and Semantic Hardening

## Status

R4 is a file-backed hardening layer on top of the proven CSE quarterly extractor. It does **not** introduce a database and it does **not** implement XBRL. XBRL remains explicitly disabled until an official CSE production interface/taxonomy is actually available for use.

This document is authoritative where it is stricter than older R2/R3 wording. In particular, R4 supersedes any earlier text that suggested either of the following could populate the reported-quarter output:

- deriving `TOTAL_LIABILITIES` as `TOTAL_ASSETS - TOTAL_EQUITY`;
- deriving a reported Q4 base-flow value from FY/YTD arithmetic.

Both are now non-publication rules: liabilities require explicit standalone source evidence, and displayed quarter flows require an explicitly reported standalone three-month value.

## Implemented controls

### 1. Persistent issuer/security identity without a database

Every governed run writes and refreshes `data/master/issuer_security_master.json` plus `outputs/issuer_security_master_<date>.json`.

- issuer IDs are anchored to CSE security identity rather than company-name text;
- the same `security_id` retains its issuer relationship through legal-name/symbol changes;
- symbol history, security class, trading currency and active dates are retained;
- legal names remain attributes, not join keys;
- current canonical issuer IDs replace name-as-ID values in the staged `issuers.parquet` before promotion.

### 2. Listing-segment-aware disclosure calendar

`outputs/expected_disclosures_<date>.json` records, per issuer and requested reporting period, the expected filing/disclosure class, due date and due-state.

Configured policy distinguishes Main and Empower reporting expectations. If the CSE source does not expose a listing segment and no explicit override exists, the system records `SEGMENT_UNKNOWN_REVIEW_REQUIRED`; it does not guess a board from the issuer name.

### 3. Reported-quarter-only flow policy

The production boundary requires every publishable flow fact to carry a three-month duration. Six-, nine- and twelve-month cumulative facts cannot populate a quarter.

Underlying reported flows (`TOP_LINE`, `OPERATING_PROFIT`, `PBT`, `PAT`, basic/diluted EPS) cannot be published as a derived Q4 fact. A mathematically derived Q4 may exist as analytic/audit evidence in future, but it is not the reported quarterly value.

`EPS_SELECTED` remains the existing deterministic selector: valid diluted EPS is preferred; otherwise valid basic EPS is used. The selector itself is not treated as a prohibited Q4 arithmetic derivation.

### 4. Accounting-regime and source-metric semantics

`outputs/fact_semantics_<date>.jsonl` carries semantic metadata alongside the stable fact schema:

- canonical metric code;
- exact top-line basis (`REVENUE`, `GROSS_INCOME`, `INSURANCE_REVENUE`, `GROSS_WRITTEN_PREMIUM`, `NET_EARNED_PREMIUM`, etc.);
- accounting-presentation/regime evidence;
- ratio definition.

Insurance labels are retained as distinct concepts during the 2026 SLFRS 4/SLFRS 17 transition rather than being treated as interchangeable economic definitions.

### 5. Last-traded price contract

The governed quarter-end price means **last traded price for the interim period**.

- filing extraction is accepted only when the value has last-traded context;
- explicit closing/closing-market-price values are rejected as substitutes;
- ambiguous generic market-price rows are withheld;
- historical fallback accepts official trade/last-traded observations on or before the reporting date;
- generic `closing_price`/`close` fields do not satisfy the production resolver.

The actual trade observation date remains visible in the historical evidence/source line, so illiquid securities are not made to look as if they traded exactly on quarter end.

### 6. CBSL bank profile

Bank facts remain standalone `BANK` scope. The R4 boundary additionally enforces:

- exact three-month duration for the quarterly output;
- `Operating profit before taxes on financial services` as the accepted bank operating-profit basis;
- an `after taxes on financial services` line cannot substitute for it;
- explicit `nil` may be normalized to zero only on a verified exact-quarter Bank statement with a resolved statement unit;
- a blank or dash is never converted to zero;
- cumulative/YTD `nil` does not become a quarterly zero.

### 7. Metric semantics cleanup

The legacy internal code `DEBT_TO_EQUITY` remains for schema/backward compatibility, but the canonical semantic name is `LIABILITIES_TO_EQUITY` and the human-facing label is **Liabilities / Equity**.

`outputs/metric_definitions_<date>.json` now also records:

- ROE = same-quarter PAT / quarter-end total equity;
- ROA = same-quarter PAT / quarter-end total assets;
- NPM = same-quarter PAT / same-quarter top line;
- total liabilities = explicit standalone source row only;
- assets minus equity = reconciliation only;
- quarter-end market price = last-traded semantics, not closing-price semantics.

### 8. Stronger independent adjudication sample

The 100-issuer packet is no longer selected only by issuer type and latest period. R4 deterministically round-robins across **issuer type × quarter** and prefers difficult evidence within each bucket, including OCR, withheld/missing facts and nonstandard scope.

The packet and its manifest expose quarter counts and difficulty-flag counts. Human fields remain empty and machine values still cannot certify themselves.

### 9. Exact API evidence, schema fingerprinting and broader period parsing

Every live market-capitalization request archives the exact JSON payload before compatibility conversion and writes `outputs/cse_api_contract_<date>.json` containing the observed fields and a deterministic schema fingerprint.

This provides an exact-decimal/raw evidence boundary even though legacy in-memory/reporting compatibility fields still use Python numeric types downstream.

Filing-title period parsing now supports long English month names/abbreviations, ISO dates and Sri Lankan day/month/year numeric dates. Numeric dates are never silently interpreted using US month/day order.

### 10. Hash-bound timeout quarantine

The three historically accepted timeout identities are migrated to `data/quarantine/known_timeout_pins.json` on their first verified R4 observation. Each pin includes filing ID and SHA-256.

After a pin exists, a different filing ID or hash invalidates the quarantine. R4 appends a `QUARANTINE_INTEGRITY` pipeline error, which is not part of the known-timeout allowlist and therefore makes universe acceptance fail closed.

## Production order

```text
CSE sources
  -> exact raw/API contract archive
  -> existing extraction/compiler/resolver
  -> R4 runtime guards (period, bank, reported-quarter, last-traded)
  -> validation/ratio derivation
  -> R4 repository hardening
  -> canonical identity + disclosure + semantic sidecars
  -> hash-bound quarantine integrity
  -> rewrite candidate CSV + immutable staging generation
  -> full-universe acceptance
  -> gold promotion only if accepted
```

The existing PDF/OCR/compiler architecture remains unchanged. R4 is intentionally a production boundary rather than a second extraction engine.

## R4 outputs

A governed run can additionally produce:

- `outputs/r4_hardening_<date>.json`
- `outputs/issuer_security_master_<date>.json`
- `outputs/expected_disclosures_<date>.json`
- `outputs/fact_semantics_<date>.jsonl`
- `outputs/cse_api_contract_<date>.json`
- `outputs/quarantine_integrity_<date>.json`
- `data/master/issuer_security_master.json`
- `data/quarantine/known_timeout_pins.json`

These are local files. No database service is required.

## Deliberately excluded

- XBRL ingestion or taxonomy mapping before the official CSE production capability is available;
- any required SQL/cloud/local database;
- an LLM publication path;
- silent board/listing-segment inference;
- closing-price substitution for last traded price;
- derived liabilities publication;
- cumulative/YTD substitution for reported quarter facts.
