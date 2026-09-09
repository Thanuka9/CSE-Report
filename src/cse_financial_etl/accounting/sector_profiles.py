"""Sector / issuer profiles — semantic expectations, never page templates (§16)."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass

from cse_financial_etl.config import infer_issuer_type, issuer_profile_for_name, load_issuers


@dataclass(frozen=True, slots=True)
class SectorProfile:
    code: str
    top_line_concepts: tuple[str, ...]
    preferred_entity: str
    formula_notes: tuple[str, ...]


PROFILES: dict[str, SectorProfile] = {
    "GENERAL_CORPORATE": SectorProfile(
        code="GENERAL_CORPORATE",
        top_line_concepts=("REVENUE", "TOP_LINE"),
        preferred_entity="COMPANY",
        formula_notes=("gross_profit_bridge", "pat_pbt_tax"),
    ),
    "BANK": SectorProfile(
        code="BANK",
        top_line_concepts=("GROSS_INCOME", "NET_INTEREST_INCOME", "TOP_LINE"),
        preferred_entity="BANK",
        formula_notes=("bank_gross_income_npm", "pat_pbt_tax"),
    ),
    "FINANCE_LEASING": SectorProfile(
        code="FINANCE_LEASING",
        top_line_concepts=("INTEREST_INCOME", "GROSS_INCOME", "TOP_LINE"),
        preferred_entity="COMPANY",
        formula_notes=("pat_pbt_tax",),
    ),
    "INSURANCE": SectorProfile(
        code="INSURANCE",
        top_line_concepts=("INSURANCE_REVENUE", "GROSS_INCOME", "TOP_LINE"),
        preferred_entity="COMPANY",
        formula_notes=("pat_pbt_tax",),
    ),
    "INVESTMENT_HOLDING": SectorProfile(
        code="INVESTMENT_HOLDING",
        top_line_concepts=("TOP_LINE", "REVENUE"),
        preferred_entity="COMPANY",
        formula_notes=("pat_pbt_tax",),
    ),
    "OTHER": SectorProfile(
        code="OTHER",
        top_line_concepts=("TOP_LINE",),
        preferred_entity="COMPANY",
        formula_notes=("pat_pbt_tax",),
    ),
}


def profile_for_issuer(issuer_name: str, project_root: object | None = None) -> SectorProfile:
    if project_root is not None:
        with suppress(Exception):
            load_issuers(project_root)  # type: ignore[arg-type]

    configured = issuer_profile_for_name(issuer_name)
    issuer_type = (
        configured.issuer_type.strip().upper()
        if configured is not None and configured.issuer_type
        else infer_issuer_type(issuer_name)
    )
    mapping = {
        "BANK": "BANK",
        "FINANCE_COMPANY": "FINANCE_LEASING",
        "FINANCE": "FINANCE_LEASING",
        "LEASING": "FINANCE_LEASING",
        "INSURANCE": "INSURANCE",
        "GENERAL": "GENERAL_CORPORATE",
        "CORPORATE": "GENERAL_CORPORATE",
        "HOLDING": "INVESTMENT_HOLDING",
        "INVESTMENT_HOLDING": "INVESTMENT_HOLDING",
    }
    return PROFILES[mapping.get(issuer_type, "OTHER")]