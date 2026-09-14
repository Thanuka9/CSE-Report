"""Reconstruct rows, columns, header hierarchy, and cells. No metric mapping."""

from __future__ import annotations

import re
from collections import Counter

from cse_financial_etl.v2 import PARSER_NAME_NATIVE, PARSER_VERSION_NATIVE
from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalLine, CanonicalPage
from cse_financial_etl.v2.contracts.enums import StatementType
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.contracts.statement import (
    CanonicalStatement,
    StatementCell,
    StatementColumn,
    StatementRow,
)
from cse_financial_etl.v2.statements.detector import StatementRegion
from cse_financial_etl.v2.statements.numeric import (
    is_numeric_token,
    parse_numeric,
    split_label_and_values,
)
from cse_financial_etl.v2.taxonomy.registry import normalize_label

_VALUE_GAP = 36.0
_HEADER_CUE = re.compile(
    r"\b(?:group|company|bank|consolidated|separate|quarter|months?|ended|ending|"
    r"as at|year|period|rs\.?|lkr|'000|thousand|million|unaudited|audited|"
    r"docusign|envelope id)\b",
    re.IGNORECASE,
)
_MONTH = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE,
)
_ACCOUNT = re.compile(
    r"\b(?:profit|loss|revenue|income|assets?|equity|liabilit|cash|expense|share)\b",
    re.IGNORECASE,
)
_STATEMENT_TITLE = re.compile(
    r"income statement|statement of (?:profit|comprehensive|financial|income|cash)|"
    r"financial position|balance sheet|(?:consolidated|company|group|bank)\s+income statement",
    re.IGNORECASE,
)
_YEAR_HEADER = re.compile(r"^(?:notes?\s+)?(?:20\d{2}\s*)+%?\s*$", re.IGNORECASE)
_DOTTED_DATES = re.compile(r"\b\d{1,2}\.\d{1,2}\.20\d{2}\b")
_SHARE_PARENT = re.compile(
    r"earnings?\s*(?:/\s*\(\s*loss\s*\))?\s*per share|earning per share",
    re.IGNORECASE,
)
_SHARE_QUALIFIER = re.compile(
    r"^(?:[-–—]\s*)?(?:basic|diluted)(?:\s*/\s*diluted)?\b",
    re.IGNORECASE,
)


def _parser(document: CanonicalDocument) -> tuple[str, str]:
    return (
        document.parser_manifest.get("parser_name") or PARSER_NAME_NATIVE,
        document.parser_manifest.get("parser_version") or PARSER_VERSION_NATIVE,
    )


def _ref(
    document: CanonicalDocument,
    line: CanonicalLine,
    page_number: int,
    *,
    raw_text: str | None = None,
    x: float | None = None,
) -> SourceRef:
    parser_name, parser_version = _parser(document)
    token = None
    if raw_text is not None:
        matches = [item for item in line.tokens if item.text == raw_text]
        if matches and x is not None:
            token = min(
                matches,
                key=lambda item: abs(((item.bbox[0] + item.bbox[2]) / 2.0) - x),
            )
        elif matches:
            token = matches[0]
    return SourceRef(
        filing_id=document.filing_version_id,
        filing_version_id=document.filing_version_id,
        source_sha256=document.source_sha256,
        page_number=page_number,
        bbox=token.bbox if token is not None else line.bbox,
        raw_text=raw_text if raw_text is not None else line.text,
        parser_name=parser_name,
        parser_version=parser_version,
    )


def _cluster_columns(xs: list[float]) -> list[tuple[float, float]]:
    if not xs:
        return []
    ordered = sorted(xs)
    groups: list[list[float]] = [[ordered[0]]]
    for x in ordered[1:]:
        if x - groups[-1][-1] <= _VALUE_GAP:
            groups[-1].append(x)
        else:
            groups.append([x])
    return [(min(group), max(group)) for group in groups]


def _intervals_for_body(
    body: list[tuple[int, CanonicalLine, str, list[tuple[float, str]]]],
    *,
    statement_type: StatementType | None = None,
) -> list[tuple[float, float]]:
    value_xs = [x for _page, _line, _label, values in body for x, _text in values]
    clustered = _cluster_columns(value_xs)
    two_value = [values for _page, _line, _label, values in body if len(values) == 2]
    if statement_type is StatementType.EPS_NOTE and len(two_value) >= 2:
        sample = max(two_value, key=lambda values: values[-1][0] - values[0][0])
        return [(x - 12.0, x + 12.0) for x, _text in sample]
    counts = [len(values) for _page, _line, _label, values in body if len(values) >= 2]
    if not counts:
        return clustered
    modal = Counter(counts).most_common(1)[0][0]
    if modal < 4:
        return clustered
    sample = max(
        (values for _page, _line, _label, values in body if len(values) == modal),
        key=lambda values: values[-1][0] - values[0][0],
    )
    return [(x - 12.0, x + 12.0) for x, _text in sample]


def _merged_label(pending: str | None, label: str) -> str:
    label = label.strip()
    if not pending:
        return label
    if not label:
        return pending
    if _SHARE_PARENT.search(pending) and _SHARE_QUALIFIER.match(label):
        parent = pending.rstrip(" -–—")
        qualifier = label.lstrip(" -–—")
        return f"{parent} {qualifier}".strip()
    return label


def _is_pending_label(text: str) -> bool:
    stripped = text.strip()
    if not stripped or _is_header_line(stripped) or _STATEMENT_TITLE.search(stripped):
        return False
    if re.search(r"\bstatement of\b|\bnotes? to\b", stripped, re.IGNORECASE):
        return False
    return bool(_ACCOUNT.search(stripped))


def _is_header_line(text: str) -> bool:
    stripped = text.strip()
    if (
        _STATEMENT_TITLE.search(stripped)
        or _YEAR_HEADER.match(stripped)
        or _DOTTED_DATES.search(stripped)
    ):
        return True
    if _ACCOUNT.search(stripped) or re.search(r"\b(?:basic|diluted)\b", stripped, re.IGNORECASE):
        return False
    return bool(_HEADER_CUE.search(stripped) or _MONTH.search(stripped))


def _line_values(line: CanonicalLine) -> tuple[str, list[tuple[float, str]]]:
    numeric_tokens = [token for token in line.tokens if is_numeric_token(token.text)]
    parsed_tokens = [token for token in numeric_tokens if parse_numeric(token.text) is not None]
    if _is_header_line(line.text):
        return line.text.strip(), []
    if parsed_tokens:
        skip = {id(token) for token in numeric_tokens}
        label_tokens = [token for token in line.tokens if id(token) not in skip]
        label = " ".join(token.text for token in label_tokens).strip()
        values = [
            ((token.bbox[0] + token.bbox[2]) / 2.0, token.text) for token in parsed_tokens
        ]
        return label, values
    label, raw_values = split_label_and_values(line.text)
    if not raw_values:
        return line.text.strip(), []
    # Synthetic single-token rows: space values evenly to the right of the label.
    start = line.bbox[2] - 20.0 * len(raw_values)
    placed = [(start + (index * 80.0), text) for index, text in enumerate(raw_values)]
    return label, placed


def reconstruct_statements(
    document: CanonicalDocument,
    regions: tuple[StatementRegion, ...],
) -> tuple[CanonicalStatement, ...]:
    pages = {page.page_number: page for page in document.pages}
    statements: list[CanonicalStatement] = []
    for region in regions:
        if region.statement_type == StatementType.OTHER_FINANCIAL_STATEMENT:
            continue
        statement = _reconstruct_region(document, pages, region)
        if statement is not None:
            statements.append(statement)
    return tuple(statements)


def _reconstruct_region(
    document: CanonicalDocument,
    pages: dict[int, CanonicalPage],
    region: StatementRegion,
) -> CanonicalStatement | None:
    region_pages = tuple(range(region.page_start, region.page_end + 1))
    lines: list[tuple[int, CanonicalLine]] = []
    for page_number in region_pages:
        page = pages.get(page_number)
        if page is None:
            continue
        for line in page.lines:
            lines.append((page_number, line))
    if not lines:
        return None

    body: list[tuple[int, CanonicalLine, str, list[tuple[float, str]]]] = []
    headers: list[tuple[int, CanonicalLine]] = []
    pending_label: str | None = None
    for page_number, line in lines:
        label, values = _line_values(line)
        if values:
            keep_share_parent = bool(
                pending_label
                and _SHARE_PARENT.search(pending_label)
                and _SHARE_QUALIFIER.match(label.strip())
            )
            label = _merged_label(pending_label, label)
            body.append((page_number, line, label, values))
            if not keep_share_parent:
                pending_label = None
        elif _is_pending_label(label):
            pending_label = label.strip()
        else:
            headers.append((page_number, line))
            pending_label = None

    intervals = _intervals_for_body(body, statement_type=region.statement_type)
    if not intervals:
        # One implicit column when numbers were not geometrically clustered.
        count = max((len(values) for _p, _l, _lab, values in body), default=0)
        intervals = [(float(index * 80), float(index * 80 + 40)) for index in range(count)]
    if not intervals:
        return None

    columns = tuple(
        StatementColumn(column_id=f"{region.region_id}-c{index:02d}")
        for index in range(len(intervals))
    )

    def column_index(x: float) -> int:
        best = 0
        best_distance = float("inf")
        for index, (low, high) in enumerate(intervals):
            center = (low + high) / 2.0
            distance = 0.0 if low - 8 <= x <= high + 8 else abs(x - center)
            if distance < best_distance:
                best = index
                best_distance = distance
        return best

    rows: list[StatementRow] = []
    for row_index, (page_number, line, label, values) in enumerate(body):
        if not label:
            continue
        row_id = f"{region.region_id}-r{row_index:04d}"
        cells: list[StatementCell] = []
        for x, raw in values:
            col_index = column_index(x)
            cell_id = f"{row_id}-{columns[col_index].column_id}"
            cells.append(
                StatementCell(
                    cell_id=cell_id,
                    row_id=row_id,
                    column_id=columns[col_index].column_id,
                    raw_text=raw,
                    parsed_numeric_value=parse_numeric(raw),
                    source_ref=_ref(document, line, page_number, raw_text=raw, x=x),
                )
            )
        rows.append(
            StatementRow(
                row_id=row_id,
                raw_label=label,
                normalized_label=normalize_label(label),
                cells=tuple(cells),
                source_refs=(_ref(document, line, page_number),),
            )
        )

    header_refs = tuple(_ref(document, line, page_number) for page_number, line in headers[:8])
    source_refs = region.source_refs + header_refs
    if not source_refs:
        source_refs = region.source_refs
    return CanonicalStatement(
        statement_id=region.region_id,
        filing_version_id=document.filing_version_id,
        statement_type=region.statement_type,
        pages=region_pages,
        rows=tuple(rows),
        columns=columns,
        source_refs=source_refs,
    )


def header_texts(document: CanonicalDocument, region: StatementRegion) -> tuple[str, ...]:
    pages = {page.page_number: page for page in document.pages}
    texts: list[str] = []
    for page_number in range(region.page_start, region.page_end + 1):
        page = pages.get(page_number)
        if page is None:
            continue
        for line in page.lines[:12]:
            texts.append(line.text)
    return tuple(texts)
