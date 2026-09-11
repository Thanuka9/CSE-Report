from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import extract_filing
from cse_financial_etl.tunnels.extraction_compiler import compile_filing
from tests.fixture_paths import real_pdf


def _entry_debug(entry: object) -> dict[str, object]:
    return {
        "entry_id": getattr(entry, "entry_id", None),
        "tunnel": getattr(entry, "tunnel", None),
        "status": getattr(entry, "status", None),
        "raw_value": str(getattr(entry, "raw_value", None)),
        "normalized_value": str(getattr(entry, "normalized_value", None)),
        "entity": getattr(entry, "entity", None),
        "period_end": getattr(entry, "period_end", None),
        "duration_months": getattr(entry, "duration_months", None),
        "comparison_role": getattr(entry, "comparison_role", None),
        "unit": getattr(entry, "unit", None),
        "scale_factor": getattr(entry, "scale_factor", None),
        "page": getattr(entry, "page", None),
        "label": getattr(entry, "label", None),
        "score": getattr(entry, "score", None),
        "reasons": getattr(entry, "reasons", None),
        "evidence": getattr(entry, "evidence", None),
    }


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
    if any(
        fact.normalized_value == Decimal("29495553000")
        and fact.status == "EXTRACTED"
        for fact in candidates
    ):
        return

    compiled = compile_filing(
        pdf,
        issuer_name="COMMERCIAL BANK OF CEYLON PLC",
        symbol="COMB.N0000",
        period_end=date(2026, 6, 30),
        legacy_facts=None,
        compile_statements=True,
        run_tunnel_b_always=True,
    )
    native = [
        _entry_debug(entry)
        for entry in compiled["ledger"].for_concept("OPERATING_PROFIT")
        if getattr(entry, "evidence", {}).get("candidate_origin") == "compiler_geometry"
    ]
    raise AssertionError(
        json.dumps(
            {
                "published": [fact.as_json() for fact in candidates],
                "native": native,
            },
            indent=2,
            default=str,
        )
    )
