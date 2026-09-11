from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.compiler.header_tree import CompiledHeaderColumn, _assign_roles
from cse_financial_etl.documents.document_ir import BBox, LineIR, PageIR, TokenIR
from cse_financial_etl.extraction.statement_extractor import (
    METRIC_RULES,
    _comparison_from_layout,
    _select_layout_value,
)

from .synthetic_pages import right_aligned, words

TokenSpec = tuple[str, float, float]


def _make_layout_page(
    line_specs: list[list[TokenSpec]],
    *,
    width: float,
    height: float = 840.0,
    y_start: float = 60.0,
    y_step: float = 14.0,
) -> PageIR:
    """Build the extractor's native IR rather than the compiler-only synthetic IR."""

    lines: list[LineIR] = []
    for idx, spec in enumerate(line_specs):
        y0 = y_start + idx * y_step
        y1 = y0 + 10.0
        tokens = tuple(
            TokenIR(
                text=text,
                bbox=BBox(x0, y0, x1, y1),
                block_no=0,
                line_no=idx,
                word_no=word_no,
            )
            for word_no, (text, x0, x1) in enumerate(spec)
        )
        if not tokens:
            continue
        lines.append(
            LineIR(
                page=1,
                line_id=f"p1-l{idx}",
                text=" ".join(token.text for token in tokens),
                bbox=BBox(
                    min(token.bbox.x0 for token in tokens),
                    y0,
                    max(token.bbox.x1 for token in tokens),
                    y1,
                ),
                tokens=tokens,
            )
        )
    return PageIR(
        number=1,
        width=width,
        height=height,
        lines=tuple(lines),
        text="\n".join(line.text for line in lines),
    )


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


def test_single_source_column_role_is_not_rewritten_by_query_context() -> None:
    """A query target cannot relabel a source column as comparative.

    If OCR removes a sibling column, later period/eligibility conflict checks must
    reject the filing mismatch.  The header compiler itself must remain a pure
    function of source evidence.
    """

    [source_column] = _assign_roles([_column("c1", date(2025, 3, 31))])
    assert source_column.comparison_role == "CURRENT"
    assert source_column.evidence["comparison_role"]["source_owned"] is True


def test_source_date_order_marks_relative_roles_without_known_target() -> None:
    prior, current = _assign_roles(
        [
            _column("c1", date(2025, 3, 31)),
            _column("c2", date(2026, 3, 31)),
        ]
    )
    assert prior.comparison_role == "COMPARATIVE"
    assert current.comparison_role == "CURRENT"
    assert prior.evidence["comparison_role"]["source_owned"] is True
    assert current.evidence["comparison_role"]["source_owned"] is True


def test_stock_layout_rejects_company_comparative_when_company_current_is_corrupt() -> None:
    """Sathosa-shaped Group/Company table: clean prior Company NAVPS cannot fill current."""

    page = _make_layout_page(
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
                ("591i56", 470, 510),
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
    page = _make_layout_page(
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
