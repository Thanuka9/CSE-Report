"""Independent column-owned context resolvers. Never copy query-target metadata."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Literal, overload

from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalLine, CanonicalPage
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    StatementType,
    UnitDimension,
)
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.contracts.statement import CanonicalStatement, StatementColumn
from cse_financial_etl.v2.statements.detector import (
    HEADING_BAND_LINES,
    StatementRegion,
    detect_statement_regions,
)
from cse_financial_etl.v2.statements.numeric import parse_numeric

_ENTITY_PATTERNS: tuple[tuple[EntityScope, re.Pattern[str]], ...] = (
    (EntityScope.CONSOLIDATED, re.compile(r"\bconsolidated\b", re.I)),
    (EntityScope.GROUP, re.compile(r"\bgroup\b", re.I)),
    (EntityScope.SEPARATE, re.compile(r"\bseparate\b", re.I)),
    (EntityScope.BANK, re.compile(r"\bbank\b", re.I)),
    (EntityScope.COMPANY, re.compile(r"\bcompany\b", re.I)),
)

_DURATION: tuple[tuple[int, re.Pattern[str]], ...] = (
    (3, re.compile(r"\b(?:03|3|three)\s+months?\b|\bquarter ended\b", re.I)),
    (6, re.compile(r"\b(?:06|6|six)\s+months?\b", re.I)),
    (9, re.compile(r"\b(?:09|9|nine)\s+months?\b", re.I)),
    (12, re.compile(r"\b(?:12|twelve)\s+months?\b|\byear ended\b|\bfinancial year\b", re.I)),
)

_COMPARATIVE = re.compile(r"\b(?:prior|previous|comparative|last year)\b", re.I)
_CURRENT = re.compile(r"\bcurrent\b", re.I)
_UNIT_CUE = re.compile(
    r"\brs\.?\b|\blkr\b|\brupees?\b|'000|\bthousands?\b|\bmillions?\b|\bmn\b",
    re.I,
)
_NON_HEADER_LABEL = re.compile(r"\bowners of the company\b|\battributable to\b", re.I)

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_NAMED_DATE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[- ,]+([A-Za-z]{3,9})[- ,]+(20\d{2})\b", re.I)
_MONTH_FIRST_DATE = re.compile(
    r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b", re.I
)
_HYPHEN_SHORT_DATE = re.compile(r"\b(\d{1,2})-([A-Za-z]{3,9})-(\d{2})\b", re.I)
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DOTTED_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2}|\d{2})\b")
_DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[- ,]+([A-Za-z]{3,9})\b", re.I)
_YEAR = re.compile(r"\b(20\d{2})\b")
_FOLLOWING_MONTH = re.compile(r"\s+([A-Za-z]{3,9})\b")
_UNICODE_DASHES = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)


def _fold_dashes(text: str) -> str:
    return text.translate(_UNICODE_DASHES)


def parse_period_end(text: str) -> date | None:
    dates = _dates_in_text(_fold_dashes(text))
    return dates[0] if dates else None


def parse_duration_months(text: str) -> int | None:
    for months, pattern in _DURATION:
        if pattern.search(text):
            return months
    if _QUARTER_WORD.search(text):
        return 3
    return None


def parse_entity_scope(text: str) -> EntityScope | None:
    hits: list[EntityScope] = []
    for scope, pattern in _ENTITY_PATTERNS:
        if pattern.search(text) and scope not in hits:
            hits.append(scope)
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    if set(hits) <= {EntityScope.GROUP, EntityScope.CONSOLIDATED}:
        return hits[0]
    if set(hits) <= {EntityScope.COMPANY, EntityScope.SEPARATE}:
        return hits[0]
    return None


def parse_comparison_role(text: str) -> ComparisonRole | None:
    if _COMPARATIVE.search(text):
        return ComparisonRole.COMPARATIVE
    if _CURRENT.search(text):
        return ComparisonRole.CURRENT
    return None


def parse_unit(text: str) -> tuple[str | None, Decimal | None, UnitDimension | None]:
    lowered = text.casefold()
    currency = None
    if re.search(r"\b(?:rs\.?|lkr|rupees?)\b", lowered):
        currency = "LKR"
    elif re.search(r"\busd\b|us\$", lowered):
        currency = "USD"
    scale = None
    if re.search(r"million|\bmns?\.?\b|\brs\.?\s*mns?\b", lowered):
        scale = Decimal("1000000")
    elif re.search(r"billion|\bbn\b", lowered):
        scale = Decimal("1000000000")
    elif re.search(r"'?\s*000|thousand", lowered):
        scale = Decimal("1000")
    elif currency is not None:
        scale = Decimal("1")
    # Statement-level Rs/'000 wins over an EPS "per share" mention in the same blob.
    if currency is not None:
        return currency, scale, UnitDimension.MONETARY
    if re.search(r"\bcents?\b", lowered) and "share" in lowered:
        return "LKR", Decimal("0.01"), UnitDimension.PER_SHARE
    if "per share" in lowered:
        return "LKR", Decimal("1"), UnitDimension.PER_SHARE
    if "number of share" in lowered:
        return None, Decimal("1"), UnitDimension.COUNT
    if "%" in text or "percent" in lowered:
        return None, Decimal("1"), UnitDimension.PERCENTAGE
    if scale is None:
        return None, None, None
    return currency, scale, UnitDimension.MONETARY


def bind_column_context(
    document: CanonicalDocument,
    statement: CanonicalStatement,
    *,
    expected_entity_scope: EntityScope | None = None,
    target_period_end: date | None = None,
    partial_monetary: Literal["cascade", "per_column"] = "cascade",
    header_engine: Literal["H0", "H1"] = "H0",
    region_hint: StatementRegion | None = None,
) -> CanonicalStatement:
    """Fill column context from heading evidence only. Query targets are not source.

    ``header_engine="H0"`` is the production V2 binder.
    ``header_engine="H1"`` runs the V1-geometry adapter (challenger / bake-off only).
    """

    if header_engine == "H1":
        from cse_financial_etl.v2.resolution.header_h1 import bind_column_context_h1

        return bind_column_context_h1(
            document,
            statement,
            expected_entity_scope=expected_entity_scope,
            target_period_end=target_period_end,
            partial_monetary=partial_monetary,
        )

    del expected_entity_scope, target_period_end  # never copied into source columns
    region = region_hint
    if region is None:
        regions = detect_statement_regions(document)
        region = next((item for item in regions if item.region_id == statement.statement_id), None)
    blob = context_blob(document, region) if region is not None else ""
    blob = blob or " ".join(ref.raw_text or "" for ref in statement.source_refs)
    cover = _cover_heading(document)
    evidence = statement.source_refs[:1]

    dates = header_calendar_dates(blob) or header_calendar_dates(cover)
    kinds = _column_kinds(statement)
    monetary_indices = [index for index, kind in enumerate(kinds) if kind == "monetary"]
    monetary_count = len(monetary_indices)
    duration_banners = _duration_banners(document, region)
    entity_banners = _entity_banners(document, region)
    entity_banner_texts = _entity_banner_texts(document, region)
    date_banners = _date_banners(document, region)
    banner_dates = [parsed for _x, parsed in date_banners]
    if banner_dates and len(banner_dates) == monetary_count:
        period_dates = banner_dates
    elif len(set(banner_dates)) >= 2 and len(banner_dates) > monetary_count > 0:
        trailing = banner_dates[-monetary_count:]
        leading = banner_dates[:monetary_count]
        # Extra title/cover date appended after an alternating current/prior grid
        # (len == monetary_count + 1) rotates pairs if we take the trailing slice.
        if (
            len(banner_dates) == monetary_count + 1
            and banner_dates[0] != banner_dates[1]
            and trailing[0] == banner_dates[1]
            and leading[0] == banner_dates[0]
        ):
            period_dates = leading
        else:
            period_dates = trailing
    else:
        period_dates = dates or banner_dates
    monetary_xs = _monetary_column_xs(statement, monetary_indices)
    columns: list[StatementColumn] = []
    for index, column in enumerate(statement.columns):
        kind = kinds[index]
        if kind == "note":
            columns.append(StatementColumn(column_id=column.column_id))
            continue
        if kind == "percent":
            columns.append(
                StatementColumn(
                    column_id=column.column_id,
                    unit_dimension=UnitDimension.PERCENTAGE,
                    monetary_scale=Decimal("1"),
                    unit_evidence=evidence,
                )
            )
            continue
        position = monetary_indices.index(index)
        period_for_column = _period_for_position(position, period_dates, monetary_count)
        entity = _entity_for_position(
            position,
            monetary_count,
            blob,
            entity_banners,
            column_xs=monetary_xs,
        )
        duration = None
        if statement.statement_type is not StatementType.BALANCE_SHEET:
            duration = _duration_for_position(
                position,
                monetary_count,
                blob,
                duration_banners,
                column_xs=monetary_xs,
            )
            if duration is None:
                duration = parse_duration_months(cover)
        role = _role_for_period(
            period_for_column, period_dates, monetary_count=monetary_count
        )
        unit = parse_unit(blob)
        cover_unit = parse_unit(cover)
        if (unit[1] is None or unit[1] == Decimal("1")) and cover_unit[1] not in {
            None,
            Decimal("1"),
        }:
            unit = (unit[0] or cover_unit[0], cover_unit[1], cover_unit[2] or unit[2])
        if statement.statement_type is StatementType.EPS_NOTE and unit[2] is None:
            unit = ("LKR", Decimal("1"), UnitDimension.PER_SHARE)
        columns.append(
            StatementColumn(
                column_id=column.column_id,
                entity_scope=entity,
                entity_evidence=_entity_evidence_refs(entity, evidence, entity_banner_texts),
                period_end=period_for_column,
                period_evidence=evidence if period_for_column is not None else (),
                duration_months=duration,
                duration_evidence=evidence if duration is not None else (),
                comparison_role=role,
                comparison_evidence=evidence if role is not None else (),
                currency=unit[0],
                monetary_scale=unit[1],
                unit_dimension=unit[2],
                unit_evidence=evidence if unit[2] is not None else (),
            )
        )
    columns = (
        _fail_closed_partial_monetary_columns(statement, columns)
        if partial_monetary == "cascade"
        else columns
    )
    return statement.model_copy(update={"columns": tuple(columns)})


def bind_column_contexts(
    document: CanonicalDocument,
    statements: tuple[CanonicalStatement, ...],
    *,
    expected_entity_scope: EntityScope | None = None,
    target_period_end: date | None = None,
    partial_monetary: Literal["cascade", "per_column"] = "cascade",
    header_engine: Literal["H0", "H1"] = "H0",
) -> tuple[CanonicalStatement, ...]:
    """Bind all statements and apply evidenced cross-page continuation bridges."""

    ordered = sorted(statements, key=lambda item: (item.pages[0], item.pages[-1], item.statement_id))
    bound_by_end: dict[tuple[int, StatementType], CanonicalStatement] = {}
    bound: list[CanonicalStatement] = []
    try:
        from cse_financial_etl.v2.statements.continuation import (  # type: ignore[import-untyped]
            ContinuationBridgeLink,
            bridge_statement_column_context,
            detect_continuation_bridge_links,
        )
    except ImportError:
        return tuple(
            bind_column_context(
                document,
                statement,
                expected_entity_scope=expected_entity_scope,
                target_period_end=target_period_end,
                partial_monetary=partial_monetary,
                header_engine=header_engine,
            )
            for statement in statements
        )

    regions = detect_statement_regions(document)
    region_by_id = {region.region_id: region for region in regions}
    links = detect_continuation_bridge_links(document, regions)
    links_by_to: dict[tuple[int, StatementType], ContinuationBridgeLink] = {
        (link.to_page, link.statement_type): link for link in links
    }
    for statement in ordered:
        region = region_by_id.get(statement.statement_id)
        current = bind_column_context(
            document,
            statement,
            region_hint=region,
            expected_entity_scope=expected_entity_scope,
            target_period_end=target_period_end,
            partial_monetary=partial_monetary,
            header_engine=header_engine,
        )
        if (
            region is not None
            and len(statement.pages) > 1
            and "EXPLICIT_CONTINUATION" in region.reason_codes
        ):
            # Bind page-1 as anchor and continuation pages alone, then evidence-gate
            # inheritance — mirrors V1 _bridge_evidenced_continuation_context.
            anchor_region = region.model_copy(update={"page_end": region.page_start})
            cont_start = statement.pages[1]
            continuation_region = region.model_copy(
                update={"page_start": cont_start, "page_end": region.page_end}
            )
            anchor = bind_column_context(
                document,
                statement,
                region_hint=anchor_region,
                expected_entity_scope=expected_entity_scope,
                target_period_end=target_period_end,
                partial_monetary=partial_monetary,
                header_engine=header_engine,
            )
            continuation = bind_column_context(
                document,
                statement,
                region_hint=continuation_region,
                expected_entity_scope=expected_entity_scope,
                target_period_end=target_period_end,
                partial_monetary=partial_monetary,
                header_engine=header_engine,
            )
            internal = links_by_to.get((cont_start, statement.statement_type))
            if internal is not None and internal.from_page == statement.pages[0]:
                current = bridge_statement_column_context(
                    anchor,
                    continuation,
                    internal,
                    document=document,
                )
            else:
                current = continuation
        cross = links_by_to.get((statement.pages[0], statement.statement_type))
        if cross is not None and cross.from_page == statement.pages[0] - 1:
            previous = bound_by_end.get((cross.from_page, cross.statement_type))
            if previous is not None:
                current = bridge_statement_column_context(
                    previous,
                    current,
                    cross,
                    document=document,
                )
        bound.append(current)
        for page_number in statement.pages:
            bound_by_end[(page_number, statement.statement_type)] = current
    return tuple(bound)


def _fail_closed_partial_monetary_columns(
    statement: CanonicalStatement, columns: list[StatementColumn]
) -> list[StatementColumn]:
    """If only some monetary columns have entity/period, none of them are proven."""

    del statement
    monetary = [
        column for column in columns if column.unit_dimension is UnitDimension.MONETARY
    ]
    if len(monetary) < 2:
        return columns
    resolved = [
        column
        for column in monetary
        if column.entity_scope is not None and column.period_end is not None
    ]
    if not resolved or len(resolved) == len(monetary):
        return columns
    cleared: list[StatementColumn] = []
    for column in columns:
        if column.unit_dimension is not UnitDimension.MONETARY:
            cleared.append(column)
            continue
        cleared.append(
            StatementColumn(
                column_id=column.column_id,
                currency=column.currency,
                monetary_scale=column.monetary_scale,
                unit_dimension=column.unit_dimension,
                unit_evidence=column.unit_evidence,
            )
        )
    return cleared


def context_blob(document: CanonicalDocument, region: StatementRegion | None) -> str:
    """Heading-band text plus on-page unit cues. Body account lines are not a source."""

    if region is None:
        return ""
    pages = {page.page_number: page for page in document.pages}
    texts: list[str] = []
    for page_number in range(region.page_start, region.page_end + 1):
        page = pages.get(page_number)
        if page is None:
            continue
        texts.extend(_page_context_lines(page, region=region))
    return " ".join(texts)


def _cover_heading(document: CanonicalDocument) -> str:
    if not document.pages:
        return ""
    return " ".join(_page_context_lines(document.pages[0]))


def header_calendar_dates(blob: str) -> list[date]:
    blob = _fold_dashes(blob)
    years = [int(text) for text in _YEAR.findall(blob)]
    day_months = _day_months(blob)
    if day_months and years and len(day_months) == len(years):
        aligned: list[date] = []
        for (day, month), year in zip(day_months, years, strict=True):
            parsed = _safe_date(year, month, day)
            if parsed is not None:
                aligned.append(parsed)
        if len(aligned) == len(years):
            return aligned
    unique_dm = _unique_pairs(day_months)
    if unique_dm and len(years) >= 2:
        paired: list[date] = []
        for index, year in enumerate(years):
            day, month = unique_dm[index % len(unique_dm)]
            parsed = _safe_date(year, month, day)
            if parsed is not None:
                paired.append(parsed)
        if paired:
            return paired
    return _dates_in_text(blob)


def context_resolution_metrics(statement: CanonicalStatement) -> dict[str, int]:
    columns = statement.columns
    total = max(len(columns), 1)
    return {
        "columns": len(columns),
        "entity_resolved": sum(column.entity_scope is not None for column in columns),
        "period_resolved": sum(column.period_end is not None for column in columns),
        "duration_resolved": sum(column.duration_months is not None for column in columns),
        "comparison_resolved": sum(column.comparison_role is not None for column in columns),
        "unit_resolved": sum(column.unit_dimension is not None for column in columns),
        "entity_resolution_rate_num": sum(column.entity_scope is not None for column in columns),
        "entity_resolution_rate_den": total,
    }


_ACCOUNT_LINE = re.compile(
    r"\b(?:profit|loss|revenue|income|turnover|assets?|equity|liabilit|cash|"
    r"expense|earnings per share|dividend)\b",
    re.I,
)
_JUNK_HEADER = re.compile(r"docusign|envelope id", re.I)
_STATEMENT_TITLE = re.compile(
    r"income statement|statement of (?:profit|comprehensive|financial|income|cash)|"
    r"financial position|balance sheet|(?:consolidated|company|group|bank)\s+income statement",
    re.I,
)
_DURATION_BANNER: tuple[tuple[int, re.Pattern[str]], ...] = (
    (12, re.compile(r"\b(?:12|twelve)\s+months?\b|\byear ended\b|\bfinancial year\b", re.I)),
    (9, re.compile(r"\b(?:09|9|nine)\s+months?\b", re.I)),
    (6, re.compile(r"\b(?:06|6|six)\s+months?\b", re.I)),
    (3, re.compile(r"\b(?:03|3|three)\s+months?\b|\bquarter ended\b", re.I)),
)
_QUARTER_WORD = re.compile(r"\bquarters?\b", re.I)
_PERIOD_WORD = re.compile(r"\bperiod\b", re.I)
_THREE_WORD = re.compile(r"\bthree\b", re.I)
_NINE_WORD = re.compile(r"\bnine\b", re.I)
_MONTHS_WORD = re.compile(r"\bmonths?\b", re.I)


def _has_entity_scope_cue(text: str) -> bool:
    """True when text carries an explicit Group/Company/Bank/Consolidated banner.

    Issuer-name-only lines (e.g. ``Foo PLC``) are excluded so G01 stay fail-closed.
    """

    if _issuer_name_entity_line(text):
        return False
    return any(pattern.search(text) for _scope, pattern in _ENTITY_PATTERNS)


def _is_entity_bearing_subtitle(line: CanonicalLine) -> bool:
    """Keep Group/Company statement subtitles; do not keep account rows mentioning Group."""

    if not _has_entity_scope_cue(line.text):
        return False
    values = [
        parsed
        for token in line.tokens
        if (parsed := parse_numeric(token.text)) is not None
    ]
    if len(values) >= 2:
        return False
    if len(values) == 1:
        value = values[0]
        # Allow a calendar year on a subtitle; reject a lone monetary amount.
        return bool(1900 <= abs(value) <= 2100 and value == value.to_integral())
    return True


@overload
def _heading_context_lines(
    page: CanonicalPage, *, return_indices: Literal[False] = False
) -> list[CanonicalLine]:
    ...


@overload
def _heading_context_lines(
    page: CanonicalPage, *, return_indices: Literal[True]
) -> list[tuple[int, CanonicalLine]]:
    ...


def _heading_context_lines(
    page: CanonicalPage,
    *,
    return_indices: bool = False,
) -> list[CanonicalLine] | list[tuple[int, CanonicalLine]]:
    lines: list[CanonicalLine] = []
    indexed: list[tuple[int, CanonicalLine]] = []
    for index, line in enumerate(page.lines):
        if _skip_context_line(line):
            continue
        if index < HEADING_BAND_LINES:
            # Keep entity-bearing statement subtitles even when they also look
            # account-like (e.g. "Comprehensive Income - Group 31st December 2025").
            if (
                _ACCOUNT_LINE.search(line.text)
                and any(parse_numeric(token.text) is not None for token in line.tokens)
                and not _STATEMENT_TITLE.search(line.text)
                and not _UNIT_CUE.search(line.text)
                and not _is_entity_bearing_subtitle(line)
            ):
                continue
            lines.append(line)
            indexed.append((index, line))
            continue
        if _UNIT_CUE.search(line.text) and not _ACCOUNT_LINE.search(line.text):
            lines.append(line)
            indexed.append((index, line))
    if return_indices:
        return indexed
    return lines


def _page_context_lines(page: CanonicalPage, *, region: StatementRegion | None = None) -> list[str]:
    lines = _heading_context_lines(page)
    if region is None or (region.segment_start_line is None and region.segment_end_line is None):
        return [line.text for line in lines]
    indexed = _heading_context_lines(page, return_indices=True)
    filtered: list[str] = []
    for line_index, line in indexed:
        if page.page_number == region.page_start and line_index < (region.segment_start_line or 0):
            continue
        if page.page_number == region.page_end and line_index >= (region.segment_end_line or len(page.lines)):
            continue
        filtered.append(line.text)
    return filtered


def _skip_context_line(line: CanonicalLine) -> bool:
    if _JUNK_HEADER.search(line.text) or _NON_HEADER_LABEL.search(line.text):
        return True
    if _STATEMENT_TITLE.search(line.text):
        return False
    if _is_entity_bearing_subtitle(line):
        return False
    if _dates_in_text(line.text):
        return False
    if _day_months(line.text):
        return False
    if _UNIT_CUE.search(line.text) and not _ACCOUNT_LINE.search(line.text):
        return False
    values: list[Decimal] = []
    for token in line.tokens:
        parsed = parse_numeric(token.text)
        if parsed is not None:
            values.append(parsed)
    if len(values) >= 2:
        if all(1900 <= abs(value) <= 2100 and value == value.to_integral() for value in values):
            return False
        return not (
            any(pattern.search(line.text) for _months, pattern in _DURATION_BANNER)
            or _QUARTER_WORD.search(line.text)
            or _PERIOD_WORD.search(line.text)
        )
    return bool(_ACCOUNT_LINE.search(line.text) and values)


def _match_x(line: CanonicalLine, match: re.Match[str]) -> float:
    cursor = 0
    for token in line.tokens:
        start = cursor
        end = cursor + len(token.text)
        if start <= match.start() < end:
            width = max(token.bbox[2] - token.bbox[0], 1.0)
            frac = (match.start() - start) / max(len(token.text), 1)
            return token.bbox[0] + width * frac
        cursor = end + 1
    return (line.bbox[0] + line.bbox[2]) / 2.0


def _iter_heading_lines(
    document: CanonicalDocument, region: StatementRegion | None
) -> list[CanonicalLine]:
    if region is None:
        return []
    pages = {page.page_number: page for page in document.pages}
    lines: list[CanonicalLine] = []
    for page_number in range(region.page_start, region.page_end + 1):
        page = pages.get(page_number)
        if page is None:
            continue
        indexed = _heading_context_lines(page, return_indices=True)
        for line_index, line in indexed:
            if (
                region.segment_start_line is not None
                and page_number == region.page_start
                and line_index < region.segment_start_line
            ):
                continue
            if (
                region.segment_end_line is not None
                and page_number == region.page_end
                and line_index >= region.segment_end_line
            ):
                continue
            lines.append(line)
    return lines


def _date_banners(
    document: CanonicalDocument, region: StatementRegion | None
) -> list[tuple[float, date]]:
    found: list[tuple[float, date]] = []
    for line in _iter_heading_lines(document, region):
        for match, parsed in _iter_date_matches(line.text):
            found.append((_match_x(line, match), parsed))
    found.sort(key=lambda item: item[0])
    return _dedupe_nearby_date_banners(found)


def _dedupe_nearby_date_banners(
    banners: list[tuple[float, date]], *, min_gap: float = 15.0
) -> list[tuple[float, date]]:
    """Collapse title/date-row collisions that share nearly the same x.

    NHL-style grids emit an extra ``31st December 2025`` from a duration title
    within a few points of the real ``31.12.2024`` column date. Keeping the
    rightward banner preserves the date-row token.
    """

    if not banners:
        return banners
    out: list[tuple[float, date]] = [banners[0]]
    for x, parsed in banners[1:]:
        prev_x, _prev = out[-1]
        if x - prev_x < min_gap:
            out[-1] = (x, parsed)
        else:
            out.append((x, parsed))
    return out


def _iter_date_matches(text: str) -> list[tuple[re.Match[str], date]]:
    text = _fold_dashes(text)
    found: list[tuple[re.Match[str], date]] = []
    for match in _NAMED_DATE.finditer(text):
        parsed = _named_date(match, text)
        if parsed is not None:
            found.append((match, parsed))
    for match in _MONTH_FIRST_DATE.finditer(text):
        month = _MONTHS.get(match.group(1).lower().rstrip("."))
        parsed = _safe_date(int(match.group(3)), month, int(match.group(2))) if month else None
        if parsed is not None:
            found.append((match, parsed))
    for match in _HYPHEN_SHORT_DATE.finditer(text):
        parsed = _named_date(match, text)
        if parsed is not None:
            found.append((match, parsed))
    for match in _DOTTED_DATE.finditer(text):
        parsed = _numeric_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed is not None:
            found.append((match, parsed))
    for match in _SLASH_DATE.finditer(text):
        parsed = _numeric_date(
            int(match.group(1)),
            int(match.group(2)),
            _year_from_raw(match.group(3), text[match.end() :]),
        )
        if parsed is not None:
            found.append((match, parsed))
    for match in _ISO_DATE.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed is not None:
            found.append((match, parsed))
    found.sort(key=lambda item: item[0].start())
    return found


def _duration_banners(
    document: CanonicalDocument, region: StatementRegion | None
) -> list[tuple[float, int]]:
    lines = [line for line in _iter_heading_lines(document, region)]
    found: list[tuple[float, int]] = []
    for index, line in enumerate(lines):
        for months, pattern in _DURATION_BANNER:
            for match in pattern.finditer(line.text):
                found.append((_match_x(line, match), months))
        next_text = lines[index + 1].text if index + 1 < len(lines) else ""
        wrapped_months = bool(_MONTHS_WORD.search(line.text) or _MONTHS_WORD.search(next_text))
        if wrapped_months:
            for match in _THREE_WORD.finditer(line.text):
                found.append((_match_x(line, match), 3))
            for match in _NINE_WORD.finditer(line.text):
                found.append((_match_x(line, match), 9))
        for match in _QUARTER_WORD.finditer(line.text):
            found.append((_match_x(line, match), 3))
        for match in _PERIOD_WORD.finditer(line.text):
            # "For the period ended <date>" is a period-end cue, not a YTD
            # duration banner. Bare column headers like "Period" beside
            # "Quarter" still participate in duration pairing.
            if re.search(r"\bperiod\s+ended\b", line.text, re.I):
                continue
            found.append((_match_x(line, match), 0))
    found.sort(key=lambda item: item[0])
    has_explicit_quarter = any(_QUARTER_WORD.search(line.text) for line in lines)
    has_nine = any(months == 9 for _x, months in found)
    resolved: list[tuple[float, int]] = []
    seen: set[tuple[float, int]] = set()
    for x, months in found:
        mapped = months
        if months == 0:
            if not has_explicit_quarter:
                continue
            mapped = 9 if has_nine else 6
        key = (round(x, 1), mapped)
        if key in seen:
            continue
        seen.add(key)
        resolved.append((x, mapped))
    resolved.sort(key=lambda item: item[0])
    return resolved


def _entity_banners(
    document: CanonicalDocument, region: StatementRegion | None
) -> list[tuple[float, EntityScope]]:
    found: list[tuple[float, EntityScope, bool]] = []
    for line in _iter_heading_lines(document, region):
        issuer_only = _issuer_name_entity_line(line.text)
        for scope, pattern in _ENTITY_PATTERNS:
            for match in pattern.finditer(line.text):
                found.append((_match_x(line, match), scope, issuer_only))
    found.sort(key=lambda item: item[0])
    column_headers = [(x, scope) for x, scope, issuer_only in found if not issuer_only]
    if column_headers:
        return column_headers
    return []


def _entity_banner_texts(
    document: CanonicalDocument, region: StatementRegion | None
) -> tuple[str, ...]:
    """Distinct heading lines that contributed non-issuer entity banners."""

    texts: list[str] = []
    seen: set[str] = set()
    for line in _iter_heading_lines(document, region):
        if _issuer_name_entity_line(line.text):
            continue
        if not any(pattern.search(line.text) for _scope, pattern in _ENTITY_PATTERNS):
            continue
        key = line.text.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        texts.append(key)
    return tuple(texts)


def _evidence_from_texts(
    template: tuple[SourceRef, ...], texts: tuple[str, ...]
) -> tuple[SourceRef, ...]:
    """Prefer entity-banner raw_text on a copy of an existing SourceRef template."""

    if not texts or not template:
        return ()
    base = template[0]
    return tuple(base.model_copy(update={"raw_text": text}) for text in texts)


def _entity_evidence_refs(
    entity: EntityScope | None,
    fallback: tuple[SourceRef, ...],
    banner_texts: tuple[str, ...],
) -> tuple[SourceRef, ...]:
    """Prefer banner lines that mention the bound entity over statement.title alone."""

    if entity is None:
        return ()
    matching = tuple(
        text
        for text in banner_texts
        if any(
            scope is entity and pattern.search(text) for scope, pattern in _ENTITY_PATTERNS
        )
    )
    preferred = matching or banner_texts
    from_banners = _evidence_from_texts(fallback, preferred)
    return from_banners or fallback


_PLC_ISSUER_NAME = re.compile(
    r"[\w&.'’/-]+(?:\s+[\w&.'’/-]+){0,12}\s+plc\b",
    re.I,
)


def _issuer_name_entity_line(text: str) -> bool:
    if re.search(r"\bplc\b", text, re.I) is None:
        return False
    distinct = {scope for scope, pattern in _ENTITY_PATTERNS if pattern.search(text)}
    return len(distinct) <= 1


def _strip_issuer_name_phrases(text: str) -> str:
    return _PLC_ISSUER_NAME.sub(" ", text)


def _dates_in_text(text: str) -> list[date]:
    text = _fold_dashes(text)
    found: list[date] = []
    seen: set[date] = set()
    spans: list[tuple[int, date]] = []
    for match in _NAMED_DATE.finditer(text):
        parsed = _named_date(match, text)
        if parsed is not None:
            spans.append((match.start(), parsed))
    for match in _MONTH_FIRST_DATE.finditer(text):
        month = _MONTHS.get(match.group(1).lower().rstrip("."))
        parsed = _safe_date(int(match.group(3)), month, int(match.group(2))) if month else None
        if parsed is not None:
            spans.append((match.start(), parsed))
    for match in _HYPHEN_SHORT_DATE.finditer(text):
        parsed = _named_date(match, text)
        if parsed is not None:
            spans.append((match.start(), parsed))
    for match in _DOTTED_DATE.finditer(text):
        parsed = _numeric_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed is not None:
            spans.append((match.start(), parsed))
    for match in _SLASH_DATE.finditer(text):
        parsed = _numeric_date(
            int(match.group(1)),
            int(match.group(2)),
            _year_from_raw(match.group(3), text[match.end() :]),
        )
        if parsed is not None:
            spans.append((match.start(), parsed))
    for match in _ISO_DATE.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed is not None:
            spans.append((match.start(), parsed))
    for _start, parsed in sorted(spans, key=lambda item: item[0]):
        if parsed not in seen:
            seen.add(parsed)
            found.append(parsed)
    return found


def _named_date(match: re.Match[str], text: str) -> date | None:
    month = _MONTHS.get(match.group(2).lower().rstrip("."))
    if month is None:
        return None
    year = _year_from_raw(match.group(3), text[match.end() :])
    if year is None:
        return None
    return _safe_date(year, month, int(match.group(1)))


def _year_from_raw(raw: str | int | None, rest: str) -> int | None:
    if raw is None:
        return None
    year = int(raw)
    if year >= 100:
        return year if 1900 <= year <= 2100 else None
    following = _FOLLOWING_MONTH.match(rest)
    if following is not None and following.group(1).lower().rstrip(".") in _MONTHS:
        return None
    if year > 31:
        return 1900 + year if year >= 90 else 2000 + year
    return 2000 + year


def _numeric_date(day: int, month: int, year: int | None) -> date | None:
    if year is None:
        return None
    parsed = _safe_date(year if year >= 100 else 2000 + year, month, day)
    if parsed is not None:
        return parsed
    return _safe_date(year if year >= 100 else 2000 + year, day, month)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _day_months(blob: str) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for match in _DAY_MONTH.finditer(blob):
        month = _MONTHS.get(match.group(2).lower().rstrip("."))
        if month is None:
            continue
        found.append((int(match.group(1)), month))
    return found


def _unique_pairs(items: list[tuple[int, int]]) -> list[tuple[int, int]]:
    unique: list[tuple[int, int]] = []
    for item in items:
        if item in unique:
            break
        unique.append(item)
    return unique


def _column_kinds(statement: CanonicalStatement) -> list[str]:
    snapshots: list[tuple[int, list[Decimal], bool]] = []
    for column in statement.columns:
        cells = [
            cell
            for row in statement.rows
            for cell in row.cells
            if cell.column_id == column.column_id
        ]
        percent = (
            bool(cells)
            and sum(1 for cell in cells if cell.raw_text.strip().endswith("%")) * 5
            >= len(cells) * 4
        )
        numbers = [
            cell.parsed_numeric_value for cell in cells if cell.parsed_numeric_value is not None
        ]
        snapshots.append((len(cells), numbers, percent))
    maxima = [
        max((abs(value) for value in numbers), default=Decimal("0"))
        for _count, numbers, _pct in snapshots
    ]
    global_max = max(maxima, default=Decimal("0"))
    kinds: list[str] = []
    for (_count, numbers, percent), column_max in zip(snapshots, maxima, strict=True):
        if not numbers:
            kinds.append("note")
        elif (
            percent
            or (column_max < Decimal("1000") and global_max >= Decimal("10000"))
            or (
                numbers
                and global_max >= Decimal("10000")
                and column_max < Decimal("10000")
                and sum(1 for value in numbers if abs(value) < Decimal("100")) * 2 >= len(numbers)
            )
            or (
                numbers
                and global_max >= Decimal("10000")
                and sum(1 for value in numbers if abs(value) < Decimal("100")) * 5
                >= len(numbers) * 4
            )
        ):
            kinds.append("percent")
        elif (
            all(abs(value) < Decimal("100") for value in numbers) and global_max >= Decimal("10000")
        ) or (
            numbers
            and all(
                value == value.to_integral() and abs(value) < Decimal("100") for value in numbers
            )
            and any(column_max >= Decimal("100") for column_max in maxima)
        ):
            kinds.append("note")
        else:
            kinds.append("monetary")
    return kinds


def _period_for_position(
    position: int, dates: list[date], monetary_count: int | None = None
) -> date | None:
    if not dates:
        return None
    if monetary_count is not None and len(dates) == monetary_count:
        return dates[position]
    if position < len(dates):
        return dates[position]
    return dates[position % len(dates)]


def _entity_from_banner_geometry(
    position: int,
    column_xs: list[float],
    banners: list[tuple[float, EntityScope]],
) -> EntityScope | None:
    """Nearest explicit entity banner owns the monetary column.

    Source geometry only — never invents COMPANY/BANK from issuer identity or
    expected production entity. GROUP banners never relabel as COMPANY/BANK.
    """

    if position < 0 or position >= len(column_xs) or len(banners) < 2 or len(column_xs) < 2:
        return None
    x = column_xs[position]
    nearest = min(banners, key=lambda item: abs(item[0] - x))
    return nearest[1]


def _entity_for_position(
    position: int,
    monetary_count: int,
    blob: str,
    entity_banners: list[tuple[float, EntityScope]] | None = None,
    column_xs: list[float] | None = None,
) -> EntityScope | None:
    scopes = [scope for _x, scope in entity_banners or ()]
    if scopes:
        unique: list[EntityScope] = []
        for scope in scopes:
            if scope not in unique:
                unique.append(scope)
        if (
            column_xs is not None
            and len(unique) >= 2
            and len(entity_banners or ()) > 2
        ):
            banner_xs = [x for x, _scope in entity_banners or ()]
            col_span = max(column_xs) - min(column_xs)
            banner_span = max(banner_xs) - min(banner_xs)
            # Multi-banner grids (e.g. Bank Bank Group Group): nearest banner wins.
            # Two-banner Group|Company stays on left/right half-split below.
            if col_span > 0 and banner_span >= max(40.0, 0.2 * col_span):
                geometric = _entity_from_banner_geometry(
                    position, column_xs, list(entity_banners or ())
                )
                if geometric is not None:
                    return geometric
        if len(scopes) >= 4 and len(unique) == 2 and monetary_count == 6:
            mapped = (scopes[0], scopes[1], scopes[2], scopes[2], scopes[3], scopes[3])
            return mapped[position]
        if len(unique) == 2 and monetary_count >= 2:
            xs = [x for x, _scope in entity_banners or ()]
            spread = max(xs) - min(xs) if xs else 0
            if monetary_count >= 4 or spread >= 80:
                # Preserve banner order (left entity → left monetary half).
                ordered_unique: list[EntityScope] = []
                for _x, scope in sorted(entity_banners or (), key=lambda item: item[0]):
                    if scope not in ordered_unique:
                        ordered_unique.append(scope)
                left, right = (ordered_unique + unique)[:2]
                midpoint = monetary_count // 2
                return left if position < midpoint else right
        if len(unique) == 1:
            return unique[0]
    paired_left, paired_right = _paired_entities(blob)
    if paired_left is not None and paired_right is not None and monetary_count >= 4:
        midpoint = monetary_count // 2
        return paired_left if position < midpoint else paired_right
    # Unlabelled / ambiguous multi-entity blob → leave unresolved (fail closed).
    if paired_left is not None and paired_right is not None:
        return None
    return parse_entity_scope(_strip_issuer_name_phrases(blob))


def _paired_entities(blob: str) -> tuple[EntityScope | None, EntityScope | None]:
    if re.search(r"\bbank\s+group\b", blob, re.I):
        return EntityScope.BANK, EntityScope.GROUP
    if re.search(r"\bgroup\s+bank\b", blob, re.I):
        return EntityScope.GROUP, EntityScope.BANK
    if re.search(r"\bgroup\s+company\b", blob, re.I):
        return EntityScope.GROUP, EntityScope.COMPANY
    if re.search(r"\bcompany\s+group\b", blob, re.I):
        return EntityScope.COMPANY, EntityScope.GROUP
    has_group = re.search(r"\bgroup\b", blob, re.I) is not None
    has_company = re.search(r"\bcompany\b", blob, re.I) is not None
    has_bank = re.search(r"\bbank\b", blob, re.I) is not None
    has_consolidated = re.search(r"\bconsolidated\b", blob, re.I) is not None
    if has_group and has_company:
        return EntityScope.GROUP, EntityScope.COMPANY
    if has_group and has_bank:
        return EntityScope.GROUP, EntityScope.BANK
    if has_consolidated and has_company:
        return EntityScope.CONSOLIDATED, EntityScope.COMPANY
    return None, None


def _monetary_column_xs(
    statement: CanonicalStatement, monetary_indices: list[int]
) -> list[float] | None:
    """Median cell-center x for each monetary column; None when geometry is incomplete."""

    xs: list[float] = []
    for index in monetary_indices:
        column_id = statement.columns[index].column_id
        centers = [
            (cell.source_ref.bbox[0] + cell.source_ref.bbox[2]) / 2.0
            for row in statement.rows
            for cell in row.cells
            if cell.column_id == column_id and cell.source_ref.bbox is not None
        ]
        if not centers:
            return None
        centers.sort()
        xs.append(centers[len(centers) // 2])
    return xs


def _duration_from_banner_geometry(
    position: int,
    column_xs: list[float],
    banners: list[tuple[float, int]],
) -> int | None:
    """Nearest in-field duration banner owns the column (merged quarter/YTD spans).

    Banners whose x falls outside the monetary column field are ignored so left-side
    period-end date cues cannot steal ownership from an explicit Quarter/3M banner.
    Wider repeating Bank|Group duration cycles stay on order-based pair cycling.
    """

    if position < 0 or position >= len(column_xs) or len(column_xs) < 2 or len(banners) < 2:
        return None
    if len(column_xs) > 4 and len(column_xs) % 4 == 0:
        return None
    min_c = min(column_xs)
    max_c = max(column_xs)
    gap = (max_c - min_c) / max(len(column_xs) - 1, 1)
    margin = max(gap, 40.0)
    in_field = [(x, months) for x, months in banners if min_c - margin <= x <= max_c + margin]
    families = {months for _x, months in in_field}
    if len(families) < 2:
        return None
    column_x = column_xs[position]
    return min(in_field, key=lambda item: abs(item[0] - column_x))[1]


def _duration_for_position(
    position: int,
    monetary_count: int,
    blob: str,
    banners: list[tuple[float, int]] | None = None,
    column_xs: list[float] | None = None,
) -> int | None:
    banner_list = list(banners or ())
    if column_xs is not None and len(column_xs) == monetary_count:
        from_geometry = _duration_from_banner_geometry(position, column_xs, banner_list)
        if from_geometry is not None:
            return from_geometry
    from_banners = _cycle_durations(
        position, monetary_count, [months for _x, months in banner_list]
    )
    if from_banners is not None:
        return from_banners
    has_quarter = (
        re.search(r"\bquarter ended\b|\b(?:03|3|three)\s+months?\b", blob, re.I) is not None
    )
    has_six = re.search(r"\b(?:06|6|six)\s+months?\b", blob, re.I) is not None
    has_nine = re.search(r"\b(?:09|9|nine)\s+months?\b", blob, re.I) is not None
    if has_six and has_quarter and monetary_count >= 4:
        three_at = _last_index(blob, r"\bquarter ended\b|\b(?:03|3|three)\s+months?\b")
        six_at = _last_index(blob, r"\b(?:06|6|six)\s+months?\b")
        three_first = three_at is not None and (six_at is None or three_at < six_at)
        return _pair_cycle(position, monetary_count, 3 if three_first else 6, 6 if three_first else 3)
    if has_nine and has_quarter and monetary_count >= 4:
        three_at = _last_index(blob, r"\bquarter ended\b|\b(?:03|3|three)\s+months?\b")
        nine_at = _last_index(blob, r"\b(?:09|9|nine)\s+months?\b")
        three_first = three_at is not None and (nine_at is None or three_at < nine_at)
        return _pair_cycle(position, monetary_count, 3 if three_first else 9, 9 if three_first else 3)
    return parse_duration_months(blob)


def _cycle_durations(position: int, monetary_count: int, banner_months: list[int]) -> int | None:
    if not banner_months or monetary_count < 1:
        return None
    if len(banner_months) == monetary_count:
        return banner_months[position]
    families: list[int] = []
    for months in banner_months:
        if months not in families:
            families.append(months)
    if len(families) < 2 or monetary_count < 4:
        return None
    left, right = families[0], families[1]
    if monetary_count % 4 == 0:
        return _pair_cycle(position, monetary_count, left, right)
    if 12 in families and 3 in families:
        year_count = sum(1 for months in banner_months if months == 12)
        assigned = [12] * min(year_count, monetary_count)
        assigned.extend([3] * (monetary_count - len(assigned)))
        return assigned[position]
    midpoint = monetary_count // 2
    return left if position < midpoint else right


def _pair_cycle(position: int, monetary_count: int, left: int, right: int) -> int:
    cycle = (left, left, right, right)
    if monetary_count % 4 == 0:
        return cycle[position % 4]
    midpoint = monetary_count // 2
    return cycle[0] if position < midpoint else cycle[2]


def _last_index(blob: str, pattern: str) -> int | None:
    matches = list(re.finditer(pattern, blob, re.I))
    return matches[-1].start() if matches else None


def _role_for_period(
    period: date | None, dates: list[date], *, monetary_count: int
) -> ComparisonRole | None:
    if period is None:
        return None
    unique = {item for item in dates}
    if len(unique) >= 2:
        return ComparisonRole.CURRENT if period == max(unique) else ComparisonRole.COMPARATIVE
    return ComparisonRole.CURRENT
