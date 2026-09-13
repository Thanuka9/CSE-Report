"""V2 validation adapters over proven V1 accounting rules."""

from __future__ import annotations

from cse_financial_etl.v2.validation.accounting import derive_facts, validate_source_facts

__all__ = ["derive_facts", "validate_source_facts"]
