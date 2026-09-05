from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, NamedTuple

from cse_financial_etl.config import IssuerProfile, infer_entity_scope
from cse_financial_etl.documents.document_ir import (
    BBox,
    DocumentIR,
    LineIR,
    PageIR,
    TokenIR,
    cluster_numeric_columns,
    compact_line,
    extract_document_ir,
)
from cse_financial_etl.documents.pdf_text import PdfPage, extract_layout_pages
from cse_financial_etl.domain.enums import MetricType, UnitScope
from cse_financial_etl.domain.models import UnitCandidate
from cse_financial_etl.extraction.evidence_graph import build_value_graph, summarize_graph
from cse_financial_etl.extraction.semantic_matcher import get_semantic_matcher
from cse_financial_etl.extraction.unit_detector import detect_candidates, resolve_unit
from cse_financial_etl.transformation.normalizer import normalize_value

NCI_OR_GROUP_PAT_RE = re.compile(
    r"non[- ]controlling|minority interest|\bnci\b|owners of the parent|"
    r"holders of the parent|attributable to nci",
    re.I,
)

NUMBER_RE = re.compile(r"(?<![A-Za-z])(?:\(?-?\d[\d,]*(?:\.\d+)?\)?%?|-)(?![A-Za-z])")
NOTE_RE = re.compile(r"^\d{1,2}$")


@dataclass(frozen=True, slots=True)
class MetricRule:
    code: str
    aliases: tuple[re.Pattern[str], ...]
    statement: str
    metric_type: str


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    issuer_name: str
    symbol: str
    period_end: date
    metric_code: str
    metric_type: str
    raw_text: str | None
    raw_value: Decimal | None
    normalized_value: Decimal | None
    currency: str | None
    scale_factor: int | None
    entity_scope: str
    source_page: int | None
    source_line: str | None
    unit_source_text: str | None
    confidence: str
    status: str
    raw_label: str | None = None
    source_bbox: str | None = None
    extraction_method: str = "LAYOUT_TEXT"
    semantic_model: str = "regex"
    semantic_confidence: float = 0.0
    entity_confidence: float = 0.0
    period_confidence: float = 0.0
    unit_confidence: float = 0.0
    column_confidence: float = 0.0
    validation_confidence: float = 0.0
    overall_certainty: float = 0.0
    certainty_band: str = "NONE"
    comparison_role: str = "CURRENT"
    duration_months: int | None = None
    validation_status: str = "NOT_VALIDATED"
    review_status: str = "REVIEW"
    evidence_json: str | None = None

    def as_json(self) -> dict[str, object]:
        result = asdict(self)
        result["period_end"] = self.period_end.isoformat()
        result["raw_value"] = str(self.raw_value) if self.raw_value is not None else None
        result["normalized_value"] = (
            str(self.normalized_value) if self.normalized_value is not None else None
        )
        return result


@dataclass(frozen=True, slots=True)
class QuarterPrice:
    issuer_name: str
    symbol: str
    period_end: date
    value: Decimal | None
    source_page: int | None
    source_line: str | None
    source_method: str
    confidence: str
    status: str
    confidence_score: float = 0.0
    certainty_band: str = "NONE"
    source_bbox: str | None = None
    validation_status: str = "NOT_VALIDATED"


@dataclass(frozen=True, slots=True)
class _LayoutCandidate:
    rule: MetricRule
    page: PageIR
    line: LineIR
    token: TokenIR
    raw_value: Decimal
    raw_label: str
    semantic_model: str
    semantic_confidence: float
    entity_confidence: float
    period_confidence: float
    column_confidence: float
    candidate_score: float
    graph: dict[str, Any]


def _patterns(*aliases: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(alias, re.IGNORECASE) for alias in aliases)


METRIC_RULES: tuple[MetricRule, ...] = (
    MetricRule(
        "TOP_LINE",
        _patterns(
            r"^\s*revenue(?:\s+from\s+contracts.*)?\b",
            r"^\s*total\s+revenue\b",
            r"^\s*net\s+revenue\b",
            r"^\s*(?:net\s+)?sales(?:\s+revenue)?\b(?!\s+and)",
            r"^\s*gross\s+income\b",
            r"^\s*total\s+operating\s+income\b",
            r"^\s*total\s+income\b",
            r"^\s*net\s+operating\s+income\b",
            r"^\s*insurance\s+revenue\b",
            r"^\s*gross\s+written\s+premium\b",
            r"^\s*net\s+earned\s+premiums?\b",
            r"^\s*turnover\b",
        ),
        "FLOW",
        "MONETARY_ABSOLUTE",
    ),
    MetricRule(
        "OPERATING_PROFIT",
        _patterns(
            r"^\s*results?\s+(?:from|of)\s+operating\s+activities\b",
            r"^\s*profit\s*/\s*\(?loss\)?\s+from\s+operations\b",
            r"^\s*operating\s+profit\s*/\s*\(?loss\)?\b",
            r"^\s*operating\s+profit\s+before\s+tax(?:es|ation)?\s+on\s+financial\s+services\b",
            r"^\s*operating\s+profit\b",
            r"^\s*profit\s+from\s+operat(?:ions|ing\s+activities)\b",
            r"^\s*operating\s+results?\b",
            r"^\s*\(?\s*ebit\s*\)?\s*$",
            r"^\s*earnings\s+before\s+interest\s+and\s+tax(?:es|ation)?\b(?!\s+depreciation)",
        ),
        "FLOW",
        "MONETARY_ABSOLUTE",
    ),
    MetricRule(
        "PBT",
        _patterns(
            r"^\s*profit\s*/\s*\(?loss\)?\s+before\s+(?:income\s+)?tax(?:ation)?\b",
            r"^\s*loss\s*/\s*\(?profit\)?\s+before\s+(?:income\s+)?tax(?:ation)?\b",
            r"^\s*(?:loss|profit)\s+before\s+(?:income\s+)?tax(?:ation)?\b",
        ),
        "FLOW",
        "MONETARY_ABSOLUTE",
    ),
    MetricRule(
        "PAT",
        _patterns(
            r"^\s*profit\s*/\s*\(?loss\)?\s+for\s+the\s+(?:period|quarter|year)\b",
            r"^\s*loss\s*/\s*\(?profit\)?\s+for\s+the\s+(?:period|quarter|year)\b",
            r"^\s*(?:net\s+)?(?:loss|profit)\s+for\s+the\s+(?:period|quarter|year)\b",
            r"^\s*profit\s*/\s*\(?loss\)?\s+after\s+(?:income\s+)?tax(?:ation)?\b",
            r"^\s*(?:net\s+)?profit\s+after\s+(?:income\s+)?tax(?:ation)?\b",
            r"^\s*(?:profit|loss).{0,40}attributable\s+to\s+(?:the\s+)?(?:equity\s+holders|owners|shareholders)\b",
        ),
        "FLOW",
        "MONETARY_ABSOLUTE",
    ),
    MetricRule(
        "EPS_BASIC",
        _patterns(
            r"^\s*basic(?:\s*/\s*diluted)?\s+(?:earnings|loss)\s+per\s+(?:ordinary\s+)?share\b",
            r"^\s*(?:earnings|loss)\s+per\s+share.*\bbasic\b",
            r"^\s*earnings?\s*/\s*\(?loss\)?\s+per\s+(?:ordinary\s+)?share\b",
            r"^\s*earnings?\s+per\s+(?:ordinary\s+)?share\b",
            r"^\s*loss\s+per\s+share\s+for\s+the\s+period\b",
            r"^\s*basic\s+eps\b",
            r"^\s*eps\s*\(\s*basic",
            r"^\s*[-–]\s*basic\b",
            r"^\s*basic\b",
        ),
        "FLOW",
        "MONETARY_PER_SHARE",
    ),
    MetricRule(
        "EPS_DILUTED",
        _patterns(
            r"^\s*diluted\s+(?:earnings|loss)\s+per\s+(?:ordinary\s+)?share\b",
            r"^\s*basic\s*/\s*diluted\s+(?:earnings|loss)\s+per\s+(?:ordinary\s+)?share\b",
            r"^\s*(?:earnings|loss)\s+per\s+share.*\bdiluted\b",
            r"^\s*diluted\s+eps\b",
            r"^\s*eps\s*\(\s*diluted",
            r"^\s*[-–]\s*diluted\b",
            r"^\s*diluted\b",
        ),
        "FLOW",
        "MONETARY_PER_SHARE",
    ),
    MetricRule(
        "TOTAL_ASSETS",
        _patterns(r"^\s*total\s+assets\b"),
        "STOCK",
        "MONETARY_ABSOLUTE",
    ),
    MetricRule(
        "TOTAL_EQUITY",
        _patterns(
            r"^\s*total\s+(?:shareholders['’]?\s+)?equity\b",
            r"^\s*equity\s+attributable\s+to\s+(?:equity\s+holders|owners).+\b",
            r"^\s*total\s+shareholders['’]?\s+funds\b",
            r"^\s*shareholders['’]?\s+funds\b",
        ),
        "STOCK",
        "MONETARY_ABSOLUTE",
    ),
    MetricRule(
        "TOTAL_LIABILITIES",
        _patterns(
            r"^\s*total\s+liabilities\b(?!\s+(?:and|&)\s+equity)",
            r"^\s*liabilities\s+total\b",
        ),
        "STOCK",
        "MONETARY_ABSOLUTE",
    ),
    MetricRule(
        "NAVPS",
        _patterns(
            r"^\s*net\s+(?:book\s+value|assets?(?:\s+value)?)\s+per\s+(?:ordinary\s+)?share\b",
            r"^\s*net\s+asset\s+value\s+per\s+(?:ordinary\s+)?share\b",
            r"^\s*nav(?:ps)?\s+per\s+(?:ordinary\s+)?share\b",
            r"^\s*navps\b",
        ),
        "STOCK",
        "MONETARY_PER_SHARE",
    ),
)


def _decimal(token: str) -> Decimal | None:
    if token == "-" or token.endswith("%"):
        return None
    negative = token.startswith("(") and token.endswith(")")
    cleaned = token.strip("()").replace(",", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -value if negative else value


def _numbers(line: str) -> list[tuple[str, Decimal | None]]:
    values = [(match.group(0), _decimal(match.group(0))) for match in NUMBER_RE.finditer(line)]
    if len(values) >= 3 and NOTE_RE.fullmatch(values[0][0]) and values[0][1] is not None:
        values = values[1:]
    while len(values) > 1 and values[0][0] == "-":
        values = values[1:]
    return values


def _header_text(page: PdfPage | PageIR) -> str:
    """Use the full page. Column headers and EPS notes are often below a title block."""

    return page.text


def _page_search_text(page: PdfPage | PageIR) -> str:
    return _header_text(page)


def _is_exact_quarter_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.upper())
    patterns = (
        r"\bQUARTER\s+(?:ENDED|TO)\b",
        r"\b(?:THREE|0?3)\s+MONTHS?\s+(?:ENDED|TO)\b",
        r"\bFOR\s+THE\s+(?:THREE|0?3)\s+MONTHS?\b",
        r"\b(?:THREE|0?3)[- ]MONTH\s+PERIOD\s+(?:ENDED|TO)\b",
        r"\bFIRST\s+QUARTER\b",
        r"\bSECOND\s+QUARTER\b",
        r"\bTHIRD\s+QUARTER\b",
        r"\bFOURTH\s+QUARTER\b",
        r"\b[1-4]\s*Q\s*(?:19|20)?\d{2}\b",
        r"\b[1-4]Q\b",
        r"\bQ[1-4]\b",
        r"\b(?:JAN|JANUARY)\s*[-–]\s*(?:MAR|MARCH)\b",
        r"\b(?:APR|APRIL)\s*[-–]\s*(?:JUN|JUNE)\b",
        r"\b(?:JUL|JULY)\s*[-–]\s*(?:SEP|SEPTEMBER)\b",
        r"\b(?:OCT|OCTOBER)\s*[-–]\s*(?:DEC|DECEMBER)\b",
    )
    if any(re.search(pattern, normalized) for pattern in patterns):
        return True
    # Multi-column PDF headers often emit "Three" and "months to" as
    # separate visual lines. Likewise, bank statements commonly use a bare
    # "Quarter" column beside "Period" columns.
    has_split_three_months = bool(
        re.search(r"\b(?:THREE|0?3)\b", normalized)
        and re.search(r"\bMONTHS?\s+(?:ENDED|TO)\b", normalized)
    )
    return has_split_three_months or bool(re.search(r"\bQUARTER\b", normalized))


def _is_exact_quarter_page(page: PdfPage) -> bool:
    return _is_exact_quarter_text(page.text)


def _duration_months(text: str) -> int | None:
    normalized = re.sub(r"\s+", " ", text.upper())
    duration_patterns = (
        (12, r"\b(?:TWELVE|12)\s+MONTHS?\b|\bYEAR\s+ENDED\b"),
        (9, r"\b(?:NINE|0?9)\s+MONTHS?\b"),
        (6, r"\b(?:SIX|0?6)\s+MONTHS?\b"),
        (3, r"\b(?:THREE|0?3)\s+MONTHS?\b|\bQUARTER\b"),
    )
    for duration, pattern in duration_patterns:
        if re.search(pattern, normalized):
            return duration
    return None


def _statement_score(page: PdfPage, statement: str, entity: str) -> int:
    header = _header_text(page).upper()
    score = 0
    if statement == "FLOW":
        if any(
            term in header
            for term in (
                "PROFIT OR LOSS",
                "INCOME STATEMENT",
                "STATEMENT OF INCOME",
                "COMPREHENSIVE INCOME",
            )
        ):
            score += 20
        if _is_exact_quarter_text(header):
            score += 10
    else:
        if any(term in header for term in ("FINANCIAL POSITION", "BALANCE SHEET")):
            score += 20
        if "AS AT" in header or "AS OF" in header:
            score += 8
    if re.search(rf"\b{entity.upper()}\b", header):
        score += 35
    elif "GROUP" in header or "CONSOLIDATED" in header:
        score -= 45
    return score


def _unit_declaration(line: str) -> bool:
    lowered = line.lower()
    stripped = line.strip()
    return bool(
        re.search(
            r"\ball\s+(?:amounts?|values?|figures?)\b.*\b(?:rs|lkr|rupees?|usd)\b",
            lowered,
        )
        or re.search(r"^\(?\s*in\s+(?:rs|lkr|sri\s+lanka\s+rupees?|usd)", stripped, re.I)
        or re.fullmatch(
            r"(?:\s*(?:rs\.?|lkr|usd)\s*(?:['’]?000s?|mn|mns|million|bn|billion)?\s*)+",
            stripped,
            re.I,
        )
        or re.search(
            r"\b(?:rs\.?|lkr|usd|sri\s+lank(?:a|an)\s+rupees?)\s*"
            r"(?:['’]?0{3}s?|mn(?:s|['’]s)?|millions?|bn(?:s|['’]s)?|billions?)\b",
            stripped,
            re.I,
        )
        or re.search(
            r"\b(?:thousands?|millions?|billions?)\s+of\s+"
            r"(?:sri\s+lank(?:a|an)\s+)?rupees?\b",
            stripped,
            re.I,
        )
    )


def _statement_unit(page: PdfPage) -> tuple[str | None, int | None, str | None]:
    for line in page.text.splitlines():
        if not _unit_declaration(line):
            continue
        candidates = detect_candidates(line, scope=UnitScope.STATEMENT)
        if candidates:
            unit = resolve_unit(candidates)
            return unit.currency, unit.scale_factor, line.strip()
    return None, None, None


def _entity_column_labels(page: PageIR) -> set[str]:
    """Collect Group/Company/Bank labels that look like column headers, not prose."""

    labels: set[str] = set()
    entity_words = {"GROUP", "CONSOLIDATED", "COMPANY", "BANK"}
    filler = entity_words | {"RS", "LKR", "USD", "AND", "THE"}
    for line in page.lines:
        words = [re.sub(r"[^A-Za-z]", "", token.text).upper() for token in line.tokens]
        words = [word for word in words if word]
        found = [word for word in words if word in entity_words]
        if not found:
            continue
        if len(words) <= 8 or all(word in filler or word.isdigit() for word in words):
            labels.update(found)
    return labels


def _is_dual_entity(page: PdfPage | PageIR) -> bool:
    if isinstance(page, PageIR):
        headers = _entity_column_labels(page)
        title = " ".join(line.text for line in page.lines[:12]).upper()
        has_group = bool(headers & {"GROUP", "CONSOLIDATED"}) or bool(
            re.search(r"\b(?:GROUP|CONSOLIDATED)\b", title)
        )
        has_standalone = bool(headers & {"COMPANY", "BANK"})
        return has_group and has_standalone
    header = _page_search_text(page).upper()
    return ("GROUP" in header or "CONSOLIDATED" in header) and (
        "COMPANY" in header or "BANK" in header
    )


def _column_roles(
    *, width: int, has_change: bool, has_quarter: bool, has_ytd: bool
) -> list[str] | None:
    """Classify comparison roles from discovered headers, not from a magic index."""

    if width <= 0:
        return None
    if has_ytd and has_quarter:
        if has_change and width >= 6:
            return [
                "CURRENT_YTD",
                "COMPARATIVE_YTD",
                "CHANGE_YTD",
                "CURRENT",
                "COMPARATIVE",
                "CHANGE",
            ][:width]
        if width >= 4:
            return ["CURRENT_YTD", "COMPARATIVE_YTD", "CURRENT", "COMPARATIVE"][:width]
    if has_change and width >= 3:
        return ["CURRENT", "COMPARATIVE", "CHANGE"][:width]
    if width >= 2:
        return ["CURRENT", "COMPARATIVE"][:width]
    return ["CURRENT"]


def _entity_header_order(header: str) -> list[str]:
    """Prefer short column-header lines over title prose such as Company/Group."""

    for line in header.splitlines():
        tokens = re.findall(r"\b(GROUP|COMPANY|BANK)\b", line)
        unique = list(dict.fromkeys(tokens))
        if len(unique) < 2:
            continue
        leftover = re.sub(r"\b(?:GROUP|COMPANY|BANK|AND|THE|OF|OR)\b", " ", line)
        leftover_words = [word for word in re.findall(r"[A-Z]+", leftover) if word]
        if len(leftover_words) <= 2:
            return unique
    return list(dict.fromkeys(re.findall(r"\b(GROUP|COMPANY|BANK)\b", header)))


def _select_current(
    values: list[tuple[str, Decimal | None]], page: PdfPage, statement: str
) -> tuple[str, Decimal | None] | None:
    """Select the current standalone value from discovered headers, never by magic index."""

    if not values:
        return None
    header = _header_text(page).upper()
    entity_order = _entity_header_order(header)
    has_change = bool(re.search(r"\bCHANGE\b|%", header))
    has_quarter = statement == "STOCK" or _is_exact_quarter_text(header)
    has_ytd = any(
        phrase in header
        for phrase in ("SIX MONTHS", "NINE MONTHS", "TWELVE MONTHS", "YEAR TO DATE", " YTD ")
    )
    standalone = next((item for item in ("COMPANY", "BANK") if item in entity_order), None)
    proven = has_quarter or has_change or bool(re.search(r"\b20\d{2}\b", header)) or len(values) == 1

    def pick(group: list[tuple[str, Decimal | None]]) -> tuple[str, Decimal | None] | None:
        roles = _column_roles(
            width=len(group), has_change=has_change, has_quarter=has_quarter, has_ytd=has_ytd
        )
        if roles is None or "CURRENT" not in roles:
            return None
        return group[roles.index("CURRENT")]

    if standalone and len(entity_order) >= 2 and len(values) >= 2 * len(entity_order):
        group_size = len(values) // len(entity_order)
        group_index = entity_order.index(standalone)
        group = values[group_index * group_size : (group_index + 1) * group_size]
        return pick(group) if group else None
    if not proven:
        return None
    return pick(values)


def _find_metric(page: PdfPage, rule: MetricRule) -> tuple[str, Decimal | None, str] | None:
    lines = page.text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if rule.code == "PAT" and _is_excluded_pat_line(stripped):
            continue
        if not any(pattern.search(stripped) for pattern in rule.aliases):
            continue
        if rule.code in {"EPS_BASIC", "EPS_DILUTED"}:
            label_only = NUMBER_RE.sub(" ", stripped)
            label_only = re.sub(r"\s+", " ", label_only).strip(" :-–").lower()
            if rule.code == "EPS_DILUTED" and "diluted" not in label_only:
                continue
            if (
                rule.code == "EPS_BASIC"
                and re.search(r"\bdiluted\b", label_only)
                and not re.search(r"\bbasic\b", label_only)
            ):
                continue
            if label_only in {"basic", "diluted"} or re.fullmatch(
                r"[-–]?\s*(?:basic|diluted)", label_only
            ):
                nearby = " ".join(lines[max(0, index - 4) : index + 1]).lower()
                if not re.search(
                    r"earnings?\s*/?\s*\(?\s*loss\s*\)?\s+per\s+(?:ordinary\s+)?share|"
                    r"loss\s+per\s+(?:ordinary\s+)?share|\beps\b",
                    nearby,
                ):
                    continue
        values = _numbers(line)
        selected = _select_current(values, page, rule.statement)
        if selected is not None:
            return selected[0], selected[1], line.strip()
    return None


def _bbox_json(bbox: BBox) -> str:
    return json.dumps(asdict(bbox), separators=(",", ":"))


def _metric_label(line: LineIR) -> str:
    segments: list[list[TokenIR]] = []
    current: list[TokenIR] = []
    for token in line.tokens:
        if token.is_numeric:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    if not segments:
        return ""
    label_tokens = max(
        segments,
        key=lambda segment: (
            sum(bool(re.search(r"[A-Za-z]", token.text)) for token in segment),
            sum(len(token.text) for token in segment),
        ),
    )
    label = " ".join(token.text for token in label_tokens)
    return re.sub(r"^\s*\d{1,2}\s+", "", label).strip(" :-–")


def _metric_confidence(line: LineIR, rule: MetricRule) -> tuple[float, str, str]:
    label = _metric_label(line) or line.text
    if any(pattern.search(label) for pattern in rule.aliases):
        return 1.0, "regex+rapidfuzz", label
    semantic = get_semantic_matcher().match(label, rule.code)
    return semantic.score, semantic.model, label


def _is_statement_page(page: PageIR, statement: str) -> bool:
    """Detect a real statement title anywhere on the page, not only the first lines."""

    joined = re.sub(r"\s+", " ", page.text.upper())
    patterns: tuple[str, ...]
    if statement == "FLOW":
        patterns = (
            r"STATEMENTS? OF PROFIT OR LOSS",
            r"STATEMENTS? OF COMPREHENSIVE INCOME",
            r"INCOME STATEMENT",
            r"STATEMENT OF INCOME",
        )
    else:
        patterns = (
            r"STATEMENTS? OF FINANCIAL POSITION",
            r"BALANCE SHEET",
        )
    return any(re.search(pattern, joined) for pattern in patterns)


def _classify_page_statement(page: PageIR) -> str | None:
    text = re.sub(r"\s+", " ", page.text.upper())
    if re.search(
        r"STATEMENT(?:S)? OF CASH FLOWS?|STATEMENT(?:S)? OF CHANGES IN EQUITY",
        text,
    ) and not re.search(r"STATEMENT(?:S)? OF PROFIT OR LOSS|INCOME STATEMENT", text):
        return "OTHER"
    if _is_statement_page(page, "FLOW"):
        return "FLOW"
    if _is_statement_page(page, "STOCK"):
        return "STOCK"
    return None


def _page_statement_map(document: DocumentIR) -> dict[int, str | None]:
    """Carry P&L / balance-sheet context onto untitled continuation pages."""

    current: str | None = None
    mapping: dict[int, str | None] = {}
    for page in document.pages:
        classified = _classify_page_statement(page)
        if classified == "OTHER":
            current = None
        elif classified is not None:
            current = classified
        mapping[page.number] = current
    return mapping


def _page_has_eps(page: PageIR) -> bool:
    return bool(
        re.search(
            r"earnings?\s*/?\s*\(?\s*loss\s*\)?\s+per\s+(?:ordinary\s+)?share|"
            r"loss\s+per\s+(?:ordinary\s+)?share|"
            r"basic\s+(?:and\s+|/\s*)diluted",
            page.text,
            re.I,
        )
    )


def _page_has_navps(page: PageIR) -> bool:
    upper = page.text.upper()
    return bool(re.search(r"NET ASSETS? PER SHARE|NET ASSET VALUE PER|\bNAVPS\b|\bNAPS\b", upper))


def _nearby_text(page: PageIR, line: LineIR, radius: int = 4) -> str:
    lines = list(page.lines)
    try:
        index = lines.index(line)
    except ValueError:
        return line.text
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    return " ".join(item.text for item in lines[start:end])


def _header_points(page: PageIR, line: LineIR, pattern: str) -> list[float]:
    regex = re.compile(pattern, re.I)
    points: list[float] = []
    for header_line in page.lines:
        if header_line.bbox.y0 >= line.bbox.y0:
            break
        for token in header_line.tokens:
            if regex.fullmatch(token.text.strip("():")):
                points.append(token.bbox.center_x)
    return points


def _phrase_occurrences(header_line: LineIR, phrase: str) -> list[tuple[float, float, float]]:
    """Return (x0, x1, center) for each token-span match of a header phrase."""

    words = phrase.lower().split()
    if not words:
        return []
    texts = [token.text.lower() for token in header_line.tokens]
    found: list[tuple[float, float, float]] = []
    for index in range(len(texts) - len(words) + 1):
        if texts[index : index + len(words)] != words:
            continue
        span = header_line.tokens[index : index + len(words)]
        x0 = min(token.bbox.x0 for token in span)
        x1 = max(token.bbox.x1 for token in span)
        center = sum(token.bbox.center_x for token in span) / len(span)
        found.append((x0, x1, center))
    return found


class _HeaderSpan(NamedTuple):
    kind: str
    x0: float
    x1: float
    center: float
    phrase: str


_DURATION_PHRASES: tuple[tuple[str, str], ...] = (
    ("three months", "QUARTER"),
    ("six months", "YTD"),
    ("nine months", "YTD"),
    ("twelve months", "YTD"),
    ("year to date", "YTD"),
)


def _owned_header_regions(spans: list[_HeaderSpan], page_width: float) -> list[_HeaderSpan]:
    """Expand sibling header phrases into parent x-spans that meet at midpoints."""

    ordered = sorted(spans, key=lambda span: span.center)
    owned: list[_HeaderSpan] = []
    for index, span in enumerate(ordered):
        left = 0.0 if index == 0 else (ordered[index - 1].center + span.center) / 2
        right = (
            page_width
            if index == len(ordered) - 1
            else (span.center + ordered[index + 1].center) / 2
        )
        owned.append(_HeaderSpan(span.kind, left, right, span.center, span.phrase))
    return owned


def _duration_parent_regions(page: PageIR, line: LineIR) -> list[_HeaderSpan]:
    """Parent duration spans from the lowest header row that has both 3M and YTD labels.

    Nearest-phrase distance is a fallback only. Sibling labels on one header row
    partition the x-axis so a 3M parent still owns its columns when a 6M token is closer.
    """

    parent_row: list[_HeaderSpan] | None = None
    for header_line in page.lines:
        if header_line.bbox.y0 >= line.bbox.y0:
            break
        spans = [
            _HeaderSpan(kind, x0, x1, center, phrase)
            for phrase, kind in _DURATION_PHRASES
            for x0, x1, center in _phrase_occurrences(header_line, phrase)
        ]
        kinds = {span.kind for span in spans}
        if "QUARTER" in kinds and "YTD" in kinds and len(spans) >= 2:
            parent_row = _owned_header_regions(spans, page.width)
    return parent_row or []


def _parent_kind_at(x: float, regions: list[_HeaderSpan]) -> _HeaderSpan | None:
    for span in regions:
        if span.x0 <= x < span.x1:
            return span
    return None


def _line_points(page: PageIR, line: LineIR, phrase: str) -> list[float]:
    """Locate each occurrence of a header phrase by token span, not line center."""

    points: list[float] = []
    for header_line in page.lines:
        if header_line.bbox.y0 >= line.bbox.y0:
            break
        occurrences = _phrase_occurrences(header_line, phrase)
        if occurrences:
            points.extend(center for _x0, _x1, center in occurrences)
        elif phrase in re.sub(r"\s+", " ", header_line.text.lower()):
            points.append(header_line.bbox.center_x)
    return points


def _closeness(x: float, points: list[float], width: float, span_fraction: float = 0.16) -> float:
    if not points:
        return 0.0
    distance = min(abs(x - point) for point in points)
    return max(0.0, 1.0 - distance / max(width * span_fraction, 1.0))


def _page_entity_confidence(page: PageIR, expected: str, inherited: float | None = None) -> float:
    if _is_dual_entity(page):
        return 0.94
    labels = _entity_column_labels(page)
    title = " ".join(line.text for line in page.lines[:8]).upper()
    header = " ".join(line.text for line in page.lines[:20]).upper()
    explicit_statement = re.search(
        rf"\b{expected}\b.*(?:INCOME STATEMENT|FINANCIAL POSITION|PROFIT OR LOSS)|"
        rf"(?:INCOME STATEMENT|FINANCIAL POSITION|PROFIT OR LOSS).*\b{expected}\b",
        header,
    )
    expected_present = expected.upper() in labels or bool(re.search(rf"\b{expected}\b", title))
    other = "GROUP" if expected in {"COMPANY", "BANK"} else "COMPANY"
    other_present = (
        bool(labels & {"GROUP", "CONSOLIDATED", other})
        or bool(re.search(rf"\b{other}\b", title))
        or "CONSOLIDATED" in title
    )
    if explicit_statement:
        return 1.0
    if expected_present:
        return 0.92 if other_present else 0.96
    if inherited is not None and inherited > 0:
        return inherited
    if expected.upper() not in labels and bool(labels & {"GROUP", "CONSOLIDATED"}):
        return 0.0
    return 0.72


def _select_layout_value(
    page: PageIR,
    line: LineIR,
    rule: MetricRule,
    entity: str,
    period_end: date,
    *,
    page_entity: float | None = None,
) -> tuple[TokenIR, Decimal, float, dict[str, Any]] | None:
    candidates: list[tuple[TokenIR, Decimal | None]] = []
    for token in line.numeric_tokens:
        value = _decimal(token.text)
        if value is not None or token.text == "-":
            candidates.append((token, value))
    if len(candidates) >= 3:
        first_token, first_value = candidates[0]
        if (
            first_value is not None
            and first_value == first_value.to_integral()
            and abs(first_value) <= 99
            and first_token.bbox.x0 < candidates[1][0].bbox.x0 - 15
        ):
            candidates = candidates[1:]
    if not candidates:
        return None

    expected_points = _header_points(page, line, rf"{entity}")
    other_points = _header_points(page, line, r"GROUP|COMPANY|BANK")
    other_points = [point for point in other_points if point not in expected_points]
    if not _is_dual_entity(page):
        # A standalone statement title such as "... - Company" describes the
        # whole page; its x-position is not a numeric-column header.
        expected_points = []
        other_points = []
    target_year_points = _header_points(page, line, str(period_end.year))
    target_date_pattern = (
        rf"(?:{period_end.day:02d}[./-]{period_end.month:02d}[./-]{period_end.year}|"
        rf"{period_end.day}[./-]{period_end.month}[./-]{period_end.year})"
    )
    target_date_points = _header_points(page, line, target_date_pattern)
    quarter_points = _header_points(page, line, r"QUARTER|\b[1-4]\s*Q\b")
    quarter_points.extend(_line_points(page, line, "three months"))
    change_points = _header_points(page, line, r"%|CHANGE|VARIANCE")
    ytd_points: list[float] = []
    for phrase in ("six months", "nine months", "twelve months", "year to date"):
        ytd_points.extend(_line_points(page, line, phrase))
    duration_regions = _duration_parent_regions(page, line)

    scored: list[tuple[float, TokenIR, Decimal | None, dict[str, float]]] = []
    page_scope = page_entity if page_entity is not None else _page_entity_confidence(page, entity)
    cluster_centers = cluster_numeric_columns(page, min_y=max(0.0, line.bbox.y0 - 80))
    for index, (token, value) in enumerate(candidates):
        x = token.bbox.center_x
        entity_near = _closeness(x, expected_points, page.width)
        other_near = _closeness(x, other_points, page.width)
        if len(expected_points) == 1 and len(other_points) == 1:
            boundary = (expected_points[0] + other_points[0]) / 2
            expected_is_left = expected_points[0] < other_points[0]
            inside_expected_region = x < boundary if expected_is_left else x > boundary
            entity_component = 1.0 if inside_expected_region else 0.0
        elif expected_points:
            entity_component = max(0.0, min(1.0, 0.55 + 0.55 * entity_near - 0.45 * other_near))
        else:
            entity_component = page_scope
        date_component = max(
            _closeness(x, target_date_points, page.width),
            _closeness(x, target_year_points, page.width),
        )
        if not target_date_points and not target_year_points:
            date_component = 0.65
        quarter_component = (
            _closeness(x, quarter_points, page.width) if rule.statement == "FLOW" else 0.8
        )
        if rule.statement == "FLOW" and not quarter_points:
            quarter_component = 0.72 if _is_exact_quarter_text(page.text) else 0.0
        change_penalty = _closeness(x, change_points, page.width, 0.055)
        left_bias = max(0.0, 1.0 - index / max(len(candidates), 1))
        cluster_component = _closeness(x, list(cluster_centers), page.width)
        prior_year_points = _header_points(page, line, str(period_end.year - 1))
        parent = _parent_kind_at(x, duration_regions)
        if (
            rule.statement == "FLOW"
            and target_year_points
            and prior_year_points
            and _closeness(x, prior_year_points, page.width)
            > _closeness(x, target_year_points, page.width)
        ):
            continue
        if rule.statement == "FLOW" and parent is not None:
            if parent.kind == "YTD":
                continue
            quarter_component = 1.0
        elif (
            rule.statement == "FLOW"
            and quarter_points
            and ytd_points
            and _closeness(x, ytd_points, page.width) > _closeness(x, quarter_points, page.width)
        ):
            continue
        score = (
            entity_component * 0.36
            + date_component * 0.24
            + quarter_component * 0.24
            + left_bias * 0.08
            + cluster_component * 0.08
            - change_penalty * 0.18
        )
        scored.append(
            (
                score,
                token,
                value,
                {
                    "entity": entity_component,
                    "date": date_component,
                    "quarter": quarter_component,
                    "cluster": cluster_component,
                    "change_penalty": change_penalty,
                    "parent_span": 1.0 if parent is not None and parent.kind == "QUARTER" else 0.0,
                },
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return None
    score, token, value, components = scored[0]
    if value is None or components["change_penalty"] >= 0.6:
        return None
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    margin = max(0.0, score - runner_up)
    column_confidence = min(1.0, score * 0.75 + margin * 1.5)
    governing = _parent_kind_at(token.bbox.center_x, duration_regions)
    graph = build_value_graph(
        label=_metric_label(line),
        value_token=token,
        entity=entity,
        period_end=period_end.isoformat(),
        line=line,
        column_scores=[
            {
                "raw": candidate_token.text,
                "x": candidate_token.bbox.center_x,
                "score": round(candidate_score, 4),
            }
            for candidate_score, candidate_token, _candidate_value, _components in scored
        ],
        cluster_centers=cluster_centers,
        components=components,
        selected_score=score,
        runner_up_score=runner_up,
        parent_header=(
            {
                "phrase": governing.phrase,
                "kind": governing.kind,
                "x0": governing.x0,
                "x1": governing.x1,
            }
            if governing is not None
            else None
        ),
    )
    return token, value, column_confidence, graph


def _unit_for_layout(
    document: DocumentIR, page: PageIR, line: LineIR, metric_type: str
) -> tuple[str | None, int | None, str | None, float]:
    if metric_type == "MONETARY_PER_SHARE":
        row_candidates = detect_candidates(line.text, scope=UnitScope.ROW, page=page.number)
        currency = row_candidates[0].currency if row_candidates else "LKR"
        source = row_candidates[0].source_text if row_candidates else "Per-share amount"
        return currency, 1, source, 0.98 if row_candidates else 0.85

    collected: list[UnitCandidate] = []
    ranked: list[tuple[float, str, int, str]] = []
    for candidate_page in document.pages:
        page_gap = abs(candidate_page.number - page.number)
        for candidate_line in candidate_page.lines:
            if not _unit_declaration(candidate_line.text):
                continue
            if "per share" in candidate_line.text.lower():
                continue
            units = detect_candidates(
                candidate_line.text,
                scope=(
                    UnitScope.STATEMENT
                    if candidate_page.number == page.number
                    else UnitScope.REPORT
                ),
                page=candidate_page.number,
                distance=(
                    abs(candidate_line.bbox.center_y - line.bbox.center_y) / max(page.height, 1)
                    if candidate_page.number == page.number
                    else 2.0 + page_gap
                ),
            )
            collected.extend(units)
            for unit in units:
                specificity = 0.15 if unit.scale_factor > 1 else 0.0
                same_page = 0.7 if candidate_page.number == page.number else 0.25
                distance_score = max(0.0, 0.25 - unit.distance * 0.15)
                ranked.append(
                    (
                        same_page + distance_score + specificity,
                        unit.currency,
                        unit.scale_factor,
                        candidate_line.text.strip(),
                    )
                )
    if collected:
        try:
            winner = resolve_unit(collected)
            return winner.currency, winner.scale_factor, winner.source_text, 0.92
        except Exception:
            pass
    if not ranked:
        return None, None, None, 0.0
    ranked.sort(key=lambda item: item[0], reverse=True)
    score, currency, scale, source = ranked[0]
    return currency, scale, source, min(0.99, 0.62 + score * 0.32)


def _certainty_band(score: float) -> str:
    if score >= 0.9:
        return "HIGH"
    if score >= 0.75:
        return "MEDIUM"
    if score > 0:
        return "LOW"
    return "NONE"


def _missing_fact(
    issuer_name: str,
    symbol: str,
    period_end: date,
    rule: MetricRule,
    entity: str,
    status: str,
    *,
    page_number: int | None = None,
    source_line: str | None = None,
) -> ExtractedFact:
    return ExtractedFact(
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=period_end,
        metric_code=rule.code,
        metric_type=rule.metric_type,
        raw_text=None,
        raw_value=None,
        normalized_value=None,
        currency=None,
        scale_factor=None,
        entity_scope=entity,
        source_page=page_number,
        source_line=source_line,
        unit_source_text=None,
        confidence="NONE",
        status=status,
        duration_months=3 if rule.statement == "FLOW" else None,
        validation_status="FAILED",
        review_status="REVIEW",
    )


def _is_excluded_pat_line(text: str) -> bool:
    """Skip NCI/group attribution lines; keep standalone company/bank PAT."""

    return bool(NCI_OR_GROUP_PAT_RE.search(text))


def entity_scope_for_issuer(
    issuer_name: str, issuers: dict[str, IssuerProfile] | None = None
) -> str:
    return infer_entity_scope(issuer_name, issuers)


def _bare_eps_label(label: str) -> bool:
    normalized = re.sub(r"\s+", " ", label.lower()).strip(" :-–")
    return bool(re.fullmatch(r"[-–]?\s*(?:basic|diluted)", normalized))


def _layout_candidates(
    document: DocumentIR,
    rule: MetricRule,
    entity: str,
    period_end: date,
    *,
    require_exact_quarter: bool = True,
    statement_map: dict[int, str | None] | None = None,
) -> tuple[list[_LayoutCandidate], bool, bool]:
    candidates: list[_LayoutCandidate] = []
    found_outside_quarter = False
    found_wrong_scope = False
    mapping = statement_map if statement_map is not None else _page_statement_map(document)
    last_entity_by_statement: dict[str, float] = {}
    document_quarter_context = any(
        _is_exact_quarter_text(page.text)
        or re.search(
            r"\b(?:FIRST|SECOND|THIRD|FOURTH)\s+QUARTER\b|\b[1-4]Q\b|\bQ[1-4]\b",
            page.text,
            re.I,
        )
        for page in document.pages
    )
    for page in document.pages:
        inherited_statement = mapping.get(page.number)
        inherited_entity = (
            last_entity_by_statement.get(inherited_statement) if inherited_statement else None
        )
        page_entity = _page_entity_confidence(page, entity, inherited=inherited_entity)
        if inherited_statement:
            last_entity_by_statement[inherited_statement] = page_entity
        exact_quarter = _is_exact_quarter_text(page.text) or bool(
            document_quarter_context
            and (
                inherited_statement == "FLOW"
                or rule.code in {"EPS_BASIC", "EPS_DILUTED", "NAVPS"}
                or re.search(r"\bFOR\s+THE\s+PERIOD\s+ENDED\b", page.text, re.I)
            )
        )
        primary_statement = _is_statement_page(page, rule.statement)
        expected_statement = primary_statement or inherited_statement == rule.statement
        if rule.code in {"EPS_BASIC", "EPS_DILUTED"} and _page_has_eps(page):
            expected_statement = True
        if rule.code == "NAVPS" and _page_has_navps(page):
            expected_statement = True
        for line in page.lines:
            if rule.code == "PAT" and _is_excluded_pat_line(line.text):
                continue
            if rule.code in {"TOTAL_EQUITY", "TOTAL_LIABILITIES"} and re.search(
                r"\bequity\s+(?:and|&)\s+liabilities\b|\bliabilities\s+(?:and|&)\s+equity\b",
                line.text,
                re.I,
            ):
                continue
            semantic_score, semantic_model, raw_label = _metric_confidence(line, rule)
            if semantic_score < 0.84:
                continue
            if rule.code.startswith("TOTAL_") and not semantic_model.startswith("regex"):
                continue
            if rule.code == "OPERATING_PROFIT":
                if re.search(r"\bebitda\b", raw_label, re.I):
                    continue
                if not re.search(
                    r"\boperat(?:e|ing|ions?)\w*\b|\bebit\b|earnings\s+before\s+interest",
                    raw_label,
                    re.I,
                ):
                    continue
            if rule.code in {"EPS_BASIC", "EPS_DILUTED"}:
                lowered_label = raw_label.lower()
                if rule.code == "EPS_DILUTED" and "diluted" not in lowered_label:
                    continue
                if (
                    rule.code == "EPS_BASIC"
                    and re.search(r"\bdiluted\b", lowered_label)
                    and not re.search(r"\bbasic\b", lowered_label)
                ):
                    continue
                if _bare_eps_label(raw_label):
                    nearby = _nearby_text(page, line).lower()
                    if not re.search(
                        r"earnings?\s*/?\s*\(?\s*loss\s*\)?\s+per\s+(?:ordinary\s+)?share|"
                        r"loss\s+per\s+(?:ordinary\s+)?share|\beps\b",
                        nearby,
                    ):
                        continue
            if rule.code == "NAVPS" and not semantic_model.startswith("regex"):
                continue
            if rule.code == "NAVPS" and (
                len(raw_label.split()) > 12
                or re.search(r"\b(?:calculated|based)\b", raw_label, re.I)
            ):
                continue
            if not expected_statement:
                continue
            if rule.statement == "FLOW" and require_exact_quarter and not exact_quarter:
                found_outside_quarter = True
                continue
            if rule.statement == "FLOW" and not require_exact_quarter and exact_quarter:
                continue
            if page_entity == 0:
                found_wrong_scope = True
                continue
            selected = _select_layout_value(
                page, line, rule, entity, period_end, page_entity=page_entity
            )
            if selected is None:
                continue
            token, raw_value, column_confidence, graph = selected
            period_confidence = 0.98 if rule.statement == "FLOW" else 0.94
            statement_bonus = 0.15 if primary_statement else 0.0
            exact_label_bonus = 0.08 if semantic_model.startswith("regex") else 0.0
            top_line_bonus = 0.0
            if rule.code == "TOP_LINE":
                lowered_label = raw_label.lower()
                if (entity == "BANK" and lowered_label.startswith("gross income")) or (
                    entity != "BANK" and re.match(r"^(?:net\s+)?revenue\b", lowered_label)
                ):
                    top_line_bonus = 0.08
            score = (
                semantic_score * 0.30
                + page_entity * 0.26
                + period_confidence * 0.20
                + column_confidence * 0.24
                + statement_bonus
                + exact_label_bonus
                + top_line_bonus
            )
            candidates.append(
                _LayoutCandidate(
                    rule=rule,
                    page=page,
                    line=line,
                    token=token,
                    raw_value=raw_value,
                    raw_label=raw_label,
                    semantic_model=semantic_model,
                    semantic_confidence=semantic_score,
                    entity_confidence=page_entity,
                    period_confidence=period_confidence,
                    column_confidence=column_confidence,
                    candidate_score=score,
                    graph=graph,
                )
            )
    return candidates, found_outside_quarter, found_wrong_scope


def _usable_eps(fact: ExtractedFact | None) -> bool:
    return (
        fact is not None
        and fact.status in {"EXTRACTED", "LOW_CERTAINTY"}
        and fact.normalized_value is not None
    )


def _selected_eps_fact(
    issuer_name: str,
    symbol: str,
    period_end: date,
    entity: str,
    *,
    diluted: ExtractedFact | None,
    basic: ExtractedFact | None,
) -> ExtractedFact:
    """Prefer extracted diluted EPS; otherwise extracted basic. Never copy a miss."""

    selected = diluted if _usable_eps(diluted) else basic if _usable_eps(basic) else None
    if selected is not None:
        return replace(
            selected,
            metric_code="EPS_SELECTED",
            unit_source_text=(
                "Diluted EPS selected"
                if selected.metric_code == "EPS_DILUTED"
                else "Basic EPS selected"
            ),
            evidence_json=json.dumps(
                {
                    "selection": selected.metric_code,
                    "source": selected.evidence_json,
                },
                separators=(",", ":"),
            ),
        )
    statuses = [fact.status for fact in (diluted, basic) if fact is not None]
    preferred = (
        "CONSOLIDATED_ONLY",
        "EXACT_QUARTER_NOT_REPORTED",
        "CUMULATIVE_ONLY",
        "SOURCE_CONFIRMED_NOT_REPORTED",
        "NOT_FOUND_BY_PARSER",
        "UNIT_NOT_RESOLVED",
    )
    missing_status = next((status for status in preferred if status in statuses), None)
    if missing_status is None:
        missing_status = next(
            (status for status in statuses if status not in {"NOT_REPORTED", "EXTRACTED"}),
            "NOT_FOUND_BY_PARSER",
        )
    selected_rule = MetricRule("EPS_SELECTED", (), "FLOW", "MONETARY_PER_SHARE")
    return _missing_fact(
        issuer_name,
        symbol,
        period_end,
        selected_rule,
        entity,
        missing_status,
    )


def _cross_metric_inconsistency(facts: list[ExtractedFact]) -> str | None:
    """Flag flow metrics that did not resolve through the same current 3M standalone path."""

    context_codes = {"TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT", "EPS_BASIC", "EPS_DILUTED"}
    extracted = [
        fact
        for fact in facts
        if fact.metric_code in context_codes and fact.status in {"EXTRACTED", "LOW_CERTAINTY"}
    ]
    if len(extracted) < 2:
        return None
    scopes = {fact.entity_scope for fact in extracted}
    durations = {fact.duration_months for fact in extracted}
    roles = {fact.comparison_role for fact in extracted}
    if len(scopes) > 1 or len(durations) > 1 or len(roles) > 1:
        return (
            "Flow metrics resolved through inconsistent entity, duration, or comparison paths: "
            f"scopes={sorted(scopes)} durations={sorted(str(item) for item in durations)} "
            f"roles={sorted(roles)}."
        )
    confidences = [fact.entity_confidence for fact in extracted]
    pages = {fact.source_page for fact in extracted}
    if len(pages) > 1 and max(confidences) - min(confidences) >= 0.3:
        return "Flow metrics resolved through inconsistent header/period paths."
    return None


def _write_diagnostics(
    diagnostics_dir: Path,
    document: DocumentIR,
    facts: list[ExtractedFact],
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "document_quality.json").write_text(
        json.dumps(document.evidence_dict(), indent=2),
        encoding="utf-8",
    )
    review = [fact for fact in facts if fact.status not in {"EXTRACTED", "EXTRACTED_DERIVED"}]
    if not review:
        return
    payload = {
        "review_count": len(review),
        "facts": [
            {
                "metric_code": fact.metric_code,
                "status": fact.status,
                "page": fact.source_page,
                "line": fact.source_line,
                "evidence": json.loads(fact.evidence_json) if fact.evidence_json else None,
            }
            for fact in review
        ],
    }
    (diagnostics_dir / "diagnostics.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def _text_fallback_metric(
    pdf_path: Path,
    rule: MetricRule,
    entity: str,
    text_cache_dir: Path | None,
) -> tuple[PdfPage, str, Decimal, str, str | None, int | None, str | None] | None:
    """Last-resort Poppler/pypdf text path when coordinate IR found no candidate."""

    try:
        pages = extract_layout_pages(pdf_path, text_cache_dir)
    except Exception:
        return None
    ranked: list[tuple[int, PdfPage, tuple[str, Decimal | None, str]]] = []
    for page in pages:
        score = _statement_score(page, rule.statement, entity)
        if score < 10:
            continue
        found = _find_metric(page, rule)
        if found is None or found[1] is None:
            continue
        ranked.append((score, page, found))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    _score, page, found = ranked[0]
    raw, value, line = found
    if value is None:
        return None
    currency, scale, unit_text = _statement_unit(page)
    return page, raw, value, line, currency, scale, unit_text


def extract_filing(
    pdf_path: Path,
    issuer_name: str,
    symbol: str,
    period_end: date,
    text_cache_dir: Path | None = None,
    *,
    ocr_enabled: bool = True,
    issuers: dict[str, IssuerProfile] | None = None,
    diagnostics_dir: Path | None = None,
    auto_approve_threshold: float = 0.95,
    manual_review_threshold: float = 0.80,
) -> list[ExtractedFact]:
    document = extract_document_ir(
        pdf_path,
        ocr_dir=text_cache_dir,
        enable_ocr=ocr_enabled,
    )
    entity = entity_scope_for_issuer(issuer_name, issuers)
    facts: list[ExtractedFact] = []
    statement_map = _page_statement_map(document)

    for rule in METRIC_RULES:
        candidates, outside_quarter, wrong_scope = _layout_candidates(
            document, rule, entity, period_end, statement_map=statement_map
        )
        cumulative_only = False
        if not candidates and rule.code in {"TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT"}:
            cumulative_candidates, _outside, cumulative_wrong_scope = _layout_candidates(
                document,
                rule,
                entity,
                period_end,
                require_exact_quarter=False,
                statement_map=statement_map,
            )
            cumulative_candidates = [
                candidate
                for candidate in cumulative_candidates
                if (_duration_months(candidate.page.text) or 0) > 3
            ]
            if cumulative_candidates:
                candidates = cumulative_candidates
                cumulative_only = True
            wrong_scope = wrong_scope or cumulative_wrong_scope
        if not candidates and rule.code in {"EPS_BASIC", "EPS_DILUTED", "NAVPS"}:
            retry, retry_outside, retry_wrong_scope = _layout_candidates(
                document,
                rule,
                entity,
                period_end,
                require_exact_quarter=False,
                statement_map=statement_map,
            )
            if retry:
                candidates = retry
            outside_quarter = outside_quarter or retry_outside
            wrong_scope = wrong_scope or retry_wrong_scope
        if not candidates:
            fallback = _text_fallback_metric(pdf_path, rule, entity, text_cache_dir)
            if fallback is not None:
                page, raw, value, line, currency, scale, unit_text = fallback
                if rule.metric_type == "MONETARY_PER_SHARE":
                    normalized = value
                    status = "EXTRACTED"
                    unit_confidence = 0.86
                elif currency is None or scale is None:
                    normalized = None
                    status = "UNIT_NOT_RESOLVED"
                    unit_confidence = 0.0
                else:
                    unit = UnitCandidate(
                        unit_text or "", currency, scale, UnitScope.STATEMENT, page=page.number
                    )
                    normalized = normalize_value(
                        value, MetricType.MONETARY_ABSOLUTE, [unit]
                    ).normalized_value
                    status = "EXTRACTED"
                    unit_confidence = 0.8
                overall = 0.72
                if status == "EXTRACTED" and overall < manual_review_threshold:
                    status = "LOW_CERTAINTY"
                facts.append(
                    ExtractedFact(
                        issuer_name=issuer_name,
                        symbol=symbol,
                        period_end=period_end,
                        metric_code=rule.code,
                        metric_type=rule.metric_type,
                        raw_text=raw,
                        raw_value=value,
                        normalized_value=normalized,
                        currency=currency,
                        scale_factor=1 if rule.metric_type == "MONETARY_PER_SHARE" else scale,
                        entity_scope=entity,
                        source_page=page.number,
                        source_line=line,
                        unit_source_text=unit_text,
                        confidence=_certainty_band(overall),
                        status=status,
                        raw_label=line,
                        extraction_method="TEXT_FALLBACK",
                        semantic_model="regex+rapidfuzz",
                        semantic_confidence=0.9,
                        entity_confidence=0.8,
                        period_confidence=0.8,
                        unit_confidence=unit_confidence,
                        column_confidence=0.7,
                        validation_confidence=0.8,
                        overall_certainty=overall,
                        certainty_band=_certainty_band(overall),
                        duration_months=3 if rule.statement == "FLOW" else None,
                        validation_status="PASSED" if status == "EXTRACTED" else "REVIEW",
                        review_status="REVIEW",
                    )
                )
                continue
            status = (
                "EXACT_QUARTER_NOT_REPORTED"
                if outside_quarter
                else "CONSOLIDATED_ONLY"
                if wrong_scope
                else "SOURCE_CONFIRMED_NOT_REPORTED"
                if any(value == rule.statement for value in statement_map.values())
                else "NOT_FOUND_BY_PARSER"
            )
            facts.append(_missing_fact(issuer_name, symbol, period_end, rule, entity, status))
            continue

        candidates.sort(
            key=lambda candidate: (candidate.candidate_score, -candidate.page.number), reverse=True
        )
        selected = candidates[0]
        currency, scale, unit_text, unit_confidence = _unit_for_layout(
            document, selected.page, selected.line, rule.metric_type
        )
        if rule.metric_type == "MONETARY_PER_SHARE":
            normalized = selected.raw_value
            status = "CUMULATIVE_ONLY" if cumulative_only else "EXTRACTED"
        elif currency is None or scale is None:
            normalized = None
            status = "UNIT_NOT_RESOLVED"
        else:
            unit = UnitCandidate(
                unit_text or "",
                currency,
                scale,
                UnitScope.STATEMENT,
                page=selected.page.number,
            )
            normalized = normalize_value(
                selected.raw_value, MetricType.MONETARY_ABSOLUTE, [unit]
            ).normalized_value
            status = "CUMULATIVE_ONLY" if cumulative_only else "EXTRACTED"

        validation_confidence = 0.9
        overall = (
            selected.semantic_confidence * 0.20
            + selected.entity_confidence * 0.20
            + selected.period_confidence * 0.18
            + selected.column_confidence * 0.20
            + unit_confidence * 0.12
            + validation_confidence * 0.10
        )
        if status == "EXTRACTED" and overall < manual_review_threshold:
            status = "LOW_CERTAINTY"
        if "OCR" in document.quality.extraction_method.upper() and status == "EXTRACTED":
            overall = min(overall * 0.88, auto_approve_threshold - 0.02)
            if overall < manual_review_threshold:
                status = "LOW_CERTAINTY"
        review_status = (
            "APPROVED"
            if status in {"EXTRACTED", "EXTRACTED_DERIVED"} and overall >= auto_approve_threshold
            else "REVIEW"
        )
        band = _certainty_band(overall)
        stored_graph = (
            summarize_graph(selected.graph)
            if status == "EXTRACTED" and review_status == "APPROVED"
            else selected.graph
        )
        evidence = {
            "selected_line": compact_line(selected.line),
            "graph": stored_graph,
            "source_header_year": period_end.year,
            "comparison_role": "CURRENT",
            "duration_months": (
                _duration_months(selected.page.text)
                if cumulative_only
                else 3
                if rule.statement == "FLOW"
                else None
            ),
            "candidate_count": len(candidates),
            "candidate_scores": [
                {
                    "page": candidate.page.number,
                    "label": candidate.raw_label,
                    "raw_value": str(candidate.raw_value),
                    "score": round(candidate.candidate_score, 4),
                    "selected": candidate is selected,
                }
                for candidate in candidates[:8]
            ],
            "rejected_raw_values": [
                str(candidate.raw_value)
                for candidate in candidates
                if candidate is not selected
            ][:12],
            "column_raw_values": [
                str(row.get("raw"))
                for row in selected.graph.get("column_scores", [])
                if row.get("raw")
            ],
            "unit": {
                "currency": currency,
                "scale_factor": scale,
                "source_text": unit_text,
                "confidence": round(unit_confidence, 4),
            },
        }
        facts.append(
            ExtractedFact(
                issuer_name=issuer_name,
                symbol=symbol,
                period_end=period_end,
                metric_code=rule.code,
                metric_type=rule.metric_type,
                raw_text=selected.token.text,
                raw_value=selected.raw_value,
                normalized_value=normalized,
                currency=currency,
                scale_factor=scale,
                entity_scope=entity,
                source_page=selected.page.number,
                source_line=selected.line.text,
                unit_source_text=unit_text,
                confidence=(
                    band if status in {"EXTRACTED", "LOW_CERTAINTY", "CUMULATIVE_ONLY"} else "LOW"
                ),
                status=status,
                raw_label=selected.raw_label,
                source_bbox=_bbox_json(selected.token.bbox),
                extraction_method=document.quality.extraction_method,
                semantic_model=selected.semantic_model,
                semantic_confidence=round(selected.semantic_confidence, 4),
                entity_confidence=round(selected.entity_confidence, 4),
                period_confidence=round(selected.period_confidence, 4),
                unit_confidence=round(unit_confidence, 4),
                column_confidence=round(selected.column_confidence, 4),
                validation_confidence=validation_confidence,
                overall_certainty=round(overall, 4),
                certainty_band=band,
                duration_months=(
                    _duration_months(selected.page.text)
                    if cumulative_only
                    else 3
                    if rule.statement == "FLOW"
                    else None
                ),
                validation_status="PASSED" if status == "EXTRACTED" else "REVIEW",
                review_status=review_status,
                evidence_json=json.dumps(evidence, separators=(",", ":")),
            )
        )

    fact_map = facts_by_code(facts)
    # Total Liabilities remains source-backed. Assets - Equity is validation only.

    diluted = fact_map.get("EPS_DILUTED")
    basic = fact_map.get("EPS_BASIC")
    facts.append(
        _selected_eps_fact(
            issuer_name,
            symbol,
            period_end,
            entity,
            diluted=diluted,
            basic=basic,
        )
    )
    flagged = _cross_metric_inconsistency(facts)
    if flagged is not None:
        facts.append(
            _missing_fact(
                issuer_name,
                symbol,
                period_end,
                MetricRule("CROSS_METRIC_CONTEXT", (), "FLOW", "RATIO"),
                entity,
                "CROSS_METRIC_CONTEXT_INCONSISTENT",
                source_line=flagged,
            )
        )
    if diagnostics_dir is not None:
        _write_diagnostics(diagnostics_dir, document, facts)
    return facts


def extract_quarter_prices(
    pdf_path: Path,
    issuer_name: str,
    symbols: Iterable[str],
    period_end: date,
    text_cache_dir: Path | None = None,
) -> list[QuarterPrice]:
    document = extract_document_ir(pdf_path, ocr_dir=text_cache_dir)
    generic: list[tuple[float, PageIR, LineIR, Decimal, TokenIR]] = []
    class_values: dict[str, tuple[PageIR, LineIR, Decimal, TokenIR]] = {}
    price_section_terms = (
        "market price",
        "share price",
        "market price per share",
        "price per share",
        "market value of shares",
    )
    for page in document.pages:
        lines = list(page.lines)
        for index, line in enumerate(lines):
            context = " ".join(item.text for item in lines[max(0, index - 12) : index + 3]).lower()
            local_context = " ".join(
                item.text for item in lines[max(0, index - 3) : index + 1]
            ).lower()
            lowered = line.text.lower()
            section_present = any(term in context for term in price_section_terms)
            price_label = bool(
                re.search(r"\blast\s+traded(?:\s+(?:market\s+)?price)?\b", lowered)
                or re.search(r"\bclosing\s+(?:share\s+)?price\b", lowered)
                or re.search(r"\bmarket\s+price\s+as\s+at\b", lowered)
                or (section_present and re.match(r"^\s*closing\b", lowered))
                or (section_present and re.match(r"^\s*share\s+price\b", lowered))
                or (
                    section_present
                    and re.match(r"^\s*(?:period|quarter|year)\s+end(?:ed)?\b", lowered)
                )
            )
            if not price_label and not (
                re.match(r"^\s*(?:non[- ]?voting|voting)\b", lowered)
                and any(term in local_context for term in ("price per share", "last traded"))
            ):
                continue
            numeric: list[tuple[TokenIR, Decimal]] = []
            for token in line.numeric_tokens:
                value = _decimal(token.text)
                if value is not None:
                    numeric.append((token, value))
            if not numeric:
                continue
            if (
                re.match(r"^\s*(?:period|quarter|year)\s+end(?:ed)?\b", lowered)
                and "voting" in context
                and "non-voting" in context
            ):
                class_values.setdefault("N", (page, line, numeric[0][1], numeric[0][0]))
                if len(numeric) >= 2:
                    class_values.setdefault("X", (page, line, numeric[1][1], numeric[1][0]))
                continue
            token, value = numeric[0]
            if re.match(r"^\s*non[- ]?voting\b", lowered):
                class_values.setdefault("X", (page, line, value, token))
            elif re.match(r"^\s*voting\b", lowered):
                class_values.setdefault("N", (page, line, value, token))
            else:
                score = 0.78
                if "last traded" in lowered:
                    score += 0.15
                if period_end.isoformat() in context or str(period_end.year) in context:
                    score += 0.05
                generic.append((min(score, 0.99), page, line, value, token))

    best_generic = max(generic, key=lambda item: (item[0], -item[1].number), default=None)
    result: list[QuarterPrice] = []
    for symbol in symbols:
        security_class = "X" if ".X" in symbol.upper() else "N"
        class_match = class_values.get(security_class)
        if class_match:
            page, line, value, token = class_match
            result.append(
                QuarterPrice(
                    issuer_name,
                    symbol,
                    period_end,
                    value,
                    page.number,
                    line.text,
                    "FILING_LAYOUT",
                    "HIGH",
                    "EXTRACTED",
                    0.97,
                    "HIGH",
                    _bbox_json(token.bbox),
                    "PASSED",
                )
            )
        elif best_generic:
            score, page, line, value, token = best_generic
            result.append(
                QuarterPrice(
                    issuer_name,
                    symbol,
                    period_end,
                    value,
                    page.number,
                    line.text,
                    "FILING_LAYOUT",
                    _certainty_band(score),
                    "EXTRACTED",
                    round(score, 4),
                    _certainty_band(score),
                    _bbox_json(token.bbox),
                    "PASSED",
                )
            )
        else:
            result.append(
                QuarterPrice(
                    issuer_name,
                    symbol,
                    period_end,
                    None,
                    None,
                    None,
                    "FILING_AND_PUBLIC_HISTORY_NOT_FOUND",
                    "NONE",
                    "HISTORICAL_PRICE_NOT_AVAILABLE",
                )
            )
    return result


def facts_by_code(facts: Iterable[ExtractedFact]) -> dict[str, ExtractedFact]:
    return {fact.metric_code: fact for fact in facts}
