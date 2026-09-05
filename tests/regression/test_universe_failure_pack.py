from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from cse_financial_etl.extraction.statement_extractor import extract_filing, facts_by_code

ROOT = Path(__file__).resolve().parents[2]


def _pdf(relative: str) -> Path:
    path = ROOT / relative
    if not path.exists():
        pytest.skip(f"Universe failure PDF not downloaded: {relative}")
    return path


def _facts(relative: str, issuer: str, symbol: str, period: date) -> dict:
    return facts_by_code(
        extract_filing(_pdf(relative), issuer, symbol, period, ocr_enabled=False)
    )


def test_cic_selects_company_and_rejects_group() -> None:
    facts = _facts(
        "data/raw/filings/C_I_C_HOLDINGS_PLC/2025-12-31_493_1770119995452.pdf",
        "CIC HOLDINGS PLC",
        "CIC.N0000",
        date(2025, 12, 31),
    )
    top = facts["TOP_LINE"]
    assert top.status == "EXTRACTED"
    assert top.entity_scope == "COMPANY"
    assert top.normalized_value == Decimal("5816610000.00")
    assert top.source_page == 3
    assert "28,644" not in (top.source_line or "")
    liabilities = facts["TOTAL_LIABILITIES"]
    assert liabilities.status == "EXTRACTED"
    assert liabilities.entity_scope == "COMPANY"
    assert liabilities.source_page == 5
    assert liabilities.normalized_value == Decimal("26918550000.00")
    assert liabilities.raw_value == Decimal("26918.55")
    assert liabilities.raw_value != Decimal("49979.10")


def test_jkh_company_pat_uses_thousands_scale() -> None:
    facts = _facts(
        "data/raw/filings/JOHN_KEELLS_HOLDINGS_PLC/2026-06-30_508_1785229278745.pdf",
        "JOHN KEELLS HOLDINGS PLC",
        "JKH.N0000",
        date(2026, 6, 30),
    )
    pat = facts["PAT"]
    assert pat.status == "EXTRACTED"
    assert pat.entity_scope == "COMPANY"
    assert pat.raw_value == Decimal("5378093")
    assert pat.scale_factor == 1000
    assert pat.normalized_value == Decimal("5378093000")
    assets = facts["TOTAL_ASSETS"]
    assert assets.status == "EXTRACTED"
    assert assets.source_page == 17
    assert assets.normalized_value == Decimal("366834520000")
    assert assets.raw_value != Decimal("934898114")


def test_ndb_rejects_notes_page_equity() -> None:
    facts = _facts(
        "data/raw/filings/NATIONAL_DEVELOPMENT_BANK_PLC/2026-06-30_386_1784717094209.pdf",
        "NATIONAL DEVELOPMENT BANK PLC",
        "NDB.N0000",
        date(2026, 6, 30),
    )
    equity = facts["TOTAL_EQUITY"]
    assert equity.status == "EXTRACTED"
    assert equity.entity_scope == "BANK"
    assert equity.source_page == 8
    assert equity.normalized_value == Decimal("80048931000")
    assert equity.raw_value != Decimal("-5993528")
    liabilities = facts["TOTAL_LIABILITIES"]
    assert liabilities.status == "EXTRACTED"
    assert liabilities.entity_scope == "BANK"
    assert liabilities.source_page == 8
    assert liabilities.normalized_value == Decimal("868970702000")


def test_pickme_company_operating_profit_and_honest_liabilities() -> None:
    facts = _facts(
        "data/raw/filings/DIGITAL_MOBILITY_SOLUTIONS_LANKA_PLC/2026-06-30_3218_1785237350161.pdf",
        "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
        "PKME.N0000",
        date(2026, 6, 30),
    )
    operating = facts["OPERATING_PROFIT"]
    assert operating.status == "EXTRACTED"
    assert operating.normalized_value == Decimal("833824000")
    assert "833,198" not in (operating.source_line or "")
    liabilities = facts["TOTAL_LIABILITIES"]
    assert liabilities.status == "EXTRACTED_DERIVED"
    assert liabilities.entity_scope == "COMPANY"
    assert liabilities.raw_value == Decimal("2421207")
    assert liabilities.normalized_value == Decimal("2421207000")


def test_hotel_rs_apostrophe_thousands_and_asiri_cash_flow_op() -> None:
    facts = _facts(
        "data/raw/filings/AITKEN_SPENCE_HOTEL_HOLDINGS_PLC/2026-06-30_521_1786698820226.pdf",
        "AITKEN SPENCE HOTEL HOLDINGS PLC",
        "AHUN.N0000",
        date(2026, 6, 30),
    )
    pat = facts["PAT"]
    assert pat.status == "EXTRACTED"
    assert pat.scale_factor == 1000
    assert pat.raw_value == Decimal("-84437")
    assert pat.normalized_value == Decimal("-84437000")
    operating = facts["OPERATING_PROFIT"]
    assert operating.status in {"EXTRACTED", "LOW_CERTAINTY"}
    assert operating.scale_factor == 1000
    assert operating.entity_scope == "COMPANY"
    assert operating.raw_value == Decimal("-36771")
    assert operating.normalized_value == Decimal("-36771000")
    assert operating.raw_value != Decimal("-508630")
    assert operating.raw_value != Decimal("-78445")

    asiri = _facts(
        "data/raw/filings/ASIRI_HOSPITAL_HOLDINGS_PLC/2026-06-30_512_1786008393675.pdf",
        "ASIRI HOSPITAL HOLDINGS PLC",
        "ASIR.N0000",
        date(2026, 6, 30),
    )
    asiri_op = asiri["OPERATING_PROFIT"]
    assert asiri_op.raw_value != Decimal("-1109244")
    assert "Working Capital" not in (asiri_op.source_line or "")


def test_lotus_sri_lankan_rupees_is_unit_scale_one() -> None:
    from cse_financial_etl.config import load_unit_pattern_config
    from cse_financial_etl.extraction.unit_detector import configure_unit_patterns

    configure_unit_patterns(load_unit_pattern_config(ROOT))
    facts = _facts(
        "data/raw/filings/LOTUS_HYDRO_POWER_PLC/2026-06-30_1000_1786445069288.pdf",
        "LOTUS HYDRO POWER PLC",
        "HPFL.N0000",
        date(2026, 6, 30),
    )
    pat = facts["PAT"]
    assert pat.status in {"EXTRACTED", "LOW_CERTAINTY"}
    assert pat.scale_factor == 1
    assert pat.status != "UNIT_NOT_RESOLVED"


def test_softlogic_singular_total_liability_on_company_sofp() -> None:
    facts = _facts(
        "data/raw/filings/SOFTLOGIC_CAPITAL_PLC/2026-06-30_1100_1786699448160.pdf",
        "SOFTLOGIC CAPITAL PLC",
        "SCAP.N0000",
        date(2026, 6, 30),
    )
    liabilities = facts["TOTAL_LIABILITIES"]
    assert liabilities.status == "EXTRACTED"
    assert liabilities.entity_scope == "COMPANY"
    assert liabilities.raw_value == Decimal("18669216994")
    assert liabilities.source_page == 6
    assert liabilities.raw_value != Decimal("91790041822")


def test_ambeon_holdings_latest_pat_is_total_period_profit() -> None:
    facts = _facts(
        "data/raw/filings/AMBEON_HOLDINGS_PLC/2026-06-30_782_1786930433403.06.2026.pdf",
        "AMBEON HOLDINGS PLC",
        "GREG.N0000",
        date(2026, 6, 30),
    )
    pat = facts["PAT"]
    assert pat.status == "EXTRACTED"
    assert "Continuing" not in (pat.source_line or "")
    assert "for the period" in (pat.source_line or "").lower()
    assert pat.raw_value == Decimal("-234370")


def test_ambeon_capital_latest_op_is_not_pbt_continuing() -> None:
    facts = _facts(
        "data/raw/filings/AMBEON_CAPITAL_PLC/2026-06-30_1181_1786931840868.pdf",
        "AMBEON CAPITAL PLC",
        "TAP.N0000",
        date(2026, 6, 30),
    )
    operating = facts["OPERATING_PROFIT"]
    assert "Before Tax from Continuing" not in (operating.source_line or "")
    assert operating.raw_value != Decimal("-25003") or operating.status != "EXTRACTED"
    top = facts["TOP_LINE"]
    assert "Comprehensive" not in (top.source_line or "")


def test_colombo_city_latest_top_line_is_not_comprehensive_income() -> None:
    facts = _facts(
        "data/raw/filings/COLOMBO_CITY_HOLDINGS_PLC/2026-06-30_744_1785843841492.pdf",
        "COLOMBO CITY HOLDINGS PLC",
        "PHAR.N0000",
        date(2026, 6, 30),
    )
    top = facts["TOP_LINE"]
    assert "Comprehensive" not in (top.source_line or "")
    assert top.raw_value != Decimal("-36206")


def test_bogala_profit_from_operation_and_capital_alliance_interest_income() -> None:
    bogala = _facts(
        "data/raw/filings/BOGALA_GRAPHITE_LANKA_PLC/2026-06-30_664_1786448088740.pdf",
        "BOGALA GRAPHITE LANKA PLC",
        "BOGA.N0000",
        date(2026, 6, 30),
    )
    assert bogala["OPERATING_PROFIT"].status == "EXTRACTED"
    assert bogala["OPERATING_PROFIT"].raw_value == Decimal("165706")

    calt = _facts(
        "data/raw/filings/CAPITAL_ALLIANCE_PLC/2026-06-30_2647_1786703367877.pdf",
        "CAPITAL ALLIANCE PLC",
        "CALT.N0000",
        date(2026, 6, 30),
    )
    assert "Comprehensive" not in (calt["TOP_LINE"].source_line or "")
    assert calt["TOP_LINE"].raw_value == Decimal("330218321")
    assert "Net Interest" in (calt["TOP_LINE"].source_line or "")

    vallibel = _facts(
        "data/raw/filings/VALLIBEL_ONE_PLC/2026-06-30_1074_1786707371158.6.2026.pdf",
        "VALLIBEL ONE PLC",
        "VONE.N0000",
        date(2026, 6, 30),
    )
    assert "Other operating" not in (vallibel["TOP_LINE"].source_line or "")
    assert vallibel["TOP_LINE"].raw_value != Decimal("131052")
    assert "continuing" not in (vallibel["PAT"].source_line or "").lower()


def test_windforce_latest_eps_reads_earning_share() -> None:
    facts = _facts(
        "data/raw/filings/WINDFORCE_PLC/2026-06-30_2173_1786674329905.pdf",
        "WINDFORCE PLC",
        "WIND.N0000",
        date(2026, 6, 30),
    )
    eps = facts["EPS_BASIC"]
    assert eps.status == "EXTRACTED"
    assert eps.normalized_value is not None
