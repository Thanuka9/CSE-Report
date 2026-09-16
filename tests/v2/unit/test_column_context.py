from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    StatementType,
    UnitDimension,
)
from cse_financial_etl.v2.contracts.statement import CanonicalStatement, StatementColumn
from cse_financial_etl.v2.resolution.column_context import (
    _fail_closed_partial_monetary_columns,
    bind_column_context,
    context_resolution_metrics,
    header_calendar_dates,
    parse_duration_months,
    parse_entity_scope,
    parse_period_end,
    parse_unit,
)
from cse_financial_etl.v2.statements.statement_builder import build_statements
from tests.v2.helpers import canonical_document_from_pages, geometric_document, source_ref


def test_parsers_cover_required_formats() -> None:
    assert parse_period_end("June 30, 2026") == date(2026, 6, 30)
    assert parse_period_end("30-Jun-26") == date(2026, 6, 30)
    assert parse_period_end("30\u2010Jun\u20102026") == date(2026, 6, 30)
    assert parse_period_end("30\u2013Jun\u20132025") == date(2025, 6, 30)
    dates = header_calendar_dates(
        "30\u2010Jun\u20102026 30\u2010Jun\u20102025 30\u2010Jun\u20102026 30\u2010Jun\u20102025"
    )
    assert dates[:4] == [
        date(2026, 6, 30),
        date(2025, 6, 30),
        date(2026, 6, 30),
        date(2025, 6, 30),
    ]
    assert parse_period_end("30th June 2026") == date(2026, 6, 30)
    assert parse_period_end("30 June 2026") == date(2026, 6, 30)
    assert parse_period_end("30/06/2026") == date(2026, 6, 30)
    assert parse_period_end("2026-06-30") == date(2026, 6, 30)
    assert parse_duration_months("03 months") == 3
    assert parse_duration_months("three months") == 3
    assert parse_duration_months("three months ended 30 June 2026") == 3
    assert parse_duration_months("quarter ended") == 3
    assert parse_duration_months("quarter ended 30 June 2026") == 3
    assert parse_duration_months("six months") == 6
    assert parse_duration_months("nine months ended") == 9
    assert parse_duration_months("period ended") is None
    assert parse_duration_months("period ended 30 June 2026") is None
    assert parse_entity_scope("GROUP") is EntityScope.GROUP
    assert parse_entity_scope("Company") is EntityScope.COMPANY
    assert parse_entity_scope("GROUP COMPANY") is None
    currency, scale, dimension = parse_unit("Rs '000")
    assert currency == "LKR"
    assert scale == Decimal("1000")
    assert dimension is UnitDimension.MONETARY
    assert parse_period_end("30 June, 2026") == date(2026, 6, 30)
    assert parse_period_end("30.06.2026") == date(2026, 6, 30)
    assert parse_period_end("30 June, 31 December 2025") == date(2025, 12, 31)
    assert parse_unit("cents per share")[2] is UnitDimension.PER_SHARE
    assert parse_unit("Rs. Change %")[2] is UnitDimension.MONETARY
    assert parse_unit("(In Rs.Mns)")[1] == Decimal("1000000")
    assert parse_unit("Rs. Mn Unaudited")[1] == Decimal("1000000")
    dates = header_calendar_dates(
        "For the three months ended 30 June Notes 2026 2025 Change 2026 2025 Change"
    )
    assert dates[:2] == [date(2026, 6, 30), date(2025, 6, 30)]
    split = header_calendar_dates(
        "As at 30 June 31 December 30 June 31 December 2026 2025 2026 2025"
    )
    assert split[:4] == [
        date(2026, 6, 30),
        date(2025, 12, 31),
        date(2026, 6, 30),
        date(2025, 12, 31),
    ]
    dotted = header_calendar_dates("30.06.2026 30.06.2025 Change 30.06.2026 30.06.2025 Change")
    assert dotted[:2] == [date(2026, 6, 30), date(2025, 6, 30)]
    rs_000, scale, dimension = parse_unit("Rs 000 Basic earnings per share")
    assert rs_000 == "LKR"
    assert scale == Decimal("1000")
    assert dimension is UnitDimension.MONETARY
    assert parse_unit("Rs. 000")[1] == Decimal("1000")


def test_column_context_uses_heading_evidence_not_query_targets() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"), (300.0, "Company")),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(
        document,
        statement,
        expected_entity_scope=EntityScope.GROUP,
        target_period_end=date(1999, 1, 1),
    )
    column = bound.columns[0]
    assert column.entity_scope is EntityScope.COMPANY
    assert column.entity_scope is not EntityScope.GROUP
    assert column.period_end == date(2026, 6, 30)
    assert column.duration_months == 3
    assert column.comparison_role is ComparisonRole.CURRENT
    assert column.monetary_scale == Decimal("1000")
    assert column.entity_evidence
    metrics = context_resolution_metrics(bound)
    assert metrics["entity_resolved"] >= 1
    assert metrics["period_resolved"] >= 1
    assert metrics["unit_resolved"] >= 1


def test_six_month_and_quarter_columns_keep_independent_durations() -> None:
    document = geometric_document(
        (
            ((40.0, "INCOME STATEMENT - BANK"),),
            ((40.0, "For the six months ended For the quarter ended"),),
            ((40.0, "30.06.2026 30.06.2025 30.06.2026 30.06.2025"),),
            ((40.0, "Rs.'000"),),
            (
                (40.0, "Profit for the period"),
                (200.0, "33793334"),
                (300.0, "30051630"),
                (400.0, "16621006"),
                (500.0, "15554770"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.duration_months for column in monetary[:4]] == [6, 6, 3, 3]
    assert monetary[2].period_end == date(2026, 6, 30)
    assert monetary[2].entity_scope is EntityScope.BANK


def test_bank_group_order_and_six_quarter_cycle() -> None:
    document = geometric_document(
        (
            ((40.0, "Bank Group"),),
            ((40.0, "For the six months ended For the quarter ended"),),
            (
                (
                    40.0,
                    "30.06.2026 30.06.2025 30.06.2026 30.06.2025 30.06.2026 30.06.2025 30.06.2026 30.06.2025",
                ),
            ),
            ((40.0, "Rs 000"),),
            (
                (40.0, "Profit for the period"),
                (120.0, "1000"),
                (180.0, "900"),
                (240.0, "500"),
                (300.0, "400"),
                (360.0, "2000"),
                (420.0, "1800"),
                (480.0, "800"),
                (540.0, "700"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.entity_scope for column in monetary[:8]] == [
        EntityScope.BANK,
        EntityScope.BANK,
        EntityScope.BANK,
        EntityScope.BANK,
        EntityScope.GROUP,
        EntityScope.GROUP,
        EntityScope.GROUP,
        EntityScope.GROUP,
    ]
    assert [column.duration_months for column in monetary[:8]] == [6, 6, 3, 3, 6, 6, 3, 3]


def test_majority_small_change_columns_are_percent() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            (
                (40.0, "Gross income"),
                (220.0, "500000"),
                (300.0, "400000"),
                (380.0, "12"),
                (460.0, "18"),
            ),
            (
                (40.0, "Profit for the period"),
                (220.0, "180658"),
                (300.0, "240374"),
                (380.0, "15"),
                (460.0, "1250"),
            ),
            (
                (40.0, "Operating profit"),
                (220.0, "200000"),
                (300.0, "190000"),
                (380.0, "8"),
                (460.0, "9"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    kinds = [column.unit_dimension for column in bound.columns]
    assert UnitDimension.PERCENTAGE in kinds
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert len(monetary) == 2


def test_quarter_listed_before_six_months_uses_three_month_first_cycle() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the quarter ended For the six months ended"),),
            ((40.0, "30.06.2026 30.06.2025 30.06.2026 30.06.2025"),),
            ((40.0, "Rs '000"),),
            (
                (40.0, "Profit for the period"),
                (200.0, "10"),
                (300.0, "9"),
                (400.0, "20"),
                (500.0, "18"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.duration_months for column in monetary[:4]] == [3, 3, 6, 6]


def test_cover_three_months_fills_period_ended_duration() -> None:
    document = canonical_document_from_pages(
        (
            (
                "ACL CABLES PLC",
                "INTERIM FINANCIAL STATEMENTS",
                "FOR THE THREE MONTHS ENDED 30TH JUNE 2026",
            ),
            (
                "CONSOLIDATED STATEMENT OF PROFIT OR LOSS",
                "Group Company",
                "For the period ended 30 June 2026 2025 2026 2025",
                "Rs thousands",
                "Profit for the Period 899,804 718,631 100 90",
            ),
        )
    )
    statement = next(
        item
        for item in build_statements(document)
        if item.statement_type.value == "INCOME_STATEMENT"
    )
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert monetary
    assert all(column.duration_months == 3 for column in monetary)


def test_six_month_x_left_of_later_quarter_banner_uses_geometry() -> None:
    document = geometric_document(
        (
            ((380.0, "Bank"), (560.0, "Group")),
            (
                (280.0, "For the period ended"),
                (400.0, "For the quarter ended"),
                (500.0, "For the period ended"),
                (600.0, "For the quarter ended"),
            ),
            ((40.0, "For the six months ended 30 June"),),
            ((40.0, "Rs 000"),),
            (
                (40.0, "Profit for the period"),
                (120.0, "3903698"),
                (180.0, "5555283"),
                (240.0, "2188790"),
                (300.0, "2737742"),
                (360.0, "4100000"),
                (420.0, "5000000"),
                (480.0, "2000000"),
                (540.0, "2500000"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.duration_months for column in monetary[:8]] == [6, 6, 3, 3, 6, 6, 3, 3]
    assert monetary[2].entity_scope is EntityScope.BANK
    assert monetary[6].entity_scope is EntityScope.GROUP


def test_year_and_three_month_columns_keep_independent_durations() -> None:
    document = geometric_document(
        (
            (
                (80.0, "Consolidated"),
                (180.0, "Company"),
                (320.0, "Consolidated"),
                (460.0, "Company"),
            ),
            (
                (80.0, "Year ended"),
                (180.0, "Year ended"),
                (260.0, "3 months to"),
                (340.0, "3 months to"),
                (420.0, "3 months to"),
                (500.0, "3 months to"),
            ),
            ((40.0, "Rs '000"),),
            (
                (40.0, "Profit for the period"),
                (80.0, "38037737"),
                (160.0, "1500000"),
                (240.0, "2000000"),
                (320.0, "1800000"),
                (400.0, "778655"),
                (480.0, "700000"),
            ),
            (
                (40.0, "Group dividend"),
                (80.0, "100"),
                (160.0, "90"),
                (240.0, "80"),
                (320.0, "70"),
                (400.0, "60"),
                (480.0, "50"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.duration_months for column in monetary[:6]] == [12, 12, 3, 3, 3, 3]
    assert [column.entity_scope for column in monetary[:6]] == [
        EntityScope.CONSOLIDATED,
        EntityScope.COMPANY,
        EntityScope.CONSOLIDATED,
        EntityScope.CONSOLIDATED,
        EntityScope.COMPANY,
        EntityScope.COMPANY,
    ]


def test_growth_columns_beside_six_and_quarter_keep_duration_cycle() -> None:
    document = geometric_document(
        (
            ((80.0, "For the Six Months Ended"), (360.0, "For the Quarter Ended")),
            ((40.0, "Rs '000"),),
            (
                (40.0, "Profit for the period"),
                (120.0, "6080157"),
                (200.0, "5488702"),
                (280.0, "10.78"),
                (360.0, "3174532"),
                (440.0, "2728017"),
                (520.0, "16.37"),
            ),
            (
                (40.0, "Interest income"),
                (120.0, "46942635"),
                (200.0, "39412000"),
                (280.0, "19.09"),
                (360.0, "24000000"),
                (440.0, "20000000"),
                (520.0, "21.12"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert len(monetary) == 4
    assert [column.duration_months for column in monetary] == [6, 6, 3, 3]


def test_change_column_outlier_stays_percent() -> None:
    document = geometric_document(
        (
            ((80.0, "For the Six Months Ended"), (360.0, "For the Quarter Ended")),
            ((40.0, "Rs '000"),),
            (
                (40.0, "Interest income"),
                (120.0, "65063347"),
                (200.0, "53749862"),
                (280.0, "21"),
                (360.0, "3174532"),
                (440.0, "2728017"),
                (520.0, "16"),
            ),
            (
                (40.0, "Profit for the period"),
                (120.0, "16203474"),
                (200.0, "11636548"),
                (280.0, "20975"),
                (360.0, "8000000"),
                (440.0, "7000000"),
                (520.0, "14"),
            ),
            (
                (40.0, "Fee income"),
                (120.0, "15000000"),
                (200.0, "12000000"),
                (280.0, "22"),
                (360.0, "7000000"),
                (440.0, "6000000"),
                (520.0, "17"),
            ),
            (
                (40.0, "Net interest income"),
                (120.0, "22000000"),
                (200.0, "19000000"),
                (280.0, "18"),
                (360.0, "9000000"),
                (440.0, "8000000"),
                (520.0, "13"),
            ),
            (
                (40.0, "Fee and commission income"),
                (120.0, "8000000"),
                (200.0, "7000000"),
                (280.0, "16"),
                (360.0, "4000000"),
                (440.0, "3500000"),
                (520.0, "12"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert len(monetary) == 4
    assert [column.duration_months for column in monetary] == [6, 6, 3, 3]


def test_income_statement_bank_title_with_page_number_keeps_bank() -> None:
    document = geometric_document(
        (
            (
                (40.0, "INCOME"),
                (90.0, "STATEMENT"),
                (180.0, "-"),
                (200.0, "BANK"),
                (500.0, "3"),
            ),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "16,621,006")),
        ),
        title="Statement of profit or loss",
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert monetary
    assert monetary[0].entity_scope is EntityScope.BANK


def test_rs_000_repeated_on_unit_row_keeps_thousand_scale() -> None:
    document = geometric_document(
        (
            ((40.0, "Bank"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs 000 Rs 000 % Rs 000 Rs 000 %"),),
            ((40.0, "Profit for the period"), (300.0, "13,192,754")),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert monetary
    assert monetary[0].monetary_scale == Decimal("1000")
    assert monetary[0].unit_dimension is UnitDimension.MONETARY


def test_issuer_plc_company_does_not_flip_group_company_headers() -> None:
    document = geometric_document(
        (
            ((40.0, "DISTILLERIES COMPANY OF SRI LANKA PLC"),),
            ((200.0, "Group"), (360.0, "Company")),
            ((40.0, "For the quarter ended 30 June 2026 2025 2026 2025"),),
            ((40.0, "Rs '000s"),),
            (
                (40.0, "Profit for the period"),
                (200.0, "1000"),
                (260.0, "900"),
                (360.0, "800"),
                (420.0, "700"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.entity_scope for column in monetary[:4]] == [
        EntityScope.GROUP,
        EntityScope.GROUP,
        EntityScope.COMPANY,
        EntityScope.COMPANY,
    ]


def test_company_in_issuer_name_alone_does_not_bind_company() -> None:
    document = geometric_document(
        (
            ((40.0, "Ceylon Tobacco Company PLC"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "7,694")),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert monetary
    assert monetary[0].entity_scope is None


def test_group_company_order_ignores_owners_of_the_company_body_row() -> None:
    document = geometric_document(
        (
            ((200.0, "Group"), (360.0, "Company")),
            ((40.0, "For the quarter ended 30 June 2026 2025 2026 2025"),),
            ((40.0, "Rs thousands"),),
            (
                (40.0, "- owners of the Company"),
                (200.0, "10114422"),
                (260.0, "5066275"),
                (360.0, "8187022"),
                (420.0, "4011546"),
            ),
            (
                (40.0, "Profit for the period"),
                (200.0, "10113665"),
                (260.0, "5063588"),
                (360.0, "8187022"),
                (420.0, "4011546"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.entity_scope for column in monetary[:4]] == [
        EntityScope.GROUP,
        EntityScope.GROUP,
        EntityScope.COMPANY,
        EntityScope.COMPANY,
    ]


def test_six_column_as_at_grid_keeps_consolidated_company_pairs() -> None:
    document = geometric_document(
        (
            (
                (80.0, "Consolidated"),
                (180.0, "Company"),
                (320.0, "Consolidated"),
                (460.0, "Company"),
            ),
            (
                (80.0, "31.03.26"),
                (180.0, "31.03.26"),
                (260.0, "30.06.26"),
                (340.0, "30.06.25"),
                (420.0, "30.06.26"),
                (500.0, "30.06.25"),
            ),
            ((40.0, "Rs '000"),),
            (
                (40.0, "Total assets"),
                (80.0, "645823764"),
                (160.0, "68498749"),
                (240.0, "686984821"),
                (320.0, "542138694"),
                (400.0, "67443036"),
                (480.0, "58655597"),
            ),
        ),
        title="Statement of financial position",
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.entity_scope for column in monetary[:6]] == [
        EntityScope.CONSOLIDATED,
        EntityScope.COMPANY,
        EntityScope.CONSOLIDATED,
        EntityScope.CONSOLIDATED,
        EntityScope.COMPANY,
        EntityScope.COMPANY,
    ]
    assert [column.period_end for column in monetary[:6]] == [
        date(2026, 3, 31),
        date(2026, 3, 31),
        date(2026, 6, 30),
        date(2025, 6, 30),
        date(2026, 6, 30),
        date(2025, 6, 30),
    ]
    assert all(column.duration_months is None for column in monetary[:6])


def test_period_beside_quarter_is_six_months() -> None:
    document = geometric_document(
        (
            ((80.0, "Bank"), (400.0, "Group")),
            (
                (80.0, "Period"),
                (140.0, "Period"),
                (200.0, "Quarter"),
                (260.0, "Quarter"),
                (400.0, "Period"),
                (460.0, "Period"),
                (520.0, "Quarter"),
                (580.0, "Quarter"),
            ),
            ((40.0, "LKR '000"),),
            (
                (40.0, "Profit for the period"),
                (80.0, "4834272"),
                (140.0, "1926755"),
                (200.0, "3012694"),
                (260.0, "1500000"),
                (400.0, "5000000"),
                (460.0, "2000000"),
                (520.0, "3100000"),
                (580.0, "1600000"),
            ),
        ),
        title="Statement of profit or loss",
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.duration_months for column in monetary[:8]] == [6, 6, 3, 3, 6, 6, 3, 3]


def test_wrapped_three_and_nine_months_keep_quarter_first() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            (
                (80.0, "Three"),
                (160.0, "Three"),
                (280.0, "Nine months to"),
                (400.0, "Nine months to"),
            ),
            ((80.0, "months to"), (160.0, "months to")),
            ((40.0, "(In Rs.Mns)"),),
            (
                (40.0, "Revenue"),
                (80.0, "5816.61"),
                (160.0, "5892.91"),
                (280.0, "15362.42"),
                (400.0, "15883.94"),
            ),
        ),
        title="Statements of Comprehensive Income",
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.duration_months for column in monetary[:4]] == [3, 3, 9, 9]


def test_partially_labeled_monetary_columns_fail_closed() -> None:
    statement = CanonicalStatement(
        statement_id="stmt-1",
        filing_version_id="fv-1",
        statement_type=StatementType.INCOME_STATEMENT,
        pages=(1,),
        columns=(),
        source_refs=(source_ref(),),
    )
    mixed = [
        StatementColumn(
            column_id="c1",
            entity_scope=EntityScope.COMPANY,
            period_end=date(2026, 6, 30),
            unit_dimension=UnitDimension.MONETARY,
        ),
        StatementColumn(
            column_id="c2",
            period_end=date(2026, 6, 30),
            unit_dimension=UnitDimension.MONETARY,
        ),
    ]
    cleared = _fail_closed_partial_monetary_columns(statement, mixed)
    assert all(column.entity_scope is None and column.period_end is None for column in cleared)


def test_period_ended_alone_does_not_invent_three_months() -> None:
    document = geometric_document(
        (
            ((200.0, "GROUP"), (360.0, "COMPANY")),
            ((40.0, "For The Period Ended 30 June 2026"),),
            ((40.0, "Rs 000"),),
            (
                (40.0, "Revenue"),
                (200.0, "3235293"),
                (260.0, "3573705"),
                (360.0, "174300"),
                (420.0, "226638"),
            ),
        ),
        title="Statement of profit or loss",
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert all(column.duration_months is None for column in monetary[:4])


def test_group_only_page_does_not_take_bank_from_issuer_name() -> None:
    document = geometric_document(
        (
            ((40.0, "Seylan Bank PLC"),),
            ((200.0, "Group"), (400.0, "Group")),
            ((80.0, "For the Six Months Ended"), (360.0, "For the Quarter Ended")),
            ((40.0, "Rs '000"),),
            (
                (40.0, "Profit for the period"),
                (120.0, "100"),
                (200.0, "90"),
                (280.0, "80"),
                (360.0, "70"),
            ),
        )
    )
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert monetary
    assert all(column.entity_scope is EntityScope.GROUP for column in monetary)


def test_group_subtitle_with_year_token_stays_in_heading_context() -> None:
    """F1: account-like subtitle + year token must keep entity cues (e.g. Group)."""

    from cse_financial_etl.v2.resolution.column_context import _heading_context_lines

    # Year must be its own token so parse_numeric hits — matching the LITE drop path.
    document = geometric_document(
        (
            (
                (40.0, "Comprehensive"),
                (140.0, "Income"),
                (200.0, "-"),
                (220.0, "Group"),
                (280.0, "31st"),
                (320.0, "December"),
                (400.0, "2025"),
            ),
            ((40.0, "For the three months ended 31 December"), (280.0, "2025"), (360.0, "2024")),
            ((40.0, "Rs.'000"),),
            ((40.0, "Revenue"), (200.0, "889,239"), (300.0, "700,000")),
            ((40.0, "Profit from Operating Activities"), (200.0, "156,042"), (300.0, "100,000")),
            ((40.0, "Net Profit for the Period"), (200.0, "79,190"), (300.0, "50,000")),
        ),
        title="Statement of Profit or Loss and Other",
    )
    heading_texts = [line.text for line in _heading_context_lines(document.pages[0])]
    assert any("Group" in text for text in heading_texts)

    bound = bind_column_context(document, build_statements(document)[0])
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert monetary
    assert all(column.entity_scope is EntityScope.GROUP for column in monetary)
    # F2: entity_evidence prefers the Group banner line over statement title alone.
    assert any(
        "Group" in (ref.raw_text or "")
        for column in monetary
        for ref in column.entity_evidence
    )


def test_account_like_subtitle_without_entity_cue_still_dropped() -> None:
    """Without Group/Company/Bank cues, account-like + year heading lines stay dropped."""

    from cse_financial_etl.v2.resolution.column_context import _heading_context_lines

    document = geometric_document(
        (
            (
                (40.0, "Comprehensive"),
                (140.0, "Income"),
                (280.0, "31st"),
                (320.0, "December"),
                (400.0, "2025"),
            ),
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 31 December 2025"),),
            ((40.0, "Rs.'000"),),
            ((40.0, "Revenue"), (300.0, "1,234")),
        ),
        title="Statement of Profit or Loss and Other",
    )
    heading_texts = [line.text for line in _heading_context_lines(document.pages[0])]
    assert not any(
        "Comprehensive" in text and "Income" in text and "Group" not in text
        for text in heading_texts
        if "Company" not in text
    )
    # Explicit Company banner still binds (separate line).
    bound = bind_column_context(document, build_statements(document)[0])
    monetary = [
        column for column in bound.columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert monetary
    assert monetary[0].entity_scope is EntityScope.COMPANY


def test_issuer_name_plc_line_still_does_not_invent_company_entity() -> None:
    document = geometric_document(
        (
            ((40.0, "Laxapana Holdings PLC"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs."),),
            ((40.0, "Revenue"), (300.0, "1,234")),
        ),
        title="Statement of profit or loss",
    )
    statement = bind_column_context(document, build_statements(document)[0])
    monetary = [
        column
        for column in statement.columns
        if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert monetary
    assert all(column.entity_scope is None for column in monetary)

def test_period_ended_date_cue_does_not_steal_quarter_columns() -> None:
    """F3: merged Period-ended + Quarter + Nine Months — quarter columns own 3M.

    Mirrors LITE page-5 geometry: a left 'For the Period ended' date cue must
    not become a false 9M banner that 1:1-maps onto the leftmost monetary column.
    """

    document = geometric_document(
        (
            ((40.0, "Group"),),
            (
                (45.0, "For the Period ended 31st"),
                (220.0, "Quarter Ended"),
                (400.0, "Nine Months Ended"),
            ),
            ((45.0, "December"),),
            (
                (200.0, "2025"),
                (280.0, "2024"),
                (400.0, "2025"),
                (480.0, "2024"),
            ),
            (
                (190.0, "Rs.'000"),
                (270.0, "Rs.'000"),
                (390.0, "Rs.'000"),
                (470.0, "Rs.'000"),
            ),
            (
                (40.0, "Revenue"),
                (200.0, "889,239"),
                (280.0, "700,000"),
                (400.0, "2,450,908"),
                (480.0, "2,000,000"),
            ),
        ),
        title="Statement of Profit or Loss and Other",
    )
    statement = bind_column_context(document, build_statements(document)[0])
    monetary = [
        column
        for column in statement.columns
        if column.unit_dimension is UnitDimension.MONETARY
    ]
    assert [column.duration_months for column in monetary[:4]] == [3, 3, 9, 9]
