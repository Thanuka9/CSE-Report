"""Target fact query layer — query compiled statements, don't scrape PDFs (§36)."""

from __future__ import annotations

from cse_financial_etl.facts.derived_facts import compute_quarter_ratios
from cse_financial_etl.facts.query_engine import query_target_facts
from cse_financial_etl.facts.target_metrics import TARGET_METRIC_CODES, TargetQuery

__all__ = [
    "TARGET_METRIC_CODES",
    "TargetQuery",
    "compute_quarter_ratios",
    "query_target_facts",
]
