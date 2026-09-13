from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.diagnostics.real_filings import (
    load_adjudication_overlay,
    load_real_filing_cases,
)


def test_round1_overlay_keeps_audited_pat_and_drops_unlabeled() -> None:
    overlay = load_adjudication_overlay()
    symbols = overlay["symbols"]
    assert set(symbols) >= {
        "JKH.N0000",
        "COMB.N0000",
        "DIAL.N0000",
        "JAT.N0000",
        "HAYL.N0000",
        "CBNK.N0000",
        "ATL.N0000",
        "LCBF.N0000",
        "CALF.N0000",
        "AINS.N0000",
        "UAL.N0000",
        "YORK.N0000",
    }
    assert symbols["JKH.N0000"]["action"] == "keep"
    assert symbols["LCBF.N0000"]["action"] == "drop_all_expected"
    cases = {case.issuer_id: case for case in load_real_filing_cases(limit=40, locked=True)}
    if "COMB.N0000" in cases:
        assert all(fact.metric_code != "EPS_DILUTED" for fact in cases["COMB.N0000"].expected)
    if "AAF.N0000" in cases:
        pat = next(fact for fact in cases["AAF.N0000"].expected if fact.metric_code == "PAT")
        assert pat.normalized_value == Decimal("181180388")
        assert all(
            fact.metric_code not in {"TOTAL_ASSETS", "EPS_DILUTED"}
            for fact in cases["AAF.N0000"].expected
        )
    if "JKH.N0000" in cases:
        pat = next(fact for fact in cases["JKH.N0000"].expected if fact.metric_code == "PAT")
        assert pat.normalized_value == Decimal("5378093000")
    if "HAYL.N0000" in cases:
        assets = next(
            fact for fact in cases["HAYL.N0000"].expected if fact.metric_code == "TOTAL_ASSETS"
        )
        assert assets.normalized_value == Decimal("67443036000")
        assert assets.reviewer == "v2-pdf-heading-adjudication"
    if "CBNK.N0000" in cases:
        top = next(fact for fact in cases["CBNK.N0000"].expected if fact.metric_code == "TOP_LINE")
        assert top.normalized_value == Decimal("2716705000")
    if "ATL.N0000" in cases:
        eps = next(fact for fact in cases["ATL.N0000"].expected if fact.metric_code == "EPS_BASIC")
        assert eps.normalized_value == Decimal("0.46")
    if "LCBF.N0000" in cases:
        assert cases["LCBF.N0000"].expected == ()
    if "YORK.N0000" in cases:
        assert cases["YORK.N0000"].expected == ()
