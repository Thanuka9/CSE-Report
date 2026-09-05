from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.sources.cse import DownloadedFiling

ACCEPTED = {"EXTRACTED", "EXTRACTED_DERIVED"}
COMPARE_CODES = {
    "PAT",
    "PBT",
    "TOP_LINE",
    "OPERATING_PROFIT",
    "EPS_BASIC",
    "EPS_DILUTED",
    "EPS_SELECTED",
    "TOTAL_ASSETS",
    "TOTAL_EQUITY",
    "TOTAL_LIABILITIES",
    "NAVPS",
}


@dataclass(frozen=True, slots=True)
class CrossFilingMismatch:
    issuer_name: str
    symbol: str
    period_end: date
    metric_code: str
    detail: str


def flag_cross_filing_mismatches(
    extracted_results: Iterable[tuple[DownloadedFiling, list[ExtractedFact]]],
    gold_facts_path: Path,
    *,
    relative_tolerance: Decimal = Decimal("0.02"),
) -> list[CrossFilingMismatch]:
    """Compare newly extracted current facts against previously published gold facts.

    A mismatch triggers investigation rather than automatic acceptance.
    """

    if not gold_facts_path.exists():
        return []
    try:
        previous = pl.read_parquet(gold_facts_path)
    except Exception:
        return []
    if previous.is_empty():
        return []
    prior = {
        (row["issuer_name"], row["period_end"], row["metric_code"]): row
        for row in previous.to_dicts()
        if row.get("status") in ACCEPTED and row.get("normalized_value") not in (None, "")
    }
    flags: list[CrossFilingMismatch] = []
    for item, facts in extracted_results:
        for fact in facts:
            if fact.metric_code not in COMPARE_CODES or fact.status not in ACCEPTED:
                continue
            if fact.normalized_value is None:
                continue
            row = prior.get((fact.issuer_name, fact.period_end.isoformat(), fact.metric_code))
            if row is None or row.get("filing_sha256") == item.sha256:
                continue
            try:
                old = Decimal(str(row["normalized_value"]))
            except Exception:
                continue
            if old == 0:
                mismatched = fact.normalized_value != 0
            else:
                mismatched = abs(fact.normalized_value - old) / abs(old) > relative_tolerance
            if not mismatched:
                continue
            flags.append(
                CrossFilingMismatch(
                    fact.issuer_name,
                    fact.symbol,
                    fact.period_end,
                    fact.metric_code,
                    (
                        f"{fact.metric_code} {fact.normalized_value} differs from prior filing "
                        f"{old} for {fact.period_end.isoformat()}."
                    ),
                )
            )
    return flags
