from __future__ import annotations

import json
from pathlib import Path


def test_golden_fixture_has_100_stratified_issuers() -> None:
    path = Path(__file__).resolve().parents[1] / "fixtures" / "golden_financial_facts.json"
    fixtures = json.loads(path.read_text(encoding="utf-8"))
    sample_size = sum(len(row.get("facts", {})) + len(row.get("prices", {})) for row in fixtures)
    assert len(fixtures) >= 100
    assert sample_size >= 100
    banks = sum(1 for row in fixtures if "BANK" in row["issuer_name"].upper())
    finance = sum(
        1
        for row in fixtures
        if any(token in row["issuer_name"].upper() for token in ("FINANCE", "LEASING", "CREDIT"))
    )
    insurance = sum(1 for row in fixtures if "INSUR" in row["issuer_name"].upper())
    holdings = sum(1 for row in fixtures if "HOLDING" in row["issuer_name"].upper())
    assert banks >= 10
    assert finance >= 10
    assert insurance >= 5
    assert holdings >= 5
    symbols = {row["symbol"] for row in fixtures}
    assert {"COMB.N0000", "DIAL.N0000", "JAT.N0000", "JKH.N0000"} <= symbols
    dial = next(row for row in fixtures if row["symbol"] == "DIAL.N0000")
    assert dial["facts"]["TOP_LINE"] == "37231246000"
    assert dial["facts"]["PAT"] == "8187022000"
    jat = next(row for row in fixtures if row["symbol"] == "JAT.N0000")
    assert jat["prices"]["JAT.N0000"] == "39.80"
    jkh = next(row for row in fixtures if row["symbol"] == "JKH.N0000")
    assert "TOTAL_LIABILITIES" not in jkh["facts"]
