from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from cse_financial_etl.extraction.statement_extractor import ExtractedFact, QuarterPrice
from cse_financial_etl.sources.cse import DownloadedFiling

FLOW_CODES = {
    "PAT",
    "PBT",
    "TOP_LINE",
    "OPERATING_PROFIT",
    "EPS_BASIC",
    "EPS_DILUTED",
    "EPS_SELECTED",
}
ABSOLUTE = "MONETARY_ABSOLUTE"
STANDALONE = {"COMPANY", "BANK"}
PUBLISHED = {"EXTRACTED", "EXTRACTED_DERIVED"}


@dataclass(frozen=True, slots=True)
class GateHit:
    code: str
    issuer_name: str
    symbol: str
    period_end: date | None
    metric_code: str | None
    detail: str


def _price_date(price: QuarterPrice) -> date | None:
    if not price.source_line:
        return None
    match = re.search(r"price_date=(\d{4}-\d{2}-\d{2})", price.source_line)
    if not match:
        return None
    return date.fromisoformat(match.group(1))


def evaluate_production_gates(
    extracted_results: Iterable[tuple[DownloadedFiling, list[ExtractedFact]]],
    prices: Iterable[QuarterPrice] = (),
    *,
    golden_validation: dict[str, Any] | None = None,
    required_scope: dict[str, str] | None = None,
) -> list[GateHit]:
    """Hard stops for a universe run. Any hit means VALIDATION_REQUIRED, not gold promotion."""

    hits: list[GateHit] = []
    if golden_validation:
        failed = [
            row
            for row in golden_validation.get("results", [])
            if row.get("status") == "FAIL"
        ]
        for row in failed:
            hits.append(
                GateHit(
                    "GOLD_WRONG_POPULATED",
                    str(row.get("issuer_name") or ""),
                    str(row.get("symbol") or ""),
                    date.fromisoformat(row["period_end"]) if row.get("period_end") else None,
                    str(row.get("metric_code") or ""),
                    f"expected {row.get('expected')} actual {row.get('actual')}",
                )
            )

    scopes = required_scope or {}
    for downloaded, facts in extracted_results:
        required = scopes.get(downloaded.filing.issuer_name)
        for fact in facts:
            if fact.status not in PUBLISHED:
                continue
            if (
                fact.metric_code in FLOW_CODES
                and fact.comparison_role != "CURRENT"
            ):
                hits.append(
                    GateHit(
                        "CURRENT_COMPARATIVE_MISMATCH",
                        fact.issuer_name,
                        fact.symbol,
                        fact.period_end,
                        fact.metric_code,
                        f"published comparison_role={fact.comparison_role}",
                    )
                )
            if fact.metric_code in FLOW_CODES and fact.duration_months in {6, 9, 12}:
                hits.append(
                    GateHit(
                        "CUMULATIVE_PUBLISHED_AS_QUARTER",
                        fact.issuer_name,
                        fact.symbol,
                        fact.period_end,
                        fact.metric_code,
                        f"duration_months={fact.duration_months}",
                    )
                )
            expected_scope = required or (
                fact.entity_scope if fact.entity_scope in STANDALONE else "COMPANY"
            )
            if (
                expected_scope in STANDALONE
                and fact.entity_scope in {"GROUP", "CONSOLIDATED"}
            ):
                hits.append(
                    GateHit(
                        "GROUP_WHERE_STANDALONE_REQUIRED",
                        fact.issuer_name,
                        fact.symbol,
                        fact.period_end,
                        fact.metric_code,
                        f"entity_scope={fact.entity_scope}",
                    )
                )
            if (
                fact.metric_type == ABSOLUTE
                and fact.status == "EXTRACTED"
                and not (fact.unit_source_text or "").strip()
            ):
                hits.append(
                    GateHit(
                        "UNIT_ASSUMED_WITHOUT_EVIDENCE",
                        fact.issuer_name,
                        fact.symbol,
                        fact.period_end,
                        fact.metric_code,
                        "EXTRACTED monetary fact has no unit evidence",
                    )
                )
            if fact.status == "EXTRACTED" and fact.validation_status == "FAILED":
                hits.append(
                    GateHit(
                        "UNRESOLVED_CANDIDATE_PUBLISHED",
                        fact.issuer_name,
                        fact.symbol,
                        fact.period_end,
                        fact.metric_code,
                        "EXTRACTED despite FAILED validation",
                    )
                )
            evidence = {}
            if fact.evidence_json:
                try:
                    parsed = json.loads(fact.evidence_json)
                    evidence = parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    evidence = {}
            if fact.status == "EXTRACTED" and evidence.get("unresolved"):
                hits.append(
                    GateHit(
                        "UNRESOLVED_CANDIDATE_PUBLISHED",
                        fact.issuer_name,
                        fact.symbol,
                        fact.period_end,
                        fact.metric_code,
                        "unresolved candidate marked EXTRACTED",
                    )
                )

    for price in prices:
        if price.status != "EXTRACTED" or price.value is None:
            continue
        observed = _price_date(price)
        if observed is not None and observed > price.period_end:
            hits.append(
                GateHit(
                    "HISTORICAL_PRICE_AFTER_QUARTER_END",
                    price.issuer_name,
                    price.symbol,
                    price.period_end,
                    "MARKET_PRICE_QUARTER_END",
                    f"price_date={observed.isoformat()} after {price.period_end.isoformat()}",
                )
            )
    return hits


def run_status_from_gates(hits: list[GateHit], *, has_errors: bool, has_review: bool) -> str:
    if hits:
        return "VALIDATION_REQUIRED"
    if has_errors or has_review:
        return "COMPLETED_WITH_REVIEW"
    return "COMPLETED"
