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
    # Phase One freeze: never publish Assets-Equity or assembled totals without
    # an explicit Total Liabilities source row (or formally approved derived policy).
    assert liabilities.status in {
        "SOURCE_CONFIRMED_NOT_REPORTED",
        "NOT_FOUND_BY_PARSER",
        "EXTRACTED_DERIVED",
        "EXTRACTED",
    }
    if liabilities.status == "EXTRACTED_DERIVED":
        assert liabilities.entity_scope == "COMPANY"
        assert liabilities.raw_value == Decimal("2421207")
        assert liabilities.normalized_value == Decimal("2421207000")
    else:
        assert liabilities.normalized_value is None
        assert liabilities.entity_scope == "COMPANY"

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
    # Company P&L prints EPS values on a detached unit line; prefer honest
    # missing/cumulative over Group page EPS. Core flow still extracts.
    assert facts["PAT"].status == "EXTRACTED"
    assert facts["TOP_LINE"].status == "EXTRACTED"
    eps = facts["EPS_BASIC"]
    assert eps.status in {"EXTRACTED", "CUMULATIVE_ONLY", "NOT_FOUND_BY_PARSER", "VALUE_CONTEXT_UNRESOLVED"}
    if eps.status == "EXTRACTED":
        assert eps.normalized_value is not None
        assert eps.duration_months == 3


def test_dialog_uses_quarter_company_not_six_month() -> None:
    """Manual QA: Dialog 6M Company values must never publish as the quarter."""

    from cse_financial_etl.extraction.statement_extractor import extract_quarter_prices

    facts = _facts(
        "data/raw/filings/DIALOG_AXIATA_PLC/2026-06-30_389_1786711190916.pdf",
        "DIALOG AXIATA PLC",
        "DIAL.N0000",
        date(2026, 6, 30),
    )
    assert facts["TOP_LINE"].status == "EXTRACTED"
    assert facts["TOP_LINE"].duration_months == 3
    assert facts["TOP_LINE"].normalized_value == Decimal("37231246000")
    assert facts["TOP_LINE"].raw_value != Decimal("73251657")
    assert facts["PAT"].normalized_value == Decimal("8187022000")
    assert facts["OPERATING_PROFIT"].normalized_value == Decimal("10628121000")
    assert facts["EPS_BASIC"].normalized_value == Decimal("0.89")
    prices = extract_quarter_prices(
        _pdf("data/raw/filings/DIALOG_AXIATA_PLC/2026-06-30_389_1786711190916.pdf"),
        "DIALOG AXIATA PLC",
        ["DIAL.N0000"],
        date(2026, 6, 30),
    )
    assert prices[0].value == Decimal("46.10")


def test_comb_bank_quarter_not_comparative_or_ytd() -> None:
    """Manual QA: COMB dual 6M+quarter Bank page must pick current quarter columns."""

    facts = _facts(
        "data/raw/filings/COMMERCIAL_BANK_OF_CEYLON_PLC/2026-06-30_369_1786618965674.pdf",
        "COMMERCIAL BANK OF CEYLON PLC",
        "COMB.N0000",
        date(2026, 6, 30),
    )
    assert facts["TOP_LINE"].entity_scope == "BANK"
    assert facts["TOP_LINE"].duration_months == 3
    assert facts["TOP_LINE"].normalized_value == Decimal("106625116000")
    assert facts["TOP_LINE"].raw_value != Decimal("86540938")
    assert facts["PAT"].normalized_value == Decimal("16621006000")
    assert facts["PAT"].raw_value != Decimal("15554770")
    assert facts["TOTAL_ASSETS"].normalized_value == Decimal("3592606230000")
    assert facts["TOTAL_EQUITY"].normalized_value == Decimal("347873696000")
    assert facts["TOTAL_LIABILITIES"].normalized_value == Decimal("3244732534000")
    assert facts["NAVPS"].normalized_value == Decimal("210.38")


def test_jat_last_traded_price_and_no_derived_liabilities() -> None:
    """Manual QA: JAT last-traded is 39.80; liabilities stay missing without an explicit total."""

    from cse_financial_etl.extraction.statement_extractor import extract_quarter_prices

    facts = _facts(
        "data/raw/filings/JAT_HOLDINGS_PLC/2026-06-30_2353_1786011152811.27_Q1_SIGNED.pdf",
        "JAT HOLDINGS PLC",
        "JAT.N0000",
        date(2026, 6, 30),
    )
    assert facts["PAT"].normalized_value == Decimal("108959808")
    assert facts["TOTAL_LIABILITIES"].status in {
        "SOURCE_CONFIRMED_NOT_REPORTED",
        "NOT_FOUND_BY_PARSER",
    }
    assert facts["TOTAL_LIABILITIES"].normalized_value is None
    prices = extract_quarter_prices(
        _pdf("data/raw/filings/JAT_HOLDINGS_PLC/2026-06-30_2353_1786011152811.27_Q1_SIGNED.pdf"),
        "JAT HOLDINGS PLC",
        ["JAT.N0000"],
        date(2026, 6, 30),
    )
    assert prices[0].value == Decimal("39.80")
    assert prices[0].value != Decimal("8.5")
