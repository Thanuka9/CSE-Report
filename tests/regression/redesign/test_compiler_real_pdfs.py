"""Compiler acceptance proof on the six audited real filings (audit finding 2).

For every PDF the DEFAULT ``extract_filing`` path must:

* compile native statements (``native_compiler_success`` True, ``compiled_statements`` > 0),
* publish with no explicit fallback,
* reproduce the manually verified 3M-ended-30-Jun-2026 standalone values from compiler
  geometry (``extraction_origin == compiler_geometry``), never from layout assistance.

If a value cannot be reproduced the compiler must be fixed; the assertions are never
loosened and no value may be routed through a fallback to make the test pass.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from cse_financial_etl.config import load_issuers
from cse_financial_etl.extraction.statement_extractor import ExtractedFact, extract_filing
from tests.fixture_paths import real_pdf

ROOT = Path(__file__).resolve().parents[3]
PERIOD_END = date(2026, 6, 30)

CASES: list[dict] = [
    {
        "issuer": "JAT HOLDINGS PLC",
        "symbol": "JAT.N0000",
        "pdf": "JAT_HOLDINGS_PLC/2026-06-30_2353_1786011152811.27_Q1_SIGNED.pdf",
        "truth": {"PAT": Decimal("108959808")},
        "entity": "COMPANY",
    },
    {
        "issuer": "COMMERCIAL BANK OF CEYLON PLC",
        "symbol": "COMB.N0000",
        "pdf": "COMMERCIAL_BANK_OF_CEYLON_PLC/2026-06-30_369_1786618965674.pdf",
        "truth": {
            "PAT": Decimal("16621006000"),
            "EPS_BASIC": Decimal("10.06"),
            "EPS_DILUTED": Decimal("10.02"),
        },
        "entity": "BANK",
    },
    {
        "issuer": "DIALOG AXIATA PLC",
        "symbol": "DIAL.N0000",
        "pdf": "DIALOG_AXIATA_PLC/2026-06-30_389_1786711190916.pdf",
        "truth": {"PAT": Decimal("8187022000"), "EPS_BASIC": Decimal("0.89")},
        "entity": "COMPANY",
    },
    {
        "issuer": "JOHN KEELLS HOLDINGS PLC",
        "symbol": "JKH.N0000",
        "pdf": "JOHN_KEELLS_HOLDINGS_PLC/2026-06-30_508_1785229278745.pdf",
        "truth": {"PAT": Decimal("5378093000")},
        "entity": "COMPANY",
    },
    {
        "issuer": "HAYLEYS FIBRE PLC",
        "symbol": "HEXP.N0000",
        "pdf": "HAYLEYS_FIBRE_PLC/2026-06-30_768_1785840975698.06.2026.pdf",
        "truth": {},
        "entity": "COMPANY",
    },
    {
        "issuer": "MERCHANT BANK OF SRI LANKA & FINANCE PLC",
        "symbol": "MBSL.N0000",
        "pdf": "MERCHANT_BANK_OF_SRI_LANKA_FINANCE_PLC/2026-06-30_380_1786934627322.06.2026 (1).pdf",
        "truth": {},
        "entity": "COMPANY",
    },
]

CORE = ("PAT", "PBT", "TOP_LINE", "TOTAL_ASSETS", "TOTAL_EQUITY")


def _evidence(fact: ExtractedFact) -> dict:
    return json.loads(fact.evidence_json or "{}")


def _run(case: dict) -> list[ExtractedFact]:
    pdf = real_pdf(case["pdf"])
    return extract_filing(
        pdf,
        case["issuer"],
        case["symbol"],
        PERIOD_END,
        ocr_enabled=False,
        issuers=load_issuers(ROOT),
    )


@pytest.mark.parametrize("case", CASES, ids=[c["symbol"] for c in CASES])
def test_default_path_compiles_and_reproduces_manual_truths(case: dict) -> None:
    facts = _run(case)
    by_code = {f.metric_code: f for f in facts}
    extracted = [f for f in facts if f.status == "EXTRACTED" and f.metric_code != "EPS_SELECTED"]
    assert extracted, "no EXTRACTED facts published"

    summary = None
    for fact in extracted:
        ev = _evidence(fact)
        assert ev.get("publication_routing") == "statement_compiler", (fact.metric_code, ev.get("publication_routing"))
        assert ev.get("native_compiler_success") is True, fact.metric_code
        assert ev.get("explicit_fallback") is None, (fact.metric_code, ev.get("explicit_fallback"))
        assert fact.review_status == "REVIEW", "machine output must not carry a human approval"
        summary = summary or ev.get("compiler_report_summary")
    assert summary is not None
    tunnel_a = summary["tunnel_a"]
    assert tunnel_a["statements"] > 0
    assert tunnel_a["native_compiler_success"] is True
    assert tunnel_a["pages"] > 0 and tunnel_a["tokens"] > 0

    # Core statement facts published from compiler geometry, standalone, current 3M.
    for code in CORE:
        fact = by_code.get(code)
        assert fact is not None and fact.status == "EXTRACTED", (code, fact.status if fact else None)
        ev = _evidence(fact)
        assert ev.get("extraction_origin") == "compiler_geometry", (code, ev.get("extraction_origin"))
        assert fact.entity_scope == case["entity"], (code, fact.entity_scope)
        assert fact.comparison_role == "CURRENT"
        assert fact.period_end == PERIOD_END
        assert fact.currency == "LKR"
        if code in {"PAT", "PBT", "TOP_LINE"}:
            assert fact.duration_months == 3, (code, fact.duration_months)

    for code, expected in case["truth"].items():
        fact = by_code.get(code)
        assert fact is not None, code
        assert fact.status == "EXTRACTED", (code, fact.status)
        assert fact.normalized_value == expected, (code, fact.normalized_value, expected)
        ev = _evidence(fact)
        assert ev.get("extraction_origin") == "compiler_geometry", (code, ev.get("extraction_origin"))
        assert ev.get("publication_routing") == "statement_compiler"
