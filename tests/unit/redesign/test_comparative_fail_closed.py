from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.compiler.header_tree import CompiledHeaderColumn, _assign_roles
from cse_financial_etl.extraction.statement_extractor import (
    METRIC_RULES,
    _comparison_from_layout,
    _select_layout_value,
)

from .synthetic_pages import make_page, right_aligned, words


def _column(column_id: str, period_end: date) -> CompiledHeaderColumn:
    return CompiledHeaderColumn(
        column_id=column_id,
        entity="COMPANY",
        comparison_role=None,
        duration_months=None,
        period_end=period_end,
        path=(),
        col_idx=int(column_id.removeprefix("c")),
        kind="VALUE",
        temporal_type="instant",
    )


def test_prior_only_compiler_column_is_not_promoted_to_current() -> None:
    """OCR loss of the target column must not make the latest surviving prior date CURRENT."""

    [prior] = _assign_roles(
        [_column("c1", date(2025, 3, 31))],
        target_period_end=date(2026, 3, 31),
    )
    assert prior.comparison_role == "COMPARATIVE"


def test_known_target_marks_only_exact_observed_target_current() -> None:
    prior, current = _assign_roles(
        [
            _column("c1", date(2025, 3, 31)),
            _column("c2", date(2026, 3, 31)),
        ],
        target_period_end=date(2026, 3, 31),
    )
    assert prior.comparison_role == "COMPARATIVE"
    assert current.comparison_role == "CURRENT"


def test_stock_layout_rejects_company_comparative_when_company_current_is_corrupt() -> None:
    """Sathosa-shaped Group/Company table: clean prior Company NAVPS cannot fill current."""

    page = make_page(
        [
            words("STATEMENT OF FINANCIAL POSITION", 40),
            [("Group", 290, 360), ("Company", 470, 560)],
            [
                ("31.03.2026", 290, 350),
                ("31.03.2025", 370, 430),
                ("31.03.2025", 530, 590),
            ],
            [
                *words("Net assets per share", 40),
                right_aligned("649.11", 350),
                right_aligned("330.32", 430),
                ("591i56", 470, 510),  # OCR-corrupted current Company value
                right_aligned("323.36", 590),
            ],
        ],
        width=650,
    )
    navps = next(rule for rule in METRIC_RULES if rule.code == "NAVPS")
    selected = _select_layout_value(
        page,
        page.lines[-1],
        navps,
        "COMPANY",
        date(2026, 3, 31),
    )
    assert selected is None


def test_stock_layout_still_selects_clean_current_company_value() -> None:
    page = make_page(
        [
            words("STATEMENT OF FINANCIAL POSITION", 40),
            [("Group", 290, 360), ("Company", 470, 600)],
            [
                ("31.03.2026", 290, 350),
                ("31.03.2025", 370, 430),
                ("31.03.2026", 470, 530),
                ("31.03.2025", 550, 610),
            ],
            [
                *words("Net assets per share", 40),
                right_aligned("649.11", 350),
                right_aligned("330.32", 430),
                right_aligned("591.56", 530),
                right_aligned("323.36", 610),
            ],
        ],
        width=660,
    )
    navps = next(rule for rule in METRIC_RULES if rule.code == "NAVPS")
    selected = _select_layout_value(
        page,
        page.lines[-1],
        navps,
        "COMPANY",
        date(2026, 3, 31),
    )
    assert selected is not None
    token, value, _score, _graph = selected
    assert value == Decimal("591.56")
    role, _year = _comparison_from_layout(
        page,
        page.lines[-1],
        token,
        date(2026, 3, 31),
        entity="COMPANY",
    )
    assert role == "CURRENT"
