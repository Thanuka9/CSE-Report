"""Synthetic adjudicated V2 golden corpus.

These are contract fixtures, not the institutional 25-40 CSE filing gold set.
Each case has an explicit expected published fact set and/or forbidden publications.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.enums import EntityScope
from cse_financial_etl.v2.diagnostics.golden import GoldenFact
from tests.v2.helpers import canonical_document_from_pages, geometric_document

REVIEWER = "synthetic-adjudicator"
REVIEW_DATE = date(2026, 9, 13)
PERIOD = date(2026, 6, 30)
SCALE_000 = Decimal("1000")


@dataclass(frozen=True)
class SyntheticCase:
    case_id: str
    document: CanonicalDocument
    issuer_id: str
    expected_entity_scope: EntityScope | None
    expected: tuple[GoldenFact, ...]
    must_not_publish: tuple[str, ...] = ()


def _gold(
    *,
    metric: str,
    raw: str,
    entity: EntityScope = EntityScope.COMPANY,
    duration: int | None = 3,
    scale: Decimal | None = SCALE_000,
    period: date = PERIOD,
    normalized: Decimal | None = None,
) -> GoldenFact:
    raw_value = Decimal(raw)
    unit_scale = scale
    if normalized is not None:
        value = normalized
    elif unit_scale is None:
        value = raw_value
    else:
        value = raw_value * unit_scale
    return GoldenFact(
        metric_code=metric,
        raw_value=raw_value,
        normalized_value=value,
        entity_scope=entity,
        period_end=period,
        duration_months=duration,
        unit_scale=unit_scale,
        page=1,
        reviewer=REVIEWER,
        review_date=REVIEW_DATE,
    )


def _income(
    *body: tuple[tuple[float, str], ...],
    entity: str = "Company",
    banner: str = "For the three months ended 30 June 2026",
    unit: str = "Rs '000",
    title: str = "Statement of profit or loss",
    filing_version_id: str = "fv-1",
) -> CanonicalDocument:
    rows = (((40.0, entity),), ((40.0, banner),), ((40.0, unit),), *body)
    return geometric_document(rows, filing_version_id=filing_version_id, title=title)


def _position(
    *body: tuple[tuple[float, str], ...],
    entity: str = "Company",
    banner: str = "As at 30 June 2026",
    unit: str = "Rs '000",
    filing_version_id: str = "fv-1",
) -> CanonicalDocument:
    rows = (((40.0, entity),), ((40.0, banner),), ((40.0, unit),), *body)
    return geometric_document(
        rows,
        filing_version_id=filing_version_id,
        title="Statement of financial position",
    )


def load_synthetic_corpus() -> tuple[SyntheticCase, ...]:
    pat_row = ((40.0, "Profit for the period"), (300.0, "1,234"))
    return (
        SyntheticCase(
            "pat-company-3m-rs000",
            _income(pat_row, filing_version_id="fv-pat"),
            "issuer-pat",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="1234"),),
        ),
        SyntheticCase(
            "pbt-company-3m",
            _income(((40.0, "Profit before tax"), (300.0, "2,000")), filing_version_id="fv-pbt"),
            "issuer-pbt",
            EntityScope.COMPANY,
            (_gold(metric="PBT", raw="2000"),),
        ),
        SyntheticCase(
            "operating-profit",
            _income(((40.0, "Operating profit"), (300.0, "800")), filing_version_id="fv-op"),
            "issuer-op",
            EntityScope.COMPANY,
            (_gold(metric="OPERATING_PROFIT", raw="800"),),
        ),
        SyntheticCase(
            "top-line-revenue",
            _income(((40.0, "Revenue"), (300.0, "9,000")), filing_version_id="fv-rev"),
            "issuer-rev",
            EntityScope.COMPANY,
            (_gold(metric="TOP_LINE", raw="9000"),),
        ),
        SyntheticCase(
            "pat-and-pbt-together",
            _income(
                pat_row,
                ((40.0, "Profit before tax"), (300.0, "1,500")),
                filing_version_id="fv-both",
            ),
            "issuer-both",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="1234"), _gold(metric="PBT", raw="1500")),
        ),
        SyntheticCase(
            "group-expected-group",
            _income(pat_row, entity="GROUP", filing_version_id="fv-group"),
            "issuer-group",
            EntityScope.GROUP,
            (_gold(metric="PAT", raw="1234", entity=EntityScope.GROUP),),
        ),
        SyntheticCase(
            "group-not-converted-to-company",
            _income(pat_row, entity="GROUP", filing_version_id="fv-noconv"),
            "issuer-noconv",
            EntityScope.COMPANY,
            (),
            must_not_publish=("PAT",),
        ),
        SyntheticCase(
            "missing-entity-not-assumed",
            geometric_document(
                (
                    ((40.0, "For the three months ended 30 June 2026"),),
                    ((40.0, "Rs '000"),),
                    pat_row,
                ),
                filing_version_id="fv-noent",
            ),
            "issuer-noent",
            None,
            (),
            must_not_publish=("PAT",),
        ),
        SyntheticCase(
            "six-month-flow-not-published",
            _income(
                pat_row, banner="For the six months ended 30 June 2026", filing_version_id="fv-6m"
            ),
            "issuer-6m",
            EntityScope.COMPANY,
            (),
            must_not_publish=("PAT",),
        ),
        SyntheticCase(
            "year-ended-flow-not-published",
            _income(pat_row, banner="For the year ended 30 June 2026", filing_version_id="fv-12m"),
            "issuer-12m",
            EntityScope.COMPANY,
            (),
            must_not_publish=("PAT",),
        ),
        SyntheticCase(
            "parentheses-negative-pat",
            _income(
                ((40.0, "Profit for the period"), (300.0, "(100)")), filing_version_id="fv-neg"
            ),
            "issuer-neg",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="-100"),),
        ),
        SyntheticCase(
            "dash-is-missing-not-zero",
            _income(((40.0, "Profit for the period"), (300.0, "-")), filing_version_id="fv-dash"),
            "issuer-dash",
            EntityScope.COMPANY,
            (),
            must_not_publish=("PAT",),
        ),
        SyntheticCase(
            "zero-is-published",
            _income(((40.0, "Profit for the period"), (300.0, "0")), filing_version_id="fv-zero"),
            "issuer-zero",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="0"),),
        ),
        SyntheticCase(
            "rs-million-scale",
            _income(pat_row, unit="Rs million", filing_version_id="fv-mn"),
            "issuer-mn",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="1234", scale=Decimal("1000000")),),
        ),
        SyntheticCase(
            "date-30-jun-26",
            _income(
                pat_row, banner="For the three months ended 30-Jun-26", filing_version_id="fv-d1"
            ),
            "issuer-d1",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="1234"),),
        ),
        SyntheticCase(
            "date-iso",
            _income(
                pat_row, banner="For the three months ended 2026-06-30", filing_version_id="fv-d2"
            ),
            "issuer-d2",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="1234"),),
        ),
        SyntheticCase(
            "quarter-ended-banner",
            _income(pat_row, banner="quarter ended 30 June 2026", filing_version_id="fv-qtr"),
            "issuer-qtr",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="1234"),),
        ),
        SyntheticCase(
            "query-target-period-ignored",
            _income(pat_row, filing_version_id="fv-tgt"),
            "issuer-tgt",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="1234", period=PERIOD),),
        ),
        SyntheticCase(
            "comparative-current-only-published",
            geometric_document(
                (
                    ((40.0, "Company"),),
                    ((40.0, "For the three months ended 30 June 2026"), (300.0, "30 June 2025")),
                    ((40.0, "Rs '000"),),
                    ((40.0, "Profit for the period"), (300.0, "1,234"), (420.0, "2,000")),
                ),
                filing_version_id="fv-cmp",
            ),
            "issuer-cmp",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="1234"),),
        ),
        SyntheticCase(
            "bank-gross-income-top-line",
            _income(
                ((40.0, "Gross income"), (300.0, "5,500")),
                entity="Bank",
                filing_version_id="fv-bank",
            ),
            "issuer-bank",
            EntityScope.BANK,
            (_gold(metric="TOP_LINE", raw="5500", entity=EntityScope.BANK),),
        ),
        SyntheticCase(
            "insurance-revenue-top-line",
            _income(
                ((40.0, "Insurance revenue"), (300.0, "3,200")),
                filing_version_id="fv-ins",
            ),
            "issuer-ins",
            EntityScope.COMPANY,
            (_gold(metric="TOP_LINE", raw="3200"),),
        ),
        SyntheticCase(
            "ebitda-not-operating-profit",
            _income(((40.0, "EBITDA"), (300.0, "4,000")), filing_version_id="fv-ebitda"),
            "issuer-ebitda",
            EntityScope.COMPANY,
            (),
            must_not_publish=("OPERATING_PROFIT", "PAT"),
        ),
        SyntheticCase(
            "notes-page-not-income-statement",
            canonical_document_from_pages(
                (("Notes to the financial statements", "Profit for the period 1,234"),),
                filing_version_id="fv-notes",
            ),
            "issuer-notes",
            None,
            (),
            must_not_publish=("PAT",),
        ),
        SyntheticCase(
            "toc-page-not-a-statement",
            canonical_document_from_pages(
                (("Contents", "Statement of profit or loss ............... 2"),),
                filing_version_id="fv-toc",
            ),
            "issuer-toc",
            None,
            (),
            must_not_publish=("PAT",),
        ),
        SyntheticCase(
            "balance-sheet-explicit-liabilities",
            _position(
                ((40.0, "Total assets"), (300.0, "10,000")),
                ((40.0, "Total equity"), (300.0, "4,000")),
                ((40.0, "Total liabilities"), (300.0, "6,000")),
                filing_version_id="fv-bs",
            ),
            "issuer-bs",
            EntityScope.COMPANY,
            (
                _gold(metric="TOTAL_ASSETS", raw="10000", duration=None),
                _gold(metric="TOTAL_EQUITY", raw="4000", duration=None),
                _gold(metric="TOTAL_LIABILITIES", raw="6000", duration=None),
            ),
        ),
        SyntheticCase(
            "eps-basic-per-share-not-scaled",
            geometric_document(
                (
                    ((40.0, "Company"),),
                    ((40.0, "For the three months ended 30 June 2026"),),
                    ((40.0, "cents per share"),),
                    ((40.0, "Basic earnings per share"), (300.0, "2.50")),
                ),
                filing_version_id="fv-eps",
                title="Earnings per share",
            ),
            "issuer-eps",
            EntityScope.COMPANY,
            (
                _gold(
                    metric="EPS_BASIC", raw="2.50", scale=Decimal("1"), normalized=Decimal("2.50")
                ),
            ),
        ),
        SyntheticCase(
            "profit-after-taxation-alias",
            _income(
                ((40.0, "Profit after taxation"), (300.0, "777")), filing_version_id="fv-alias"
            ),
            "issuer-alias",
            EntityScope.COMPANY,
            (_gold(metric="PAT", raw="777"),),
        ),
        SyntheticCase(
            "consolidated-entity",
            _income(pat_row, entity="Consolidated", filing_version_id="fv-cons"),
            "issuer-cons",
            EntityScope.CONSOLIDATED,
            (_gold(metric="PAT", raw="1234", entity=EntityScope.CONSOLIDATED),),
        ),
        SyntheticCase(
            "missing-unit-not-assumed",
            geometric_document(
                (
                    ((40.0, "Company"),),
                    ((40.0, "For the three months ended 30 June 2026"),),
                    pat_row,
                ),
                filing_version_id="fv-nounit",
            ),
            "issuer-nounit",
            EntityScope.COMPANY,
            (),
            must_not_publish=("PAT",),
        ),
        SyntheticCase(
            "missing-period-not-assumed",
            geometric_document(
                (
                    ((40.0, "Company"),),
                    ((40.0, "Rs '000"),),
                    pat_row,
                ),
                filing_version_id="fv-noperiod",
            ),
            "issuer-noperiod",
            EntityScope.COMPANY,
            (),
            must_not_publish=("PAT",),
        ),
    )
