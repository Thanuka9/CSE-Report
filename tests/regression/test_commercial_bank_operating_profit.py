from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import extract_filing
from tests.fixture_paths import real_pdf


def test_commercial_bank_operating_profit_candidate_survives_extraction() -> None:
    pdf = real_pdf("2026-06-30_369_1786618965674.pdf")
    facts = extract_filing(
        pdf,
        "COMMERCIAL BANK OF CEYLON PLC",
        "COMB.N0000",
        date(2026, 6, 30),
        ocr_enabled=False,
    )
    candidates = [fact for fact in facts if fact.metric_code == "OPERATING_PROFIT"]
    if not any(
        fact.normalized_value == Decimal("29495553000")
        and fact.status == "EXTRACTED"
        for fact in candidates
    ):
        raise AssertionError(
            json.dumps([fact.as_json() for fact in candidates], indent=2, default=str)
        )
