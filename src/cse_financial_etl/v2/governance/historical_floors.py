"""Historical coverage floors frozen from the 2026-09-10 accepted run.

These constants are the unauthorized-lowering backstop. Normal PRs may keep or
raise floors in configs/coverage_baseline.yml. They may not lower them, and they
may not edit these historical constants without a governed acknowledgement.

Incident reference: silent recalibration toward 2,394 DRAFT-publishable facts
is forbidden. 8,924 is the historical production floor, not a recovery slogan.
"""

from __future__ import annotations

from typing import Final

HISTORICAL_MIN_EXTRACTED_PLUS_DERIVED: Final[int] = 8932
HISTORICAL_MIN_DRAFT_PUBLISHABLE: Final[int] = 8924
HISTORICAL_MIN_GOLD_SAMPLE: Final[int] = 100
HISTORICAL_MIN_GOLD_ISSUERS: Final[int] = 100
HISTORICAL_MIN_ISSUER_COUNT: Final[int] = 281
HISTORICAL_MIN_DOWNLOADED_FILING_COUNT: Final[int] = 829
HISTORICAL_MIN_EXTRACTED_FILING_COUNT: Final[int] = 826
HISTORICAL_MAX_QUARANTINED_EXTRACTION_TIMEOUTS: Final[int] = 3

HISTORICAL_MIN_PUBLISHABLE_BY_METRIC: Final[dict[str, int]] = {
    "DEBT_TO_EQUITY": 447,
    "EPS_BASIC": 660,
    "EPS_DILUTED": 188,
    "EPS_SELECTED": 666,
    "NAVPS": 710,
    "NPM": 627,
    "OPERATING_PROFIT": 549,
    "PAT": 675,
    "PBT": 677,
    "ROA": 600,
    "ROE": 569,
    "TOP_LINE": 683,
    "TOTAL_ASSETS": 712,
    "TOTAL_EQUITY": 690,
    "TOTAL_LIABILITIES": 471,
}

HISTORICAL_MIN_PUBLISHABLE_BY_SECTOR_METRIC: Final[dict[str, dict[str, int]]] = {
    "BANK": {
        "DEBT_TO_EQUITY": 35,
        "EPS_BASIC": 30,
        "EPS_DILUTED": 26,
        "EPS_SELECTED": 30,
        "NAVPS": 35,
        "NPM": 33,
        "OPERATING_PROFIT": 31,
        "PAT": 33,
        "PBT": 32,
        "ROA": 33,
        "ROE": 33,
        "TOP_LINE": 33,
        "TOTAL_ASSETS": 35,
        "TOTAL_EQUITY": 35,
        "TOTAL_LIABILITIES": 35,
    },
    "FINANCE_COMPANY": {
        "DEBT_TO_EQUITY": 66,
        "EPS_BASIC": 58,
        "EPS_DILUTED": 20,
        "EPS_SELECTED": 58,
        "NAVPS": 64,
        "NPM": 62,
        "OPERATING_PROFIT": 59,
        "PAT": 65,
        "PBT": 66,
        "ROA": 57,
        "ROE": 57,
        "TOP_LINE": 65,
        "TOTAL_ASSETS": 66,
        "TOTAL_EQUITY": 66,
        "TOTAL_LIABILITIES": 66,
    },
    "INSURANCE": {
        "DEBT_TO_EQUITY": 25,
        "EPS_BASIC": 24,
        "EPS_DILUTED": 13,
        "EPS_SELECTED": 26,
        "NAVPS": 30,
        "NPM": 24,
        "OPERATING_PROFIT": 6,
        "PAT": 25,
        "PBT": 25,
        "ROA": 22,
        "ROE": 21,
        "TOP_LINE": 25,
        "TOTAL_ASSETS": 29,
        "TOTAL_EQUITY": 30,
        "TOTAL_LIABILITIES": 26,
    },
    "GENERAL": {
        "DEBT_TO_EQUITY": 321,
        "EPS_BASIC": 548,
        "EPS_DILUTED": 129,
        "EPS_SELECTED": 552,
        "NAVPS": 581,
        "NPM": 508,
        "OPERATING_PROFIT": 453,
        "PAT": 552,
        "PBT": 554,
        "ROA": 488,
        "ROE": 458,
        "TOP_LINE": 560,
        "TOTAL_ASSETS": 582,
        "TOTAL_EQUITY": 559,
        "TOTAL_LIABILITIES": 344,
    },
}

SCALAR_MIN_KEYS: Final[tuple[str, ...]] = (
    "min_extracted_plus_derived",
    "min_draft_publishable",
    "min_gold_sample",
    "min_gold_issuers",
    "min_issuer_count",
    "min_downloaded_filing_count",
    "min_extracted_filing_count",
)

SCALAR_MAX_KEYS: Final[tuple[str, ...]] = ("max_quarantined_extraction_timeouts",)

HISTORICAL_SCALAR_MINS: Final[dict[str, int]] = {
    "min_extracted_plus_derived": HISTORICAL_MIN_EXTRACTED_PLUS_DERIVED,
    "min_draft_publishable": HISTORICAL_MIN_DRAFT_PUBLISHABLE,
    "min_gold_sample": HISTORICAL_MIN_GOLD_SAMPLE,
    "min_gold_issuers": HISTORICAL_MIN_GOLD_ISSUERS,
    "min_issuer_count": HISTORICAL_MIN_ISSUER_COUNT,
    "min_downloaded_filing_count": HISTORICAL_MIN_DOWNLOADED_FILING_COUNT,
    "min_extracted_filing_count": HISTORICAL_MIN_EXTRACTED_FILING_COUNT,
}

HISTORICAL_SCALAR_MAXES: Final[dict[str, int]] = {
    "max_quarantined_extraction_timeouts": HISTORICAL_MAX_QUARANTINED_EXTRACTION_TIMEOUTS,
}
