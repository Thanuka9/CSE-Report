from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.statements.numeric import parse_numeric


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
