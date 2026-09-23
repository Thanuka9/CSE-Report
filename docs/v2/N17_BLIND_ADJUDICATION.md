# N17 Blind Adjudication Package

**Status:** READY FOR HUMAN REVIEW — gold not started  
**Hybrid cutover:** superseded as a *pre-cutover extraction* holdout by
`docs/v2/HYBRID_RELEASE_CONTRACT.md`. This package remains required before
deleting V1 or certifying V2-native (non-hybrid) extraction.  
**Identity:** `tests/v2/source_truth/holdout_v2_identity_manifest.json` (13 filings)  
**Blank queue:** `tests/v2/source_truth/n17_blind_review_queue.json` (130 metric slots)  
**Production:** remains `extraction.engine: v1` / floor `8924`

## Hard rules

1. Do **not** open V1 outputs, V2 outputs, CandidateTrace, SourceFacts, or workbook cells for these PDFs.
2. Use only the source PDF + Source Metric Truth Contract + locked metric semantics.
3. Do **not** score N16 / run N18 until this queue is locked as gold.
4. Do **not** promote V2 or lower 8924.
5. First T25 holdout is retired DEV/regression — do not reuse it as final holdout.

## How to adjudicate

For each row in `n17_blind_review_queue.json`:

1. Open `local_file` (relative to repo root).
2. Find the metric on the statement pages.
3. Fill `source_presence` (`REPORTED` / `NOT_REPORTED` / `AMBIGUOUS`).
4. If reported, fill label/value/normalized_value/entity/period/duration/comparison/currency/scale/unit/page/evidence.
5. Set `adjudication_status` to `REVIEWER_1_COMPLETE` (then `LOCKED` after optional reviewer 2).
6. Keep `split = HOLDOUT`.

When complete, append locked rows to `tests/v2/source_truth/items.jsonl` (or a dedicated holdout gold file agreed by governance) and freeze before N18 scoring.

## Filings (identity only)

| Symbol | Type | Period | PDF |
|---|---|---|---|
| PABC.N0000 | BANK | 2025-12-31 | data/raw/filings/PAN_ASIA_BANKING_CORPORATION_PLC/... |
| UBC.N0000 | BANK | 2025-12-31 | data/raw/filings/UNION_BANK_OF_COLOMBO_PLC/... |
| SDB.N0000 | BANK | 2025-12-31 | data/raw/filings/SANASA_DEVELOPMENT_BANK_PLC/... |
| COCR.N0000 | FINANCE_COMPANY | 2025-12-31 | data/raw/filings/COMMERCIAL_CREDIT_AND_FINANCE_PLC/... |
| AMCL.N0000 | FINANCE_COMPANY | 2025-12-31 | data/raw/filings/AMW_CAPITAL_LEASING_AND_FINANCE_PLC/... |
| AFSL.N0000 | FINANCE_COMPANY | 2025-12-31 | data/raw/filings/ABANS_FINANCE_PLC/... |
| LGIL.N0000 | INSURANCE | 2025-12-31 | data/raw/filings/LOLC_GENERAL_INSURANCE_PLC/... |
| ATLL.N0000 | INSURANCE | 2025-12-31 | data/raw/filings/AMANA_TAKAFUL_LIFE_PLC/... |
| HUNA.N0000 | GENERAL | 2025-12-31 | data/raw/filings/HUNAS_HOLDINGS_PLC/... |
| CINS.N0000 | GENERAL | 2025-12-31 | data/raw/filings/CEYLINCO_HOLDINGS_PLC/... |
| JFP.N0000 | GENERAL | 2025-12-31 | data/raw/filings/JF_PACKAGING_PLC/... |
| NHL.N0000 | GENERAL | 2025-12-31 | data/raw/filings/NAWALOKA_HOSPITALS_PLC/... |
| SCAP.N0000 | GENERAL | 2025-12-31 | data/raw/filings/SOFTLOGIC_CAPITAL_PLC/... |

All 13 PDFs are present on the local workspace.
