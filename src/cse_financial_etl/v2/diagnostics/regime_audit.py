"""Issuer / accounting-regime audit. Name heuristics are not final truth."""

from __future__ import annotations

from cse_financial_etl.v2.taxonomy.matcher import accounting_regime_for


def audit_issuer_regime(
    *,
    issuer_id: str,
    issuer_name: str = "",
    issuer_type: str = "",
    configured_regime: str | None = None,
) -> dict[str, str | None]:
    inferred = accounting_regime_for(
        issuer_id=issuer_id, issuer_name=issuer_name, issuer_type=issuer_type
    )
    configured = (configured_regime or issuer_type or "").strip().upper() or None
    inferred_value = inferred.value
    mismatch = "NO"
    if configured and configured not in {inferred_value, "HOLDING", "GENERAL"}:
        if configured == "FINANCE" and inferred_value == "FINANCE_COMPANY":
            mismatch = "NO"
        elif configured != inferred_value:
            mismatch = "YES"
    return {
        "issuer": issuer_id,
        "configured_regime": configured,
        "v2_inferred_regime": inferred_value,
        "mismatch": mismatch,
        "standalone_entity": "BANK" if inferred_value == "BANK" else "COMPANY",
        "source": "issuer_type" if issuer_type else "name_heuristic",
    }
