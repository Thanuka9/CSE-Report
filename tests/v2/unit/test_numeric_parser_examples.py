from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.statements.numeric import (
    is_numeric_token,
    parse_numeric,
    split_label_and_values,
)


def test_numeric_parser_source_examples() -> None:
    assert parse_numeric("1,234") == Decimal("1234")
    assert parse_numeric("1,234.56") == Decimal("1234.56")
    assert parse_numeric("(1,234)") == Decimal("-1234")
    assert parse_numeric("-1,234") == Decimal("-1234")
    assert parse_numeric("0") == Decimal("0")
    assert parse_numeric("-") is None
    assert parse_numeric("—") is None
    assert parse_numeric("–") is None
    assert parse_numeric("N/A") is None
    assert parse_numeric("1 234") is None
    assert parse_numeric("1,234-") is None
    assert parse_numeric("1,234*") is None
    assert parse_numeric("O") is None
    assert parse_numeric("12.3%") is None
    assert parse_numeric("(184.4%)") is None


def test_percent_tokens_are_not_numeric_cells() -> None:
    assert is_numeric_token("1,234")
    assert is_numeric_token("(1,234)")
    assert not is_numeric_token("229.1%")
    assert not is_numeric_token("(184.4%)")


def test_split_label_skips_yoy_percent_tokens() -> None:
    label, values = split_label_and_values(
        "Profit before taxation (14,448) (4,390) 229.1% (36,003) 42,672 (184.4%)"
    )
    assert label.startswith("Profit before taxation")
    assert values == ("(14,448)", "(4,390)", "(36,003)", "42,672")
