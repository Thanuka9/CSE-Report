"""Regression tests for curated semantic regex versus fuzzy exclusions."""

from __future__ import annotations

import pytest

from cse_financial_etl.accounting.semantic_candidates import generate_concept_hypotheses


def _concepts(label: str) -> set[str]:
    return {
        hypothesis.concept
        for hypothesis in generate_concept_hypotheses(
            label,
            statement_type="PROFIT_LOSS",
            structural_score=1.0,
            accounting_score=1.0,
        )
    }


@pytest.mark.parametrize(
    "label",
    [
        "Operating profit before tax on financial services",
        "Operating profit before taxes on financial services",
    ],
)
def test_curated_bank_operating_profit_labels_survive_fuzzy_exclusion(label: str) -> None:
    assert "OPERATING_PROFIT" in _concepts(label)


def test_generic_operating_profit_before_tax_remains_blocked() -> None:
    assert "OPERATING_PROFIT" not in _concepts("Operating profit before tax")


def test_profit_before_tax_is_pbt_not_operating_profit() -> None:
    concepts = _concepts("Profit before tax")
    assert "PBT" in concepts
    assert "OPERATING_PROFIT" not in concepts


def test_income_tax_expense_cannot_fuzz_into_revenue() -> None:
    concepts = _concepts("Income tax expense")
    assert "REVENUE" not in concepts
