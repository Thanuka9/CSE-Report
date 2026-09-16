"""Production adapter. V1 extract_filing remains for replay."""

from __future__ import annotations

from typing import Any

__all__ = ["extract_for_production", "publish_production_workbook"]


def __getattr__(name: str) -> Any:
    if name == "extract_for_production":
        from cse_financial_etl.v2.production.engine import extract_for_production

        return extract_for_production
    if name == "publish_production_workbook":
        from cse_financial_etl.v2.production.publish import publish_production_workbook

        return publish_production_workbook
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
