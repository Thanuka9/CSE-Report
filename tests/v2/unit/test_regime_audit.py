from __future__ import annotations

from cse_financial_etl.v2.diagnostics.regime_audit import audit_issuer_regime


def test_regime_audit_does_not_treat_holding_as_mismatch() -> None:
    row = audit_issuer_regime(
        issuer_id="JKH.N0000",
        issuer_name="JOHN KEELLS HOLDINGS PLC",
        issuer_type="HOLDING",
    )
    assert row["v2_inferred_regime"] == "GENERAL"
    assert row["mismatch"] == "NO"
    assert row["standalone_entity"] == "COMPANY"


def test_bank_type_maps_to_bank_regime() -> None:
    row = audit_issuer_regime(
        issuer_id="COMB.N0000",
        issuer_name="COMMERCIAL BANK OF CEYLON PLC",
        issuer_type="BANK",
    )
    assert row["v2_inferred_regime"] == "BANK"
    assert row["standalone_entity"] == "BANK"
