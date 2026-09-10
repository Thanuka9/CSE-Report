from __future__ import annotations

from decimal import Decimal

import pytest

from cse_financial_etl.validation.row_safety import suspicious_selected_numeric


@pytest.mark.parametrize(
    ("metric", "raw", "scale", "line"),
    [
        ("PAT", Decimal("2026"), 1, "For the Period Ended 30th June"),
        ("TOP_LINE", Decimal("2773188245"), 1000, "Total"),
        ("PAT", Decimal("-1.18"), 1, "Basic, profit/(loss) for the period attributable to"),
        (
            "TOP_LINE",
            Decimal("3"),
            1000,
            "income. Fair value of the Land has been determined under the Level",
        ),
        (
            "TOP_LINE",
            Decimal("3798"),
            1,
            "Mn in the corresponding quarter of the previous year. "
            "The composition of the Group Revenue",
        ),
    ],
)
def test_structural_non_value_context_is_rejected(
    metric: str, raw: Decimal, scale: int, line: str
) -> None:
    assert suspicious_selected_numeric(metric, raw, scale, line)


def test_normal_financial_statement_rows_remain_eligible() -> None:
    assert not suspicious_selected_numeric(
        "TOP_LINE", Decimal("2897951"), 1000, "Revenue 2,897,951 2,650,180 (9)"
    )
    assert not suspicious_selected_numeric(
        "PAT", Decimal("143221"), 1000, "Profit / (Loss) for the period 143,221 244,723 71"
    )
