"""Deterministic concept eligibility rules (hard constraints before scoring)."""

from __future__ import annotations

FLOW_CONCEPTS = frozenset(
    {
        "TOP_LINE",
        "REVENUE",
        "GROSS_INCOME",
        "OPERATING_PROFIT",
        "PBT",
        "PAT",
        "INCOME_TAX",
        "EPS_BASIC",
        "EPS_DILUTED",
        "GROSS_PROFIT",
        "COST_OF_SALES",
    }
)
STOCK_CONCEPTS = frozenset(
    {
        "TOTAL_ASSETS",
        "TOTAL_EQUITY",
        "TOTAL_LIABILITIES",
        "NAVPS",
        "CURRENT_ASSETS",
        "NON_CURRENT_ASSETS",
        "CURRENT_LIABILITIES",
        "NON_CURRENT_LIABILITIES",
    }
)


def concept_compatible_with_statement(concept: str, statement_type: str) -> bool:
    if statement_type in {"PROFIT_LOSS", "COMPREHENSIVE_INCOME"}:
        return concept in FLOW_CONCEPTS or concept in {
            "ATTRIBUTION_OWNERS",
            "ATTRIBUTION_NCI",
            "CONTINUING_OPERATIONS_RESULT",
            "DISCONTINUED_OPERATIONS_RESULT",
            "WEIGHTED_AVG_SHARES",
        }
    if statement_type == "FINANCIAL_POSITION":
        return concept in STOCK_CONCEPTS or concept in {
            "SHARE_CAPITAL",
            "RESERVES",
            "EQUITY_ATTRIBUTABLE_TO_OWNERS",
            "NCI_EQUITY",
            "ORDINARY_SHARES",
        }
    if statement_type == "SHARE_INFORMATION":
        return concept in {"EPS_BASIC", "EPS_DILUTED", "NAVPS", "WEIGHTED_AVG_SHARES"}
    return True


def requires_exact_3m(concept: str) -> bool:
    from cse_financial_etl.accounting.ontology import PROFIT_LOSS_CONCEPTS

    if concept in {"WEIGHTED_AVG_SHARES", "ORDINARY_SHARES"}:
        return False
    return concept in FLOW_CONCEPTS or concept in PROFIT_LOSS_CONCEPTS


def group_cannot_satisfy_company(required_entity: str, candidate_entity: str) -> bool:
    """Hard rule: Group never populates required Company/Bank."""

    required = required_entity.upper()
    candidate = candidate_entity.upper()
    return required in {"COMPANY", "BANK"} and candidate == "GROUP"
