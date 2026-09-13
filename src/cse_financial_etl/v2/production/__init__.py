"""Production adapter. V1 extract_filing remains for replay."""

from cse_financial_etl.v2.production.engine import extract_for_production

__all__ = ["extract_for_production"]
