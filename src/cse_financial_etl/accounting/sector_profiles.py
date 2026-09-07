"""Sector / issuer profiles — semantic expectations, never page templates (§16)."""

from __future__ import annotations

from dataclasses import dataclass

from cse_financial_etl.config import IssuerProfile, infer_issuer_type, load_issuers


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
    issuer_type = infer_issuer_type(issuer_name)
    mapping = {
        "BANK": "BANK",
        "FINANCE_COMPANY": "FINANCE_LEASING",
        "INSURANCE": "INSURANCE",
        "CORPORATE": "GENERAL_CORPORATE",
    }
    code = mapping.get(issuer_type, "OTHER")
    if project_root is not None:
        try:
            issuers = load_issuers(project_root)  # type: ignore[arg-type]
            for profile in issuers:
                if isinstance(profile, IssuerProfile) and profile.name.upper() == issuer_name.upper():
                    break
        except Exception:
            pass
    return PROFILES[code]
