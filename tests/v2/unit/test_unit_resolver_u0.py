from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import UnitDimension
from cse_financial_etl.v2.resolution.column_context import parse_unit


def test_u0_unit_formats() -> None:
    assert parse_unit("Rs")[0] == "LKR"
    assert parse_unit("LKR")[0] == "LKR"
    assert parse_unit("Rs '000")[1] == Decimal("1000")
    assert parse_unit("LKR '000")[1] == Decimal("1000")
    assert parse_unit("Rs 000")[1] == Decimal("1000")
    assert parse_unit("Rs Mn")[1] == Decimal("1000000")
    assert parse_unit("LKR million")[1] == Decimal("1000000")
    assert parse_unit("Rs Bn")[1] == Decimal("1000000000")
    assert parse_unit("LKR billion")[1] == Decimal("1000000000")
    assert parse_unit("per share")[2] is UnitDimension.PER_SHARE
    assert parse_unit("per share in Rs")[2] is UnitDimension.MONETARY
    usd, usd_scale, usd_dim = parse_unit("USD")
    assert usd == "USD"
    assert usd_scale == Decimal("1")
    assert usd_dim is UnitDimension.MONETARY
    assert parse_unit("USD '000")[1] == Decimal("1000")
    assert parse_unit("USD '000")[0] == "USD"
    percent = parse_unit("Change %")
    assert percent[2] is UnitDimension.PERCENTAGE


def test_u0_cents_per_share_scale_is_one_hundredth() -> None:
    currency, scale, dimension = parse_unit("cents per share")
    assert dimension is UnitDimension.PER_SHARE
    assert scale == Decimal("0.01")
    assert currency == "LKR"
