"""Default Phase One equation registry."""

from __future__ import annotations

from cse_financial_etl.validation.balance_sheet import (
    BALANCE_SHEET_IDENTITY,
    BALANCE_SHEET_SANITY,
    evaluate_balance_sheet_identity,
    evaluate_balance_sheet_sanity,
)
from cse_financial_etl.validation.cross_metric import (
    CROSS_METRIC_CONTEXT,
    evaluate_cross_metric_context,
)
from cse_financial_etl.validation.eps import EPS_RECONCILIATION, evaluate_eps_reconciliation
from cse_financial_etl.validation.equation_engine import EquationEngine
from cse_financial_etl.validation.navps import NAVPS_RECONCILIATION, evaluate_navps_reconciliation
from cse_financial_etl.validation.profit_bridge import PAT_TAX_BRIDGE, evaluate_pat_tax_bridge


def build_default_equation_engine(
    *,
    balance_sheet_relative: float = 0.005,
) -> EquationEngine:
    engine = EquationEngine()
    identity = BALANCE_SHEET_IDENTITY
    if balance_sheet_relative != identity.tolerance_relative:
        identity = type(identity)(
            rule_id=identity.rule_id,
            inputs=identity.inputs,
            applicability=identity.applicability,
            severity=identity.severity,
            tolerance_relative=balance_sheet_relative,
            description=identity.description,
        )
    engine.register(identity, evaluate_balance_sheet_identity)
    engine.register(BALANCE_SHEET_SANITY, evaluate_balance_sheet_sanity)
    engine.register(CROSS_METRIC_CONTEXT, evaluate_cross_metric_context)
    engine.register(PAT_TAX_BRIDGE, evaluate_pat_tax_bridge)
    engine.register(EPS_RECONCILIATION, evaluate_eps_reconciliation)
    engine.register(NAVPS_RECONCILIATION, evaluate_navps_reconciliation)
    return engine
