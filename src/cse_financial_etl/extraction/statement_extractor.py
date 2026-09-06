from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from itertools import pairwise
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
from cse_financial_etl.extraction.unit_detector import (
    compose_unit_text,
    detect_candidates,
    resolve_unit,
)
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
            r"^\s*income\b(?!\s+tax)(?!\s+and)(?!\s+from)",
            r"^\s*net\s+operating\s+income\b",
            r"^\s*insurance\s+revenue\b",
            r"^\s*gross\s+written\s+premium\b",
            r"^\s*net\s+earned\s+premiums?\b",
            r"^\s*turnover\b",
            r"^\s*interest\s+income\b",
            r"^\s*net\s+interest\s+income\b",
            r"^\s*net\s+operating\s+(?:expense|income)\b",
        ),
        "FLOW",
        "MONETARY_ABSOLUTE",
    ),
    MetricRule(
        "OPERATING_PROFIT",
        _patterns(
            r"^\s*results?\s+(?:from|of)\s+operating\s+activities\b",
            r"^\s*profit\s*/\s*\(?loss\)?\s+from\s+operations?\b",
            r"^\s*operating\s+profit\s*/\s*\(?\s*loss\s*\)?",
            r"^\s*operating\s+profit\s+before\s+tax(?:es|ation)?\s+on\s+financial\s+services\b",
            r"^\s*operating\s+profit\b(?!\s+before\s+working\s+capital)",
            r"^\s*profit\s*/?\s*\(?\s*loss\s*\)?\s*from\s+operat(?:ion|ions|ing\s+activities)\b",
            r"^\s*profit\s+from\s+operat(?:ion|ions|ing\s+activities)\b",
            r"^\s*results?\s+from\s+operations?\b",
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
            r"^\s*earnings?\s+share\b",
            r"^\s*loss\s+per\s+share\s+for\s+the\s+period\b",
            r"^\s*basic\s+eps\b",
            r"^\s*eps\s*\(\s*basic",
            r"^\s*[-–]\s*basic\b",
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
            r"^\s*total\s+liabilit(?:y|ies)\b(?!\s+(?:and|&)\s+(?:equity|shareholders|funds))",
            r"^\s*liabilities\s+total\b",
            r"^\s*total\s+liability\b(?!\s+(?:and|&))",
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
    # Pack titles like "Second Quarter Interim Financial Statements" often wrap a
    # six/nine-month P&L. Prefer explicit cumulative duration over bare QUARTER.
    if re.search(
        r"\b(?:SIX|0?6|NINE|0?9|TWELVE|12)\s+MONTHS?\b|\bYEAR\s+ENDED\b",
        normalized,
    ) and not re.search(
        r"\b(?:THREE|03)\s+MONTHS?\b|\b3\s+MONTHS?\b|\bQUARTER\s+(?:ENDED|TO)\b|"
        r"\bFOR\s+THE\s+(?:THREE|03|3)\s+MONTHS?\b",
        normalized,
    ):
        return False
    patterns = (
        r"\bQUARTER\s+(?:ENDED|TO)\b",
        r"\b(?:THREE|03)\s+MONTHS?\s+(?:ENDED|TO)\b",
        r"\b3\s+MONTHS?\s+(?:ENDED|TO)\b",
        r"\bFOR\s+THE\s+(?:THREE|03|3)\s+MONTHS?\b",
        r"\b(?:THREE|03|3)[- ]MONTH\s+PERIOD\s+(?:ENDED|TO)\b",
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
    # separate visual lines. Combined Three+Nine pages still have a quarter block.
    has_split_three_months = bool(
        re.search(r"\bTHREE\b", normalized)
        and re.search(r"\bMONTHS?\s+(?:ENDED|TO)\b", normalized)
    )
    return has_split_three_months


def _is_exact_quarter_page(page: PdfPage) -> bool:
    return _is_exact_quarter_text(page.text)


def _duration_months(text: str) -> int | None:
    normalized = re.sub(r"\s+", " ", text.upper())
    # Prefer explicit N-month / quarter phrases over a bare Year Ended label.
    duration_patterns = (
        (9, r"\b(?:NINE|0?9)\s+MONTHS?\b"),
        (6, r"\b(?:SIX|0?6)\s+MONTHS?\b"),
        (3, r"\b(?:THREE|0?3)\s+MONTHS?\b|\bQUARTER\b"),
        (12, r"\b(?:TWELVE|12)\s+MONTHS?\b"),
    )
    for duration, pattern in duration_patterns:
        if re.search(pattern, normalized):
            return duration
    # Year Ended alone is annual; mixed Year Ended + Period Ended is unresolved here.
    if re.search(r"\bYEAR\s+ENDED\b", normalized) and not re.search(
        r"\bPERIOD\s+ENDED\b", normalized
    ):
        return 12
    return None


def _statement_score(page: PdfPage, statement: str, entity: str) -> int:
    header = _header_text(page).upper()
    score = 0
    if re.search(r"CASH FLOWS?|CHANGES IN EQUITY", header) and not re.search(
        r"PROFIT OR LOSS|INCOME STATEMENT|FINANCIAL POSITION|BALANCE SHEET",
        header,
    ):
        return 0
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
            r"(?:\s*(?:rs\.?|lkr|usd)\s*(?:['’]?\s*000s?|mn|mns|million|bn|billion)?\s*)+",
            stripped,
            re.I,
        )
        or re.search(
            r"\b(?:rs\.?|lkr|usd|sri\s+lank(?:a|an)\s+rupees?)\s*"
            r"(?:['’]?\s*0{3}s?|mn(?:s|['’]s)?|millions?|bn(?:s|['’]s)?|billions?)\b",
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

    if standalone and len(entity_order) >= 2:
        if len(values) >= len(entity_order) and len(values) % len(entity_order) == 0:
            group_size = len(values) // len(entity_order)
            group_index = entity_order.index(standalone)
            group = values[group_index * group_size : (group_index + 1) * group_size]
            return pick(group) if group else None
        return None
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


def _is_rejected_top_line_label(label: str) -> bool:
    """Reject OCI totals and non-revenue 'other/reserve' lines mistaken for top line."""

    return bool(
        re.search(r"\bcomprehensive\b", label, re.I)
        or re.search(
            r"^\s*other\s+(?:operating\s+)?income\b|^\s*revenue\s+reserves?\b|"
            r"^\s*other\s+comprehensive\b",
            label,
            re.I,
        )
    )


def _metric_confidence(line: LineIR, rule: MetricRule) -> tuple[float, str, str]:
    label = _metric_label(line) or line.text
    if rule.code == "TOP_LINE" and _is_rejected_top_line_label(label):
        return 0.0, "rejected", label
    if any(pattern.search(label) for pattern in rule.aliases):
        return 1.0, "regex+rapidfuzz", label
    semantic = get_semantic_matcher().match(label, rule.code)
    if rule.code == "TOP_LINE" and _is_rejected_top_line_label(label):
        return 0.0, "rejected", label
    return semantic.score, semantic.model, label


def _is_statement_page(page: PageIR, statement: str) -> bool:
    """Detect a real statement title anywhere on the page, not only the first lines."""

    joined = re.sub(r"\s+", " ", page.text.upper())
    patterns: tuple[str, ...]
    if statement == "FLOW":
        patterns = (
            r"STATEMENTS? OF PROFIT OR LOSS",
            r"STATEMENTS? OF PROFIT AND LOSS",
            r"STATEMENTS? OF COMPREHENSIVE INCOME",
            r"INCOME STATEMENT",
            r"STATEMENT OF INCOME",
        )
    else:
        patterns = (
            r"STATEMENTS? OF FINANCIAL POS",
            r"BALANCE SHEET",
        )
    return any(re.search(pattern, joined) for pattern in patterns)


def _page_head_text(page: PageIR) -> str:
    return re.sub(r"\s+", " ", " ".join(line.text for line in page.lines[:8]).upper())


def _is_interim_pack_title(text: str) -> bool:
    upper = text.upper()
    return bool(re.search(r"\bINTERIM\b", upper) and re.search(r"\bQUARTER\b", upper))


def _is_page_number_line(text: str) -> bool:
    return bool(re.match(r"^\s*Page\s+\d+\s*$", text, re.I))


def _joined_statement_head(page: PageIR, line_count: int = 12) -> str:
    return " ".join(
        line.text
        for line in page.lines[:line_count]
        if not _is_interim_pack_title(line.text) and not _is_page_number_line(line.text)
    ).upper()


def _head_has_split_three_months(page: PageIR, line_count: int = 12) -> bool:
    """True when 'Three' and 'months ended/to' are split across nearby header lines.

    Never treat a bare page index ('Page 3') as a three-month duration cue.
    Combined Three+Nine column headers still count as having a quarter block.
    """

    joined = _joined_statement_head(page, line_count)
    return bool(
        re.search(r"\bTHREE\b", joined)
        and re.search(r"\bMONTHS?\s+(?:ENDED|TO)\b", joined)
    )


def _head_duration_cue(page: PageIR) -> str | None:
    """Statement-heading duration. Explicit 6M/9M/12M beats a false quarter cue.

    ``PERIOD`` is ambiguous: Q1 packs use it for the three-month quarter, while
    Q2/Q3 packs use it for the cumulative page beside a Quarter Ended P&L.

    Mixed Year Ended + Period Ended pages return ``MIXED_YEAR_PERIOD`` so duration
    must come from explicit months or fiscal year-end/period-end date evidence.
    """

    saw_quarter = False
    saw_ytd = False
    saw_period = False
    saw_year_ended = False
    saw_period_ended_col = False
    saw_explicit_interim = False
    for line in page.lines[:12]:
        text = line.text.upper()
        if _is_interim_pack_title(text) or _is_page_number_line(text):
            continue
        # Combined CSE layouts put both cues on one line:
        # "Quarter ended Six months ended" / "Year Ended ... Period Ended".
        if re.search(r"\bYEAR\s+ENDED\b", text):
            saw_year_ended = True
            saw_ytd = True
        if re.search(r"(?:NINE|SIX|TWELVE|0?9|0?6|12)\s+MONTHS", text):
            saw_explicit_interim = True
            saw_ytd = True
        if re.search(
            r"FOR THE QUARTER|QUARTER\s+ENDED|(?:THREE|03)\s+MONTHS|\b3\s+MONTHS",
            text,
        ):
            saw_quarter = True
        if re.search(r"\bPERIOD\s+ENDED\b", text):
            saw_period_ended_col = True
            saw_period = True
        elif re.search(r"FOR THE PERIOD ENDED", text):
            saw_period = True
    if _head_has_split_three_months(page):
        saw_quarter = True
    # Mixed annual + period columns: never assume three months from labels alone.
    if saw_year_ended and saw_period_ended_col:
        if saw_quarter:
            return "QUARTER"
        if saw_explicit_interim:
            return "YTD"
        return "MIXED_YEAR_PERIOD"
    # Mixed 6M+quarter pages must remain eligible for exact-quarter selection.
    if saw_quarter:
        return "QUARTER"
    if saw_ytd:
        return "YTD"
    if saw_period:
        return "PERIOD"
    return None


def _page_has_statement_quarter_heading(page: PageIR) -> bool:
    if _head_has_split_three_months(page, 20):
        return True
    for line in page.lines[:20]:
        text = line.text.upper()
        if _is_interim_pack_title(text) or _is_page_number_line(text):
            continue
        if re.search(
            r"FOR THE QUARTER|QUARTER\s+ENDED|(?:THREE|03)\s+MONTHS|\b3\s+MONTHS",
            text,
        ):
            return True
    return False


def _page_is_cumulative_only(
    page: PageIR, *, document_has_quarter_heading: bool = False
) -> bool:
    if _page_has_statement_quarter_heading(page):
        return False
    cue = _head_duration_cue(page)
    if cue == "MIXED_YEAR_PERIOD":
        return _page_fiscal_period_duration(page) in {6, 9, 12}
    if cue == "YTD":
        return True
    return cue == "PERIOD" and document_has_quarter_heading


def _page_is_exact_quarter(page: PageIR, *, document_has_quarter_heading: bool = False) -> bool:
    if _page_is_cumulative_only(
        page, document_has_quarter_heading=document_has_quarter_heading
    ):
        return False
    cue = _head_duration_cue(page)
    if cue == "QUARTER" or _page_has_statement_quarter_heading(page):
        return True
    if cue == "MIXED_YEAR_PERIOD":
        return _page_fiscal_period_duration(page) == 3
    if cue == "PERIOD":
        # Bare Period Ended stays eligible for Q1 packs, but duration stays unresolved
        # until column/fiscal evidence establishes three months.
        return not document_has_quarter_heading
    return _is_exact_quarter_text(page.text)


def _document_has_quarter_flow_heading(document: DocumentIR) -> bool:
    return any(
        (
            _head_duration_cue(page) == "QUARTER"
            or (
                _head_duration_cue(page) == "MIXED_YEAR_PERIOD"
                and _page_fiscal_period_duration(page) == 3
            )
        )
        and (_classify_page_statement(page) == "FLOW" or _is_statement_page(page, "FLOW"))
        for page in document.pages
    )


def _fiscal_months_between(year_end: date, period_end: date) -> int | None:
    """Months from fiscal year-end to period-end; only 3/6/9/12 are accepted."""

    if period_end < year_end:
        return None
    months = (period_end.year - year_end.year) * 12 + (period_end.month - year_end.month)
    if period_end == year_end:
        return 12
    return months if months in {3, 6, 9, 12} else None


def _parse_header_date_token(text: str) -> date | None:
    match = _DATE_TOKEN.match(text.strip("()"))
    if not match:
        return None
    try:
        return date(int(match["y"]), int(match["m"]), int(match["d"]))
    except ValueError:
        return None


def _header_dates_by_kind(page: PageIR, line: LineIR) -> list[tuple[str, date, float]]:
    """Associate dd.mm.yyyy header dates with Year Ended / Period Ended labels."""

    label_points: list[tuple[str, float]] = []
    for header_line in page.lines:
        if header_line.bbox.y0 >= line.bbox.y0:
            break
        for phrase, kind in (("year ended", "YEAR"), ("period ended", "PERIOD")):
            for _x0, _x1, center in _phrase_occurrences(header_line, phrase):
                label_points.append((kind, center))
    if not label_points:
        return []
    dated: list[tuple[str, date, float]] = []
    for header_line in page.lines:
        if header_line.bbox.y0 >= line.bbox.y0:
            break
        for token in header_line.tokens:
            parsed = _parse_header_date_token(token.text)
            if parsed is None:
                continue
            kind, _ = min(label_points, key=lambda item: abs(item[1] - token.bbox.center_x))
            dated.append((kind, parsed, token.bbox.center_x))
    return dated


def _page_fiscal_period_duration(page: PageIR) -> int | None:
    """Infer duration from Year Ended + Period Ended date pairs on the page."""

    if not page.lines:
        return None
    anchor = page.lines[min(8, len(page.lines) - 1)]
    dated = _header_dates_by_kind(page, anchor)
    year_dates = [item[1] for item in dated if item[0] == "YEAR"]
    period_dates = [item[1] for item in dated if item[0] == "PERIOD"]
    if not year_dates or not period_dates:
        return None
    year_end = max(year_dates)
    durations = {
        months
        for period in period_dates
        if (months := _fiscal_months_between(year_end, period)) is not None
        and period != year_end
    }
    if len(durations) == 1:
        return next(iter(durations))
    return None


def _page_flow_duration(
    page: PageIR, *, document_has_quarter_heading: bool = False
) -> int | None:
    cue = _head_duration_cue(page)
    head = _page_head_text(page)
    head_duration = _duration_months(head)
    if head_duration is not None:
        # Explicit months always win over Year/Period label shortcuts.
        return head_duration
    if cue == "QUARTER":
        return 3
    if cue == "MIXED_YEAR_PERIOD":
        return _page_fiscal_period_duration(page)
    if cue == "YTD":
        body_duration = _duration_months(page.text)
        return body_duration if body_duration in {6, 9, 12} else None
    if cue == "PERIOD":
        if document_has_quarter_heading:
            body_duration = _duration_months(page.text)
            return body_duration if body_duration in {6, 9, 12} else None
        # Bare "Period ended" is unresolved without explicit or fiscal evidence.
        return _page_fiscal_period_duration(page)
    return _duration_months(page.text)


def _classify_page_statement(page: PageIR) -> str | None:
    head = _page_head_text(page)
    body = re.sub(r"\s+", " ", page.text.upper())
    if re.search(
        r"STATEMENT(?:S)? OF CASH FLOWS?|STATEMENT(?:S)? OF CHANGES IN EQUITY|"
        r"STATEMENT(?:S)? OF OTHER COMPREHENSIVE INCOME",
        head,
    ) and not re.search(
        r"STATEMENT(?:S)? OF PROFIT OR LOSS|INCOME STATEMENT|FINANCIAL POS|BALANCE SHEET",
        head,
    ):
        return "OTHER"
    if re.search(r"STATEMENTS? OF FINANCIAL POS|BALANCE SHEET", head):
        return "STOCK"
    if re.search(
        r"STATEMENTS? OF PROFIT OR LOSS|STATEMENTS? OF PROFIT AND LOSS|"
        r"INCOME STATEMENT|STATEMENT OF INCOME|STATEMENTS? OF COMPREHENSIVE INCOME",
        head,
    ):
        return "FLOW"
    if re.search(
        r"STATEMENT(?:S)? OF CASH FLOWS?|STATEMENT(?:S)? OF CHANGES IN EQUITY",
        body,
    ) and not re.search(r"STATEMENT(?:S)? OF PROFIT OR LOSS|INCOME STATEMENT", body):
        return "OTHER"
    if _is_statement_page(page, "STOCK"):
        return "STOCK"
    if _is_statement_page(page, "FLOW"):
        return "FLOW"
    return None


def _page_statement_map(document: DocumentIR) -> dict[int, str | None]:
    """Carry P&L / balance-sheet context onto untitled continuation pages."""

    current: str | None = None
    mapping: dict[int, str | None] = {}
    for page in document.pages:
        if _is_notes_heading(page):
            current = None
            mapping[page.number] = None
            continue
        classified = _classify_page_statement(page)
        if classified == "OTHER" or (_is_notes_heading(page) and classified is None):
            current = None
        elif classified is not None:
            current = classified
        mapping[page.number] = current
    return mapping


def _page_has_eps(page: PageIR) -> bool:
    return bool(
        re.search(
            r"earnings?\s*/?\s*\(?\s*loss\s*\)?\s+per\s+(?:ordinary\s+)?share|"
            r"earnings?\s+(?:per\s+)?share|"
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
        # Logical-row rebuilds can synthesize LineIR objects that are not identical
        # to page.lines members. Fall back to nearest vertical neighbour.
        if not lines:
            return line.text
        index = min(
            range(len(lines)),
            key=lambda i: abs(lines[i].bbox.y0 - line.bbox.y0),
        )
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


def _period_header_points(page: PageIR, line: LineIR, period_end: date) -> tuple[list[float], list[float]]:
    """Return (target date/year points, prior-year points), including phrase dates."""

    months = (
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    )
    month_name = months[period_end.month - 1]
    month_abbr = month_name[:3]
    prior = period_end.year - 1
    target_phrases = (
        f"{period_end.day} {month_name} {period_end.year}",
        f"{period_end.day:02d} {month_name} {period_end.year}",
        f"{period_end.day} {month_abbr} {period_end.year}",
        f"{period_end.day:02d} {month_abbr} {period_end.year}",
        f"{period_end.day:02d}.{period_end.month:02d}.{period_end.year}",
        f"{period_end.day}.{period_end.month}.{period_end.year}",
        f"{period_end.day:02d}/{period_end.month:02d}/{period_end.year}",
    )
    prior_phrases = (
        f"31 december {prior}",
        f"31 dec {prior}",
        f"31.12.{prior}",
        f"31/12/{prior}",
        f"{period_end.day} {month_name} {prior}",
        f"{period_end.day:02d} {month_name} {prior}",
        f"{period_end.day} {month_abbr} {prior}",
        f"{period_end.day:02d} {month_abbr} {prior}",
        f"{period_end.day:02d}.{period_end.month:02d}.{prior}",
        f"{period_end.day}.{period_end.month}.{prior}",
        f"{period_end.day:02d}/{period_end.month:02d}/{prior}",
        f"{period_end.day:02d}-{period_end.month:02d}-{prior}",
    )
    target_points: list[float] = []
    prior_points: list[float] = []
    for header_line in page.lines:
        if header_line.bbox.y0 >= line.bbox.y0:
            break
        for phrase in target_phrases:
            for _x0, _x1, center in _phrase_occurrences(header_line, phrase):
                target_points.append(center)
        for phrase in prior_phrases:
            for _x0, _x1, center in _phrase_occurrences(header_line, phrase):
                prior_points.append(center)
        for token in header_line.tokens:
            stripped = token.text.strip("():")
            if stripped == str(period_end.year):
                target_points.append(token.bbox.center_x)
            elif stripped == str(prior):
                prior_points.append(token.bbox.center_x)
    return target_points, prior_points


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
    ("for the quarter", "QUARTER"),
    ("quarter ended", "QUARTER"),
    # Bare "period ended" is not a three-month cue; column fiscal dates resolve it.
    ("six months", "YTD"),
    ("nine months", "YTD"),
    ("twelve months", "YTD"),
    ("year to date", "YTD"),
    ("year ended", "YTD"),
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


_DATE_TOKEN = re.compile(
    r"^(?P<d>\d{1,2})[./-](?P<m>\d{1,2})[./-](?P<y>20\d{2})$"
)


def _dated_header_centers(page: PageIR, line: LineIR) -> list[float]:
    """X-centers of dd.mm.yyyy / dd/mm/yyyy header dates above a value row."""

    centers: list[float] = []
    for header_line in page.lines:
        if header_line.bbox.y0 >= line.bbox.y0:
            break
        for token in header_line.tokens:
            if _DATE_TOKEN.match(token.text.strip("()")):
                centers.append(token.bbox.center_x)
    return centers


def _split_regions_by_date_midpoint(
    regions: list[_HeaderSpan],
    date_centers: list[float],
    page_width: float,
) -> list[_HeaderSpan]:
    """When dual headers sit above paired date columns, split at the date midpoint.

    Phrase centers for 'Group'/'Bank' or 'six months'/'quarter' are often shifted
    relative to the numeric columns; the date row is the authoritative partition.
    Only applies to a simple left/right dual header, not repeating Group/Company
    duration blocks (Six|Three|Six|Three).
    """

    if len(regions) != 2 or len(date_centers) < 4:
        return regions
    kinds = {span.kind for span in regions}
    dual_duration = kinds == {"YTD", "QUARTER"}
    dual_entity = "GROUP" in kinds and bool(kinds & {"COMPANY", "BANK"})
    if not dual_duration and not dual_entity:
        return regions
    ordered_dates = sorted(date_centers)
    mid = (ordered_dates[len(ordered_dates) // 2 - 1] + ordered_dates[len(ordered_dates) // 2]) / 2
    ordered = sorted(regions, key=lambda span: span.center)
    left, right = ordered[0], ordered[1]
    return [
        _HeaderSpan(left.kind, 0.0, mid, left.center, left.phrase),
        _HeaderSpan(right.kind, mid, page_width, right.center, right.phrase),
    ]


def _collapse_nearby_alias_spans(
    spans: list[_HeaderSpan], *, max_gap: float = 90.0
) -> list[_HeaderSpan]:
    """Merge overlapping aliases of the same kind; keep distinct column groups."""

    ordered = sorted(spans, key=lambda span: span.center)
    collapsed: list[_HeaderSpan] = []
    for span in ordered:
        if (
            collapsed
            and collapsed[-1].kind == span.kind
            and span.center - collapsed[-1].center <= max_gap
        ):
            continue
        collapsed.append(span)
    return collapsed


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
            parent_row = _owned_header_regions(
                _collapse_nearby_alias_spans(spans), page.width
            )
    if not parent_row:
        return []
    return _split_regions_by_date_midpoint(
        parent_row, _dated_header_centers(page, line), page.width
    )


_ENTITY_PHRASES: tuple[tuple[str, str], ...] = (
    ("group", "GROUP"),
    ("consolidated", "GROUP"),
    ("company", "COMPANY"),
    ("bank", "BANK"),
)
STOCK_CORE = {"TOTAL_ASSETS", "TOTAL_EQUITY", "TOTAL_LIABILITIES"}
_TITLE_COMPANY = re.compile(
    r"\bCOMPANY\s+(?:INCOME\s+)?STATEMENTS?\b|"
    r"\b(?:INCOME\s+STATEMENT|STATEMENTS?\s+OF\s+(?:FINANCIAL\s+POSITION|COMPREHENSIVE\s+INCOME|PROFIT(?:\s+OR\s+LOSS)?))\s*[-–:]\s*COMPANY\b",
    re.I,
)
_TITLE_BANK = re.compile(
    r"\bBANK\s+(?:INCOME\s+)?STATEMENTS?\b|"
    r"\b(?:INCOME\s+STATEMENT|STATEMENTS?\s+OF\s+(?:FINANCIAL\s+POSITION|COMPREHENSIVE\s+INCOME|PROFIT(?:\s+OR\s+LOSS)?))\s*[-–:]\s*BANK\b",
    re.I,
)
_TITLE_GROUP = re.compile(
    r"\b(?:CONSOLIDATED|GROUP)\s+(?:INCOME\s+)?STATEMENTS?\b|"
    r"\b(?:INCOME\s+STATEMENT|STATEMENTS?\s+OF\s+(?:FINANCIAL\s+POSITION|COMPREHENSIVE\s+INCOME|PROFIT(?:\s+OR\s+LOSS)?))\s*[-–:]\s*(?:CONSOLIDATED|GROUP)\b",
    re.I,
)
_NOTES_HEADING = re.compile(r"NOTES?\s+TO\s+THE\s+FINANCIAL\s+STATEMENTS", re.I)
_SCALE_FRAGMENT = re.compile(
    r"['’]?\s*0{3}s?|\bthousands?\b|\bmn(?:s|['’]s)?\b|\bmillions?\b|\bbn(?:s|['’]s)?\b|\bbillions?\b",
    re.I,
)
_CURRENCY_FRAGMENT = re.compile(r"\b(?:rs\.?|lkr|usd|rupees?)\b", re.I)


def _entity_spans_on_line(header_line: LineIR) -> list[_HeaderSpan]:
    return [
        _HeaderSpan(kind, x0, x1, center, phrase)
        for phrase, kind in _ENTITY_PHRASES
        for x0, x1, center in _phrase_occurrences(header_line, phrase)
    ]


def _entity_parent_regions(page: PageIR, line: LineIR) -> list[_HeaderSpan]:
    """Parent entity spans from the lowest header row that has Group and Company/Bank.

    Repeated Group/Company groups are partitioned at midpoints, matching duration spans.
    Cross-row title words are ignored so a Company statement is not split by a
    nearby Group mention.
    """

    parent_row: list[_HeaderSpan] | None = None
    for header_line in page.lines:
        if header_line.bbox.y0 >= line.bbox.y0:
            break
        spans = _entity_spans_on_line(header_line)
        kinds = {span.kind for span in spans}
        if "GROUP" in kinds and kinds & {"COMPANY", "BANK"} and len(spans) >= 2:
            parent_row = _owned_header_regions(spans, page.width)
    if not parent_row:
        return []
    return _split_regions_by_date_midpoint(
        parent_row, _dated_header_centers(page, line), page.width
    )


def _column_entity_header_kinds(page: PageIR) -> set[str]:
    """Entity kinds that appear together as short column headers, not body prose."""

    kinds: set[str] = set()
    for line in page.lines[:20]:
        words = [re.sub(r"[^A-Za-z]", "", token.text).upper() for token in line.tokens]
        words = [word for word in words if word]
        found = [word for word in words if word in {"GROUP", "CONSOLIDATED", "COMPANY", "BANK"}]
        if len(found) >= 2 and len(words) <= 8:
            kinds.update("GROUP" if word == "CONSOLIDATED" else word for word in found)
    return kinds


def _page_has_dual_entity_columns(page: PageIR) -> bool:
    """True when Group and Company/Bank headers jointly own columns on this page."""

    column_kinds = _column_entity_header_kinds(page)
    if "GROUP" in column_kinds and column_kinds & {"COMPANY", "BANK"}:
        return True
    return bool(page.lines) and bool(_entity_parent_regions(page, page.lines[-1]))


def _page_title_entity(page: PageIR) -> str | None:
    """Classify a page from its statement title, then dual column headers."""

    head = " ".join(line.text for line in page.lines[:4])
    company_title = bool(_TITLE_COMPANY.search(head))
    bank_title = bool(_TITLE_BANK.search(head))
    group_title = bool(_TITLE_GROUP.search(head))
    dual_columns = _page_has_dual_entity_columns(page)
    if company_title and not group_title:
        return "COMPANY"
    if bank_title and not group_title:
        return "BANK"
    if group_title and dual_columns:
        return "DUAL"
    if group_title:
        return "GROUP"
    if dual_columns:
        return "DUAL"
    return None


def _is_notes_heading(page: PageIR) -> bool:
    head_lines = " ".join(line.text for line in page.lines[:8])
    head_text = " ".join(page.text.splitlines()[:16])
    if _NOTES_HEADING.search(head_lines) or _NOTES_HEADING.search(head_text):
        return True
    return bool(
        re.search(
            r"identifiable assets and liabilities|"
            r"disposal of equity stake|"
            r"transactions with other related",
            head_text,
            re.I,
        )
    )


_PERIOD_YEAR = re.compile(
    r"(?:months?\s+ended|quarter\s+ended|period\s+ended|year\s+ended|as\s+at|as\s+of)"
    r"[^\n]{0,48}?\b(20\d{2})\b",
    re.I,
)


def _page_covers_period(page: PageIR, period_end: date) -> bool:
    """Reject a page whose stated period years cannot be this quarter.

    Comparative-only pages that mention only the prior year must not enter the
    candidate pool for the current target quarter.
    """

    head = "\n".join(page.text.splitlines()[:18])
    # Non-greedy duration-year capture plus all bare years in the head. Dual
    # Group/Company headers list current and comparative years on one line;
    # a greedy capture previously kept only the final comparative year.
    years = {int(year) for year in _PERIOD_YEAR.findall(head)}
    years |= {int(year) for year in re.findall(r"\b(20\d{2})\b", head)}
    if not years:
        return True
    return period_end.year in years


def _comparison_from_layout(
    page: PageIR,
    line: LineIR,
    token: TokenIR,
    period_end: date,
) -> tuple[str, int]:
    """Infer comparison_role and source header year from spatial year/date headers."""

    target_points, prior_points = _period_header_points(page, line, period_end)
    x = token.bbox.center_x
    if target_points or prior_points:
        target_near = _closeness(x, target_points, page.width) if target_points else 0.0
        prior_near = _closeness(x, prior_points, page.width) if prior_points else 0.0
        if prior_points and prior_near > target_near:
            return "COMPARATIVE", period_end.year - 1
        if target_points and target_near >= prior_near:
            return "CURRENT", period_end.year
    return "CURRENT", period_end.year


def _is_related_party_page(page: PageIR) -> bool:
    head = " ".join(line.text for line in page.lines[:10])
    return bool(
        re.search(
            r"related\s+(?:party|parties|entities)|transactions with other related",
            head,
            re.I,
        )
    )


def _is_group_segment_page(page: PageIR) -> bool:
    """Group operating-segment note pages must never feed standalone P&L facts."""

    head = " ".join(line.text for line in page.lines[:12])
    return bool(
        re.search(
            r"operating\s+segments?|"
            r"income,?\s+profit\s+and\s+asset\s+information|"
            r"segmental?\s+(?:information|analysis|results)|"
            r"group'?s?\s+operating\s+segments?",
            head,
            re.I,
        )
    )


def _column_duration_months(
    page: PageIR,
    line: LineIR,
    token: TokenIR,
    period_end: date,
    *,
    document_has_quarter_heading: bool = False,
) -> int | None:
    """Duration for the selected value's column — never override with page FY cues."""

    x = token.bbox.center_x
    parent = _parent_kind_at(x, _duration_parent_regions(page, line))
    if parent is not None:
        if parent.kind == "QUARTER":
            return 3
        if parent.kind == "YTD":
            phrase = parent.phrase.lower()
            if "six" in phrase:
                return 6
            if "nine" in phrase:
                return 9
            if "twelve" in phrase or "year ended" in phrase or "year to date" in phrase:
                return 12
            explicit = _duration_months(phrase) or _duration_months(_page_head_text(page))
            if explicit in {6, 9, 12}:
                return explicit
            return _page_flow_duration(
                page, document_has_quarter_heading=document_has_quarter_heading
            )
    # Date-header proximity: Period Ended under target date needs fiscal evidence.
    target_points, prior_points = _period_header_points(page, line, period_end)
    year_ended_points: list[float] = []
    period_ended_points: list[float] = []
    for header_line in page.lines:
        if header_line.bbox.y0 >= line.bbox.y0:
            break
        for phrase, kind in (
            ("year ended", "YTD"),
            ("period ended", "QUARTER"),
            ("quarter ended", "QUARTER"),
        ):
            for _x0, _x1, center in _phrase_occurrences(header_line, phrase):
                if kind == "YTD":
                    year_ended_points.append(center)
                else:
                    period_ended_points.append(center)
    dated = _header_dates_by_kind(page, line)
    if period_ended_points or year_ended_points:
        period_near = _closeness(x, period_ended_points, page.width) if period_ended_points else 0.0
        year_near = _closeness(x, year_ended_points, page.width) if year_ended_points else 0.0
        if period_near > year_near:
            period_dates = [(d, c) for kind, d, c in dated if kind == "PERIOD"]
            year_dates = [d for kind, d, _c in dated if kind == "YEAR"]
            if period_dates and year_dates:
                period_date = min(period_dates, key=lambda item: abs(item[1] - x))[0]
                year_date = min(year_dates, key=lambda item: abs((item - period_date).days))
                fiscal = _fiscal_months_between(year_date, period_date)
                if fiscal is not None:
                    return fiscal
            explicit = _duration_months(_page_head_text(page))
            if explicit in {3, 6, 9, 12}:
                return explicit
            return None
        if year_near > period_near:
            return 12
    if (
        target_points
        and (
            not prior_points
            or _closeness(x, target_points, page.width) >= _closeness(x, prior_points, page.width)
        )
        and (period_ended_points or _page_has_statement_quarter_heading(page))
    ):
        period_dates = [(d, c) for kind, d, c in dated if kind == "PERIOD"]
        year_dates = [d for kind, d, _c in dated if kind == "YEAR"]
        if period_dates and year_dates:
            period_date = min(period_dates, key=lambda item: abs(item[1] - x))[0]
            year_date = min(year_dates, key=lambda item: abs((item - period_date).days))
            fiscal = _fiscal_months_between(year_date, period_date)
            if fiscal is not None:
                return fiscal
        if _page_has_statement_quarter_heading(page):
            return 3
        return None
    return _page_flow_duration(page, document_has_quarter_heading=document_has_quarter_heading)


def _is_sofp_eligible(page: PageIR, document: DocumentIR, mapping: dict[int, str | None]) -> bool:
    """Core stock totals must sit on an explicit SOFP or a proven continuation."""

    if _is_notes_heading(page):
        return False
    if _is_statement_page(page, "STOCK"):
        return True
    head = " ".join(line.text for line in page.lines[:10]).upper()
    if re.search(r"\b(?:OPERATING SEGMENTS?|CASH FLOWS?|CHANGES IN EQUITY)\b", head):
        return False
    previous = next((item for item in document.pages if item.number == page.number - 1), None)
    if previous is None:
        return False
    if not _is_statement_page(previous, "STOCK") and mapping.get(previous.number) != "STOCK":
        return False
    if _is_notes_heading(previous):
        return False
    return bool(
        re.search(
            r"\bTOTAL\s+ASSETS\b|"
            r"\bNON[- ]CURRENT ASSETS\b|"
            r"\b(?:TOTAL\s+)?(?:NON[- ]CURRENT|CURRENT)\s+LIABILIT",
            page.text,
            re.I,
        )
    )


_SECTION_HEADER = re.compile(
    r"^(?:non[- ]current|current)\s+(?:assets|liabilities)$|"
    r"^capital and reserves$|"
    r"^equity and liabilities$|"
    r"^assets$|"
    r"^liabilities$",
    re.I,
)
_STOCK_TOTAL_LABEL = re.compile(
    r"^\s*total\s+(?:equity(?:\s+and\s+liabilities)?|assets|liabilities)\b",
    re.I,
)


def _max_abs_numeric(line: LineIR) -> Decimal:
    values = [
        abs(value)
        for token in line.numeric_tokens
        if (value := _decimal(token.text)) is not None
    ]
    return max(values) if values else Decimal("0")


def _line_without_numbers(line: LineIR) -> LineIR:
    tokens = tuple(token for token in line.tokens if not token.is_numeric and token.text != "-")
    text = " ".join(token.text for token in tokens)
    return LineIR(line.page, line.line_id, text, line.bbox, tokens)


def _is_section_header(text: str) -> bool:
    stripped = re.sub(r"\s+", " ", text).strip(" :-–")
    return bool(_SECTION_HEADER.fullmatch(stripped))


def _blocks_numeric_prefix_merge(text: str) -> bool:
    """Do not glue a numeric-only total onto the next section or stock total label."""

    stripped = re.sub(r"\s+", " ", text).strip(" :-–")
    return _is_section_header(stripped) or bool(_STOCK_TOTAL_LABEL.match(stripped))


def _merge_lines(first: LineIR, second: LineIR) -> LineIR:
    tokens = first.tokens + second.tokens
    bbox = BBox(
        min(first.bbox.x0, second.bbox.x0),
        min(first.bbox.y0, second.bbox.y0),
        max(first.bbox.x1, second.bbox.x1),
        max(first.bbox.y1, second.bbox.y1),
    )
    return LineIR(
        first.page,
        f"{first.line_id}+{second.line_id}",
        f"{first.text} {second.text}".strip(),
        bbox,
        tokens,
    )


def _has_money_tokens(line: LineIR) -> bool:
    return any(_decimal(token.text) is not None for token in line.numeric_tokens)


def _logical_rows(page: PageIR) -> tuple[LineIR, ...]:
    """Merge a label with an adjacent numeric line when they form one financial row.

    CSE statements sometimes print the figures on the line above a wrapped label.
    """

    lines = list(page.lines)
    merged: list[LineIR] = []
    index = 0
    max_gap = max(8.0, page.height * 0.012)
    while index < len(lines):
        current = lines[index]
        if index + 1 < len(lines):
            following = lines[index + 1]
            gap = following.bbox.y0 - current.bbox.y1
            close = -max_gap <= gap <= max_gap
            current_has_label = bool(re.search(r"[A-Za-z]{3,}", current.text))
            following_has_label = bool(
                re.search(r"[A-Za-z]{3,}", _metric_label(following) or following.text)
            )
            current_has_money = _has_money_tokens(current)
            following_has_money = _has_money_tokens(following)
            if (
                close
                and current_has_label
                and not current_has_money
                and following_has_money
                and not following_has_label
            ):
                merged.append(_merge_lines(current, following))
                index += 2
                continue
            # Windforce-style: "Earning share" / "Basic earnings per share" then a
            # detached "Rs." unit line then the numeric figures on the next row.
            if (
                close
                and current_has_label
                and not current_has_money
                and re.search(
                    r"\b(?:earning(?:s)?\s+share|earnings?\s+per\s+share|eps)\b",
                    current.text,
                    re.I,
                )
                and index + 2 < len(lines)
            ):
                unit_line = lines[index + 1]
                value_line = lines[index + 2]
                unit_gap = value_line.bbox.y0 - unit_line.bbox.y1
                unit_only = bool(
                    re.fullmatch(r"\s*(?:rs\.?|lkr|usd)\s*(?:'?\s*000|mn|m)?\s*", unit_line.text, re.I)
                    or (
                        not _has_money_tokens(unit_line)
                        and re.search(r"\b(?:rs\.?|lkr)\b", unit_line.text, re.I)
                        and len(unit_line.text.split()) <= 3
                    )
                )
                if (
                    unit_only
                    and _has_money_tokens(value_line)
                    and not re.search(r"[A-Za-z]{3,}", _metric_label(value_line) or value_line.text)
                    and -max_gap <= unit_gap <= max_gap * 1.5
                ):
                    merged.append(_merge_lines(current, value_line))
                    index += 3
                    continue
            if (
                close
                and current_has_label
                and not current_has_money
                and following_has_label
                and re.search(r"\b(?:on|of|from|and|the|to|for)\s*$", current.text, re.I)
                and len((_metric_label(following) or "").split()) <= 6
            ):
                lines[index] = _merge_lines(current, following)
                lines.pop(index + 1)
                continue
            stock_total = bool(
                re.search(r"\btotal\s+(?:equity|assets|liabilities)\b", current.text, re.I)
            )
            if (
                close
                and current_has_label
                and current.numeric_tokens
                and following.numeric_tokens
                and not following_has_label
                and stock_total
                and _max_abs_numeric(following) >= _max_abs_numeric(current) * 10
            ):
                merged.append(_merge_lines(_line_without_numbers(current), following))
                index += 2
                continue
            if (
                close
                and following_has_label
                and not following.numeric_tokens
                and current.numeric_tokens
                and not current_has_label
                and not _blocks_numeric_prefix_merge(following.text)
            ):
                merged.append(_merge_lines(following, current))
                index += 2
                continue
        merged.append(current)
        index += 1
    return tuple(merged)


def _page_stock_identity(page: PageIR, entity: str, period_end: date) -> bool:
    """True when explicit A/E/L on this page satisfy Assets ≈ Liabilities + Equity."""

    values: dict[str, Decimal] = {}
    for rule in METRIC_RULES:
        if rule.code not in STOCK_CORE:
            continue
        for line in _logical_rows(page):
            label = _metric_label(line) or line.text
            if not any(pattern.search(label) for pattern in rule.aliases):
                continue
            selected = _select_layout_value(page, line, rule, entity, period_end)
            if selected is None:
                continue
            values[rule.code] = selected[1]
            break
    assets = values.get("TOTAL_ASSETS")
    equity = values.get("TOTAL_EQUITY")
    liabilities = values.get("TOTAL_LIABILITIES")
    if assets is None or equity is None or liabilities is None:
        return False
    difference = abs(assets - liabilities - equity)
    return difference <= max(abs(assets) * Decimal("0.02"), Decimal("1"))


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


def _value_belongs_to_required_entity(
    *,
    entity: str,
    entity_span: _HeaderSpan | None,
    entity_regions: list[_HeaderSpan],
    page: PageIR,
) -> bool:
    """Company/Bank values must sit in a matching parent span. Group is never a fallback."""

    if entity not in {"COMPANY", "BANK"}:
        return True
    if entity_regions:
        return entity_span is not None and entity_span.kind == entity
    return not _page_has_dual_entity_columns(page)


def _graph_parent_kind(graph: dict[str, Any] | None) -> str | None:
    if not graph:
        return None
    for node in graph.get("nodes", []):
        if node.get("type") == "PARENT_HEADER" and node.get("kind"):
            return str(node["kind"])
    return None


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
    for token in _coalesce_spaced_thousands(line.tokens):
        if not token.is_numeric and token.text != "-":
            continue
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
    target_year_points, prior_year_points = _period_header_points(page, line, period_end)
    target_date_pattern = (
        rf"(?:{period_end.day:02d}[./-]{period_end.month:02d}[./-]{period_end.year}|"
        rf"{period_end.day}[./-]{period_end.month}[./-]{period_end.year})"
    )
    target_date_points = _header_points(page, line, target_date_pattern)
    target_date_points.extend(
        point for point in target_year_points if point not in target_date_points
    )
    quarter_points = _header_points(page, line, r"QUARTER|\b[1-4]\s*Q\b")
    quarter_points.extend(_line_points(page, line, "three months"))
    change_points = _header_points(page, line, r"%|CHANGE|VARIANCE")
    ytd_points: list[float] = []
    for phrase in ("six months", "nine months", "twelve months", "year to date"):
        ytd_points.extend(_line_points(page, line, phrase))
    duration_regions = _duration_parent_regions(page, line)
    entity_regions = _entity_parent_regions(page, line)

    scored: list[tuple[float, TokenIR, Decimal | None, dict[str, float]]] = []
    page_scope = page_entity if page_entity is not None else _page_entity_confidence(page, entity)
    cluster_centers = cluster_numeric_columns(page, min_y=max(0.0, line.bbox.y0 - 80))
    for index, (token, value) in enumerate(candidates):
        x = token.bbox.center_x
        entity_span = _parent_kind_at(x, entity_regions)
        if not _value_belongs_to_required_entity(
            entity=entity,
            entity_span=entity_span,
            entity_regions=entity_regions,
            page=page,
        ):
            continue
        entity_near = _closeness(x, expected_points, page.width)
        other_near = _closeness(x, other_points, page.width)
        if entity_span is not None and entity_span.kind in {entity, "COMPANY", "BANK"}:
            entity_component = 1.0
        elif len(expected_points) == 1 and len(other_points) == 1:
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
        parent = _parent_kind_at(x, duration_regions)
        # Reject prior-year / comparative columns for FLOW and STOCK.
        if (
            target_year_points
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
                    "entity_span": 1.0 if entity_span is not None else 0.0,
                },
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        company_money = [
            (token, value)
            for token, value in candidates
            if value is not None
            and _parent_kind_at(token.bbox.center_x, entity_regions) is not None
            and _parent_kind_at(token.bbox.center_x, entity_regions).kind == entity
        ]
        if entity in {"COMPANY", "BANK"} and len(company_money) == 1:
            token, value = company_money[0]
            graph = build_value_graph(
                label=_metric_label(line) or line.text,
                value_token=token,
                entity=entity,
                period_end=period_end.isoformat(),
                line=line,
                column_scores=[],
                cluster_centers=cluster_numeric_columns(page, min_y=max(0.0, line.bbox.y0 - 80)),
                components={"entity": 1.0, "date": 0.65, "quarter": 0.72},
                selected_score=0.55,
                runner_up_score=0.0,
            )
            return token, value, 0.55, graph
        return None
    score, token, value, components = scored[0]
    if value is None or components["change_penalty"] >= 0.6:
        return None
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    margin = max(0.0, score - runner_up)
    column_confidence = min(1.0, score * 0.75 + margin * 1.5)
    governing = _parent_kind_at(token.bbox.center_x, duration_regions)
    entity_governing = _parent_kind_at(token.bbox.center_x, entity_regions)
    if entity in {"COMPANY", "BANK"}:
        if entity_governing is not None and entity_governing.kind != entity:
            return None
        if entity_regions and entity_governing is None:
            return None
    graph_parent = None
    if entity_governing is not None:
        graph_parent = {
            "phrase": entity_governing.phrase,
            "kind": entity_governing.kind,
            "x0": entity_governing.x0,
            "x1": entity_governing.x1,
        }
    elif governing is not None:
        graph_parent = {
            "phrase": governing.phrase,
            "kind": governing.kind,
            "x0": governing.x0,
            "x1": governing.x1,
        }
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
        parent_header=graph_parent,
    )
    return token, value, column_confidence, graph


def _coalesce_spaced_thousands(tokens: tuple[TokenIR, ...]) -> tuple[TokenIR, ...]:
    """Join PDF words such as '1' + ',557' or '1' + ',' + '557' into 1,557."""

    merged: list[TokenIR] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        left = token.text.replace(" ", "")
        if index + 2 < len(tokens) and re.fullmatch(r"\(?\d{1,3}", left):
            comma = tokens[index + 1]
            third = tokens[index + 2]
            if (
                comma.text.strip() == ","
                and re.fullmatch(r"\d{3}\)?", third.text.replace(" ", ""))
                and comma.bbox.x0 - token.bbox.x1 <= 12
                and third.bbox.x0 - comma.bbox.x1 <= 12
            ):
                text = f"{left},{third.text.replace(' ', '').strip('()')}"
                if left.startswith("(") or third.text.endswith(")"):
                    text = f"({text.strip('()')})"
                merged.append(
                    TokenIR(
                        text,
                        BBox(
                            token.bbox.x0,
                            min(token.bbox.y0, third.bbox.y0),
                            third.bbox.x1,
                            max(token.bbox.y1, third.bbox.y1),
                        ),
                        token.block_no,
                        token.line_no,
                        token.word_no,
                    )
                )
                index += 3
                continue
        if index + 1 < len(tokens):
            nxt = tokens[index + 1]
            right = nxt.text.replace(" ", "")
            close = nxt.bbox.x0 - token.bbox.x1 <= 10 and abs(token.bbox.y0 - nxt.bbox.y0) <= 5
            if (
                close
                and re.fullmatch(r"\(?\d{1,3}\)?", left)
                and re.fullmatch(r",\d{3}\)?", right)
                and "." not in left
                and "." not in right
            ):
                text = f"{left.rstrip(')')},{right.lstrip(',(')}"
                if left.startswith("(") or right.endswith(")"):
                    text = f"({text.strip('()')})"
                merged.append(
                    TokenIR(
                        text,
                        BBox(
                            token.bbox.x0,
                            min(token.bbox.y0, nxt.bbox.y0),
                            nxt.bbox.x1,
                            max(token.bbox.y1, nxt.bbox.y1),
                        ),
                        token.block_no,
                        token.line_no,
                        token.word_no,
                    )
                )
                index += 2
                continue
        merged.append(token)
        index += 1
    return tuple(merged)


def _unit_for_layout(
    document: DocumentIR,
    page: PageIR,
    line: LineIR,
    metric_type: str,
    *,
    force_rescan: bool = False,
) -> tuple[str | None, int | None, str | None, float]:
    if metric_type == "MONETARY_PER_SHARE":
        row_candidates = detect_candidates(line.text, scope=UnitScope.ROW, page=page.number)
        if force_rescan and not row_candidates:
            # Look at immediate neighbors for detached "Rs." unit lines.
            page_lines = list(page.lines)
            for index, candidate in enumerate(page_lines):
                if candidate is line or abs(candidate.bbox.center_y - line.bbox.center_y) > 24:
                    continue
                row_candidates = detect_candidates(
                    candidate.text, scope=UnitScope.ROW, page=page.number
                )
                if row_candidates:
                    break
                if index + 1 < len(page_lines):
                    composed = compose_unit_text(candidate.text, page_lines[index + 1].text)
                    row_candidates = detect_candidates(
                        composed, scope=UnitScope.ROW, page=page.number
                    )
                    if row_candidates:
                        break
        currency = row_candidates[0].currency if row_candidates else "LKR"
        source = row_candidates[0].source_text if row_candidates else "Per-share amount"
        return currency, 1, source, 0.98 if row_candidates else (0.9 if force_rescan else 0.85)

    collected: list[UnitCandidate] = []
    ranked: list[tuple[float, str, int, str]] = []
    for candidate_page in document.pages:
        page_gap = abs(candidate_page.number - page.number)
        if force_rescan and page_gap > 1:
            continue
        page_lines = list(candidate_page.lines)
        for line_index, candidate_line in enumerate(page_lines):
            neighbor = ""
            if line_index + 1 < len(page_lines):
                neighbor = page_lines[line_index + 1].text
            composed = compose_unit_text(candidate_line.text, neighbor)
            probe_texts = [candidate_line.text]
            if (
                _CURRENCY_FRAGMENT.search(candidate_line.text)
                and _SCALE_FRAGMENT.search(neighbor)
            ) or (
                _SCALE_FRAGMENT.search(candidate_line.text)
                and line_index > 0
                and _CURRENCY_FRAGMENT.search(page_lines[line_index - 1].text)
            ):
                probe_texts.append(composed)
            # Join bare LKR/Rs. with a nearby scale fragment within ±2 header lines
            # (MBSL-style layouts split currency and '000 across non-adjacent rows).
            if (
                candidate_page.number == page.number
                and _CURRENCY_FRAGMENT.search(candidate_line.text)
                and not _SCALE_FRAGMENT.search(candidate_line.text)
            ):
                for offset in (1, 2, -1, -2):
                    other_index = line_index + offset
                    if other_index < 0 or other_index >= len(page_lines):
                        continue
                    other_text = page_lines[other_index].text
                    if _SCALE_FRAGMENT.search(other_text):
                        probe_texts.append(compose_unit_text(candidate_line.text, other_text))
                        break
            if not any(_unit_declaration(text) or _SCALE_FRAGMENT.search(text) for text in probe_texts):
                continue
            if "per share" in candidate_line.text.lower():
                continue
            for probe in probe_texts:
                units = detect_candidates(
                    probe,
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
                    if force_rescan and unit.scale_factor > 1:
                        specificity += 0.1
                    ranked.append(
                        (
                            same_page + distance_score + specificity,
                            unit.currency,
                            unit.scale_factor,
                            probe.strip(),
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
    """Skip NCI/group attribution, OCI, and discontinued-ops lines."""

    return bool(
        NCI_OR_GROUP_PAT_RE.search(text)
        or re.search(r"other comprehensive income", text, re.I)
        or re.search(r"from\s+discontinued\s+operations?", text, re.I)
    )


def _is_continuing_operations_pat(text: str) -> bool:
    return bool(re.search(r"from\s+continuing\s+operations?", text, re.I))


def _page_has_unqualified_pat(page: PageIR) -> bool:
    """True when the page also prints total profit for the period."""

    for line in page.lines:
        label = _metric_label(line) or line.text
        if _is_continuing_operations_pat(label) or _is_excluded_pat_line(label):
            continue
        if re.search(
            r"(?:profit|loss).{0,20}for\s+the\s+(?:period|quarter|year)|"
            r"(?:profit|loss).{0,20}after\s+(?:income\s+)?tax",
            label,
            re.I,
        ):
            return True
    return False


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
) -> tuple[list[_LayoutCandidate], bool, bool, bool]:
    candidates: list[_LayoutCandidate] = []
    found_outside_quarter = False
    found_wrong_scope = False
    label_unresolved = False
    mapping = statement_map if statement_map is not None else _page_statement_map(document)
    last_entity_by_statement: dict[str, float] = {}
    identity_by_page: dict[int, bool] = {}
    document_has_quarter_heading = _document_has_quarter_flow_heading(document)
    document_quarter_context = document_has_quarter_heading or any(
        _page_is_exact_quarter(page, document_has_quarter_heading=False)
        for page in document.pages
        if _classify_page_statement(page) == "FLOW" or _is_statement_page(page, "FLOW")
    )
    for page in document.pages:
        if rule.statement == "FLOW" and re.search(
            r"STATEMENT(?:S)?\s+OF\s+CASH\s+FLOWS?",
            " ".join(line.text for line in page.lines[:8]),
            re.I,
        ):
            continue
        title_entity = _page_title_entity(page)
        if title_entity == "GROUP" and entity in {"COMPANY", "BANK"}:
            found_wrong_scope = True
            continue
        if title_entity in {"COMPANY", "BANK"} and entity == "GROUP":
            continue
        if not _page_covers_period(page, period_end):
            continue
        if _is_notes_heading(page) and rule.code in STOCK_CORE | {
            "TOP_LINE",
            "OPERATING_PROFIT",
            "PBT",
            "PAT",
        }:
            continue
        if _is_related_party_page(page) and rule.code in {
            "TOP_LINE",
            "OPERATING_PROFIT",
            "PBT",
            "PAT",
        }:
            continue
        if _is_group_segment_page(page) and rule.code in {
            "TOP_LINE",
            "OPERATING_PROFIT",
            "PBT",
            "PAT",
            "EPS_BASIC",
            "EPS_DILUTED",
        }:
            continue
        if rule.code in STOCK_CORE and not _is_sofp_eligible(page, document, mapping):
            continue
        inherited_statement = mapping.get(page.number)
        inherited_entity = (
            last_entity_by_statement.get(inherited_statement) if inherited_statement else None
        )
        page_entity = _page_entity_confidence(page, entity, inherited=inherited_entity)
        if inherited_statement:
            last_entity_by_statement[inherited_statement] = page_entity
        cumulative_only_page = _page_is_cumulative_only(
            page, document_has_quarter_heading=document_has_quarter_heading
        )
        page_duration = _page_flow_duration(
            page, document_has_quarter_heading=document_has_quarter_heading
        )
        exact_quarter = (not cumulative_only_page) and (
            _page_is_exact_quarter(
                page, document_has_quarter_heading=document_has_quarter_heading
            )
            or bool(
                document_quarter_context
                and page_duration not in {6, 9, 12}
                and not cumulative_only_page
                and (
                    inherited_statement == "FLOW"
                    or rule.code in {"EPS_BASIC", "EPS_DILUTED", "NAVPS"}
                )
            )
        )
        primary_statement = _is_statement_page(page, rule.statement)
        expected_statement = primary_statement or inherited_statement == rule.statement
        if (
            rule.code in {"EPS_BASIC", "EPS_DILUTED"}
            and _page_has_eps(page)
            and not _is_notes_heading(page)
        ):
            expected_statement = True
        if rule.code == "NAVPS" and _page_has_navps(page):
            expected_statement = True
        for line in _logical_rows(page):
            if rule.code == "PAT" and _is_excluded_pat_line(line.text):
                continue
            if rule.code == "PAT" and (
                len((_metric_label(line) or line.text).split()) > 18
                or re.search(
                    r"\bwe confirm\b|\bno material\b|\bcontingent liabilities\b|"
                    r"\bcircumstances have arisen\b",
                    line.text,
                    re.I,
                )
            ):
                continue
            if (
                rule.code == "PAT"
                and _is_continuing_operations_pat(line.text)
                and _page_has_unqualified_pat(page)
            ):
                continue
            if rule.code == "TOP_LINE" and _is_rejected_top_line_label(
                _metric_label(line) or line.text
            ):
                continue
            if rule.code == "TOP_LINE" and re.search(r"revenue\s+reserves?\b", line.text, re.I):
                continue
            if rule.code in {"TOTAL_EQUITY", "TOTAL_LIABILITIES"} and re.search(
                r"\bequity\s+(?:and|&)\s+liabilities\b|"
                r"\bliabilities\s+(?:and|&)\s+(?:equity|shareholders|funds)\b",
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
                if re.search(r"\bebitda\b|working\s+capital|cash\s+flows?", raw_label, re.I):
                    continue
                if re.search(
                    r"from\s+(?:continuing|discontinued?)\s+operations?|"
                    r"before\s+(?:income\s+)?tax",
                    raw_label,
                    re.I,
                ) and not re.search(r"\boperating\b|\bebit\b", raw_label, re.I):
                    continue
                if not re.search(
                    r"\boperating\b|\bebit\b|earnings\s+before\s+interest|"
                    r"results?\s+from\s+operat|from\s+operations?",
                    raw_label,
                    re.I,
                ):
                    continue
            if rule.code in {"EPS_BASIC", "EPS_DILUTED"}:
                lowered_label = raw_label.lower()
                if re.search(
                    r"\b(?:calculated|required by|weighted average|number of shares|"
                    r"ordinary shares in issue|issued shares|share capital)\b",
                    line.text,
                    re.I,
                ):
                    continue
                if _is_notes_heading(page) and not _is_statement_page(page, "FLOW"):
                    continue
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
                    ) and not _page_has_eps(page):
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
                label_unresolved = True
                continue
            token, raw_value, column_confidence, graph = selected
            if rule.code in {"EPS_BASIC", "EPS_DILUTED"} and _looks_like_share_count(raw_value):
                continue
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
            if rule.code in STOCK_CORE:
                if page.number not in identity_by_page:
                    identity_by_page[page.number] = _page_stock_identity(page, entity, period_end)
                if identity_by_page[page.number]:
                    score += 0.18
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
    return candidates, found_outside_quarter, found_wrong_scope, label_unresolved


def _looks_like_share_count(value: Decimal) -> bool:
    """True for issued-share / share-capital magnitudes, not plausible EPS."""

    magnitude = abs(value)
    if magnitude >= 10_000:
        return True
    return magnitude >= 1000 and value == value.to_integral()


def _usable_eps(
    fact: ExtractedFact | None,
    *,
    navps: ExtractedFact | None = None,
) -> bool:
    if fact is None or fact.status not in {"EXTRACTED", "LOW_CERTAINTY"}:
        return False
    if fact.normalized_value is None or fact.metric_type != "MONETARY_PER_SHARE":
        return False
    if fact.scale_factor not in {None, 1}:
        return False
    if _looks_like_share_count(fact.normalized_value):
        return False
    implausible_vs_navps = (
        navps is not None
        and navps.status in {"EXTRACTED", "EXTRACTED_DERIVED", "LOW_CERTAINTY"}
        and navps.normalized_value is not None
        and abs(navps.normalized_value) > 0
        and abs(fact.normalized_value) > abs(navps.normalized_value) * Decimal("50")
    )
    return not implausible_vs_navps


def _drop_unreconciled_overlay_equity(
    facts: list[ExtractedFact], entity: str
) -> list[ExtractedFact]:
    """If a tiny equity overlay breaks A ≈ E + L, prefer a miss over the overlay."""

    by_code = facts_by_code(facts)
    assets = by_code.get("TOTAL_ASSETS")
    equity = by_code.get("TOTAL_EQUITY")
    liabilities = by_code.get("TOTAL_LIABILITIES")
    published = {"EXTRACTED", "EXTRACTED_DERIVED"}
    if (
        assets is None
        or equity is None
        or liabilities is None
        or assets.status not in published
        or equity.status not in published
        or liabilities.status not in published
        or assets.raw_value is None
        or equity.raw_value is None
        or liabilities.raw_value is None
        or assets.source_page != equity.source_page
    ):
        return facts
    difference = abs(assets.raw_value - liabilities.raw_value - equity.raw_value)
    if difference <= max(abs(assets.raw_value) * Decimal("0.02"), Decimal("1")):
        return facts
    if abs(equity.raw_value) >= abs(assets.raw_value) * Decimal("0.05"):
        return facts
    rule = next(item for item in METRIC_RULES if item.code == "TOTAL_EQUITY")
    replacement = _missing_fact(
        equity.issuer_name,
        equity.symbol,
        equity.period_end,
        rule,
        entity,
        "VALUE_CONTEXT_UNRESOLVED",
        page_number=equity.source_page,
        source_line=equity.source_line,
    )
    return [fact for fact in facts if fact.metric_code != "TOTAL_EQUITY"] + [replacement]


def _selected_eps_fact(
    issuer_name: str,
    symbol: str,
    period_end: date,
    entity: str,
    *,
    diluted: ExtractedFact | None,
    basic: ExtractedFact | None,
    navps: ExtractedFact | None = None,
) -> ExtractedFact:
    """Prefer extracted diluted EPS; otherwise extracted basic. Never copy a miss."""

    selected = (
        diluted
        if _usable_eps(diluted, navps=navps)
        else basic
        if _usable_eps(basic, navps=navps)
        else None
    )
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
    # Prefer "value found but unusable" over pure absence so basic CUMULATIVE_ONLY
    # is not hidden by diluted EXACT_QUARTER_NOT_REPORTED.
    evidence_statuses = (
        "CUMULATIVE_ONLY",
        "UNIT_NOT_RESOLVED",
        "VALUE_CONTEXT_UNRESOLVED",
        "CONSOLIDATED_ONLY",
        "LOW_CERTAINTY",
    )
    absence_statuses = (
        "EXACT_QUARTER_NOT_REPORTED",
        "SOURCE_CONFIRMED_NOT_REPORTED",
        "NOT_FOUND_BY_PARSER",
        "ENTITY_NOT_RESOLVED",
        "NOT_REPORTED",
    )
    preferred = (*evidence_statuses, *absence_statuses)

    def _status_rank(status: str) -> int:
        try:
            return preferred.index(status)
        except ValueError:
            return len(preferred)

    # Prefer basic when it carries evidence of a found value; keep diluted otherwise.
    candidates = [fact for fact in (basic, diluted) if fact is not None]
    if not candidates:
        missing_status = "NOT_FOUND_BY_PARSER"
        selection_source = None
    else:
        evidenced = [
            fact
            for fact in candidates
            if fact.status in evidence_statuses
            or (fact.raw_value is not None and fact.status not in absence_statuses)
        ]
        pool = evidenced or candidates
        # Within the pool, pick the best (lowest) preferred rank; ties prefer basic.
        selection_source = min(pool, key=lambda fact: (_status_rank(fact.status), 0 if fact is basic else 1))
        missing_status = selection_source.status
        if missing_status in {"EXTRACTED", "EXTRACTED_DERIVED", "NOT_REPORTED"}:
            missing_status = next(
                (status for status in preferred if status in {f.status for f in candidates}),
                "NOT_FOUND_BY_PARSER",
            )
    selected_rule = MetricRule("EPS_SELECTED", (), "FLOW", "MONETARY_PER_SHARE")
    missing = _missing_fact(
        issuer_name,
        symbol,
        period_end,
        selected_rule,
        entity,
        missing_status,
        source_line=(
            f"basic={basic.status if basic else None}; diluted={diluted.status if diluted else None}"
        ),
    )
    return replace(
        missing,
        evidence_json=json.dumps(
            {
                "selection_policy": "prefer_evidence_over_absence",
                "selected_status_source": (
                    selection_source.metric_code if selection_source is not None else None
                ),
                "basic_status": basic.status if basic is not None else None,
                "diluted_status": diluted.status if diluted is not None else None,
                "basic_duration_months": basic.duration_months if basic is not None else None,
                "diluted_duration_months": diluted.duration_months if diluted is not None else None,
            },
            separators=(",", ":"),
        ),
    )


def _missing_status_after_search(
    *,
    rule: MetricRule,
    document: DocumentIR,
    entity: str,
    outside_quarter: bool,
    wrong_scope: bool,
    label_unresolved: bool,
    explicit_flow: bool,
    standalone_statement: bool,
) -> str:
    """Map an empty candidate set to a precise missing taxonomy code.

    ``SOURCE_CONFIRMED_NOT_REPORTED`` requires proof of absence: correct statement
    type located for the standalone entity, target period searched (layout + text
    fallback already attempted by the caller), and no publishable metric row.

    Label/column context failure must not be reported as exact-quarter absence:
    ``outside_quarter`` only wins when the label was resolved and values were
    found outside the target quarter duration.
    """

    if label_unresolved:
        return "VALUE_CONTEXT_UNRESOLVED"
    if outside_quarter:
        return "EXACT_QUARTER_NOT_REPORTED"
    if wrong_scope and not standalone_statement:
        return "CONSOLIDATED_ONLY"

    statement_pages = [
        page for page in document.pages if _is_statement_page(page, rule.statement)
    ]
    if not statement_pages:
        return "NOT_FOUND_BY_PARSER"

    standalone_pages = [
        page
        for page in statement_pages
        if _page_title_entity(page) in {entity, "DUAL", None}
        and _page_title_entity(page) != "GROUP"
    ]
    if not standalone_pages and wrong_scope:
        return "CONSOLIDATED_ONLY"
    if not standalone_pages:
        return "ENTITY_NOT_RESOLVED"

    if rule.statement == "FLOW":
        exact_quarter_standalone = any(
            _page_is_exact_quarter(page) and _page_title_entity(page) != "GROUP"
            for page in standalone_pages
        )
        if exact_quarter_standalone and explicit_flow:
            return "SOURCE_CONFIRMED_NOT_REPORTED"
        if explicit_flow and not exact_quarter_standalone:
            return "EXACT_QUARTER_NOT_REPORTED"
        return "NOT_FOUND_BY_PARSER"

    # Stock metrics: only claim source-confirmed absence when an eligible SOFP-like
    # standalone page was searched and the metric aliases were not merely unresolved.
    sofp_like = [
        page
        for page in standalone_pages
        if _is_statement_page(page, "STOCK") or _classify_page_statement(page) == "STOCK"
    ]
    if not sofp_like:
        return "NOT_FOUND_BY_PARSER"
    if label_unresolved:
        return "VALUE_CONTEXT_UNRESOLVED"
    return "SOURCE_CONFIRMED_NOT_REPORTED"


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
    try:
        from cse_financial_etl.documents.document_context import write_document_context

        write_document_context(diagnostics_dir, document)
    except Exception:
        pass
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


def _pdf_page_unsafe_for_standalone(page: PdfPage, entity: str) -> bool:
    """Text has no x-coordinates. Dual or Group-titled pages would pick Group first."""

    if entity not in {"COMPANY", "BANK"}:
        return False
    header = _header_text(page).upper()
    entity_order = _entity_header_order(header)
    if "GROUP" in entity_order and entity in entity_order:
        return True
    title = "\n".join(page.text.splitlines()[:12]).upper()
    group_title = bool(
        re.search(
            r"\b(?:CONSOLIDATED|GROUP)\s+(?:INCOME\s+)?STATEMENTS?\b|"
            r"\b(?:INCOME\s+STATEMENT|STATEMENTS?\s+OF\s+(?:FINANCIAL\s+POSITION|"
            r"COMPREHENSIVE\s+INCOME|PROFIT(?:\s+OR\s+LOSS)?))\s*[-–:]\s*"
            r"(?:CONSOLIDATED|GROUP)\b",
            title,
        )
    )
    standalone_title = bool(re.search(rf"\b{entity}\b", title))
    return group_title and not standalone_title


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
        if _pdf_page_unsafe_for_standalone(page, entity):
            continue
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


def _text_fallback_is_publishable(page: PdfPage, entity: str) -> bool:
    title = "\n".join(page.text.splitlines()[:12]).upper()
    titled = bool(re.search(rf"\b{re.escape(entity)}\b", title))
    return titled and _is_exact_quarter_text(page.text)


_CURRENT_LIAB_TOTAL = re.compile(
    r"^\s*(?:total\s+)?current\s+liabilit(?:y|ies)\b(?!\s+(?:and|&))",
    re.I,
)
_NONCURRENT_LIAB_TOTAL = re.compile(
    r"^\s*(?:total\s+)?non[- ]current\s+liabilit(?:y|ies)\b",
    re.I,
)


def _select_labelled_layout_value(
    page: PageIR,
    pattern: re.Pattern[str],
    entity: str,
    period_end: date,
) -> tuple[LineIR, TokenIR, Decimal, dict[str, Any]] | None:
    rule = MetricRule("TOTAL_LIABILITIES", (), "STOCK", "MONETARY_ABSOLUTE")
    rows = list(_logical_rows(page))
    for index, line in enumerate(rows):
        label = _metric_label(line) or line.text
        if not pattern.search(label):
            continue
        selected = _select_layout_value(page, line, rule, entity, period_end)
        if selected is not None:
            token, value, _column_confidence, graph = selected
            return line, token, value, graph
        if not _is_section_header(label):
            continue
        section_total = _unlabelled_section_total(page, rows, index, entity, period_end)
        if section_total is not None:
            return section_total
    return None


def _unlabelled_section_total(
    page: PageIR,
    rows: list[LineIR],
    header_index: int,
    entity: str,
    period_end: date,
) -> tuple[LineIR, TokenIR, Decimal, dict[str, Any]] | None:
    """Last numeric-only row before the next section or stock total. Never A-E."""

    rule = MetricRule("TOTAL_LIABILITIES", (), "STOCK", "MONETARY_ABSOLUTE")
    last: tuple[LineIR, TokenIR, Decimal, dict[str, Any]] | None = None
    for line in rows[header_index + 1 :]:
        label = (_metric_label(line) or line.text).strip()
        if _blocks_numeric_prefix_merge(label) or _is_section_header(label):
            break
        if re.search(r"[A-Za-z]{3,}", line.text):
            continue
        selected = _select_layout_value(page, line, rule, entity, period_end)
        if selected is None:
            continue
        token, value, _column_confidence, graph = selected
        last = (line, token, value, graph)
    return last


def _assemble_standalone_liabilities(
    document: DocumentIR,
    entity: str,
    period_end: date,
    statement_map: dict[int, str | None],
    issuer_name: str,
    symbol: str,
) -> ExtractedFact | None:
    """Sum printed Company/Bank current + non-current totals. Never Group. Never A-E."""

    if entity not in {"COMPANY", "BANK"}:
        return None
    sofp_pages = [
        page
        for page in document.pages
        if _page_title_entity(page) != "GROUP"
        and _is_sofp_eligible(page, document, statement_map)
    ]
    windows: list[tuple[PageIR, ...]] = [(page,) for page in sofp_pages]
    windows.extend(
        (left, right)
        for left, right in pairwise(sofp_pages)
        if right.number == left.number + 1
    )
    for pages in windows:
        current = None
        noncurrent = None
        current_page = pages[0]
        ncl_page = pages[0]
        for page in pages:
            if current is None:
                hit = _select_labelled_layout_value(page, _CURRENT_LIAB_TOTAL, entity, period_end)
                if hit is not None:
                    current = hit
                    current_page = page
            if noncurrent is None:
                hit = _select_labelled_layout_value(page, _NONCURRENT_LIAB_TOTAL, entity, period_end)
                if hit is not None:
                    noncurrent = hit
                    ncl_page = page
        if current is None or noncurrent is None:
            continue
        current_line, current_token, current_value, current_graph = current
        ncl_line, ncl_token, ncl_value, ncl_graph = noncurrent
        if _graph_parent_kind(current_graph) in {"GROUP", "CONSOLIDATED"}:
            continue
        if _graph_parent_kind(ncl_graph) in {"GROUP", "CONSOLIDATED"}:
            continue
        currency, scale, unit_text, unit_confidence = _unit_for_layout(
            document, current_page, current_line, "MONETARY_ABSOLUTE"
        )
        if currency is None or scale is None:
            continue
        raw_value = current_value + ncl_value
        unit = UnitCandidate(
            unit_text or "", currency, scale, UnitScope.STATEMENT, page=current_page.number
        )
        normalized = normalize_value(
            raw_value, MetricType.MONETARY_ABSOLUTE, [unit]
        ).normalized_value
        overall = min(0.88, 0.70 + unit_confidence * 0.18)
        source_line = f"{compact_line(current_line)} | {compact_line(ncl_line)}"
        evidence = {
            "method": "CURRENT_PLUS_NONCURRENT",
            "entity_parent_kind": entity,
            "current_liabilities": {
                "raw": str(current_value),
                "line": compact_line(current_line),
                "page": current_page.number,
            },
            "noncurrent_liabilities": {
                "raw": str(ncl_value),
                "line": compact_line(ncl_line),
                "page": ncl_page.number,
            },
        }
        return ExtractedFact(
            issuer_name=issuer_name,
            symbol=symbol,
            period_end=period_end,
            metric_code="TOTAL_LIABILITIES",
            metric_type="MONETARY_ABSOLUTE",
            raw_text=f"{current_token.text}+{ncl_token.text}",
            raw_value=raw_value,
            normalized_value=normalized,
            currency=currency,
            scale_factor=scale,
            entity_scope=entity,
            source_page=current_page.number,
            source_line=source_line,
            unit_source_text=unit_text,
            confidence=_certainty_band(overall),
            status="EXTRACTED_DERIVED",
            raw_label="Total current liabilities + Total non-current liabilities",
            source_bbox=_bbox_json(current_token.bbox),
            extraction_method="CURRENT_PLUS_NONCURRENT",
            semantic_model="regex",
            semantic_confidence=0.9,
            entity_confidence=0.94,
            period_confidence=0.94,
            unit_confidence=round(unit_confidence, 4),
            column_confidence=0.9,
            validation_confidence=0.9,
            overall_certainty=round(overall, 4),
            certainty_band=_certainty_band(overall),
            duration_months=None,
            validation_status="PASSED",
            review_status="REVIEW",
            evidence_json=json.dumps(evidence, separators=(",", ":")),
        )
    return None


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
    force_unit_rescan: bool = False,
    prefer_exact_quarter: bool = True,
    prefer_standalone_sofp: bool = False,
) -> list[ExtractedFact]:
    """Extract facts from one filing.

    Retry flags (Phase One retry controller) may change layout/unit interpretation
    but never relax Company/Bank, exact-quarter, or non-zero blank rules.
    """

    document = extract_document_ir(
        pdf_path,
        ocr_dir=text_cache_dir,
        enable_ocr=ocr_enabled,
    )
    entity = entity_scope_for_issuer(issuer_name, issuers)
    facts: list[ExtractedFact] = []
    statement_map = _page_statement_map(document)
    require_exact_quarter = prefer_exact_quarter

    for rule in METRIC_RULES:
        if prefer_standalone_sofp and rule.statement == "STOCK":
            # First pass: only pages whose title is the standalone entity (not DUAL/Group).
            candidates, outside_quarter, wrong_scope, label_unresolved = _layout_candidates(
                document,
                rule,
                entity,
                period_end,
                statement_map=statement_map,
                require_exact_quarter=require_exact_quarter,
            )
            standalone_only = [
                candidate
                for candidate in candidates
                if _page_title_entity(candidate.page) in {entity, None}
                and _page_title_entity(candidate.page) != "GROUP"
            ]
            if standalone_only:
                candidates = standalone_only
            # else keep all candidates — do not invent a miss when dual pages exist
        else:
            candidates, outside_quarter, wrong_scope, label_unresolved = _layout_candidates(
                document,
                rule,
                entity,
                period_end,
                statement_map=statement_map,
                require_exact_quarter=require_exact_quarter,
            )
        cumulative_only = False
        if not candidates and rule.code in {"TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT"}:
            cumulative_candidates, _outside, cumulative_wrong_scope, cumulative_unresolved = (
                _layout_candidates(
                document,
                rule,
                entity,
                period_end,
                require_exact_quarter=False,
                statement_map=statement_map,
                )
            )
            cumulative_candidates = [
                candidate
                for candidate in cumulative_candidates
                if (
                    _page_flow_duration(
                        candidate.page,
                        document_has_quarter_heading=_document_has_quarter_flow_heading(
                            document
                        ),
                    )
                    or 0
                )
                > 3
            ]
            if cumulative_candidates:
                candidates = cumulative_candidates
                cumulative_only = True
            wrong_scope = wrong_scope or cumulative_wrong_scope
            label_unresolved = label_unresolved or cumulative_unresolved
        if not candidates and rule.code in {"EPS_BASIC", "EPS_DILUTED", "NAVPS"}:
            retry, retry_outside, retry_wrong_scope, retry_unresolved = _layout_candidates(
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
            label_unresolved = label_unresolved or retry_unresolved
        if not candidates:
            fallback = _text_fallback_metric(pdf_path, rule, entity, text_cache_dir)
            if fallback is not None:
                page, raw, value, line, currency, scale, unit_text = fallback
                if rule.code in {"EPS_BASIC", "EPS_DILUTED"} and _looks_like_share_count(value):
                    fallback = None
            if fallback is not None:
                page, raw, value, line, currency, scale, unit_text = fallback
                publishable = _text_fallback_is_publishable(page, entity)
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
                overall = 0.82 if publishable and status == "EXTRACTED" else 0.72
                if status == "EXTRACTED" and overall < manual_review_threshold:
                    status = "LOW_CERTAINTY"
                text_duration = (
                    _duration_months(page.text) if rule.statement == "FLOW" else None
                )
                if rule.statement == "FLOW" and text_duration in {6, 9, 12}:
                    status = "CUMULATIVE_ONLY"
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
                        duration_months=(
                            text_duration
                            if rule.statement == "FLOW" and text_duration is not None
                            else (3 if rule.statement == "FLOW" else None)
                        ),
                        validation_status="PASSED" if status == "EXTRACTED" else "REVIEW",
                        review_status="REVIEW",
                    )
                )
                continue
            explicit_flow = any(
                _is_statement_page(page, "FLOW") and _page_title_entity(page) != "GROUP"
                for page in document.pages
            )
            standalone_statement = any(
                _page_title_entity(page) in {entity, "DUAL"}
                or (
                    _page_title_entity(page) is None
                    and _is_statement_page(page, rule.statement)
                )
                for page in document.pages
            )
            status = _missing_status_after_search(
                rule=rule,
                document=document,
                entity=entity,
                outside_quarter=outside_quarter,
                wrong_scope=wrong_scope,
                label_unresolved=label_unresolved,
                explicit_flow=explicit_flow,
                standalone_statement=standalone_statement,
            )
            facts.append(_missing_fact(issuer_name, symbol, period_end, rule, entity, status))
            continue

        def _top_line_rank(
            candidate: _LayoutCandidate, *, _code: str = rule.code
        ) -> tuple[float, int]:
            label = (candidate.raw_label or "").strip().lower()
            exact_boost = 0.0
            if _code == "TOP_LINE" and label == "income":
                # Finance packs often print gross "Income" above Net interest income.
                exact_boost = 0.12
            return (candidate.candidate_score + exact_boost, -candidate.page.number)

        candidates.sort(key=_top_line_rank, reverse=True)
        selected = candidates[0]
        currency, scale, unit_text, unit_confidence = _unit_for_layout(
            document,
            selected.page,
            selected.line,
            rule.metric_type,
            force_rescan=force_unit_rescan,
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
        comparison_role, header_year = _comparison_from_layout(
            selected.page, selected.line, selected.token, period_end
        )
        column_duration = (
            _column_duration_months(
                selected.page,
                selected.line,
                selected.token,
                period_end,
                document_has_quarter_heading=_document_has_quarter_flow_heading(document),
            )
            if rule.statement == "FLOW"
            else None
        )
        evidence = {
            "selected_line": compact_line(selected.line),
            "graph": stored_graph,
            "source_header_year": header_year,
            "comparison_role": comparison_role,
            "duration_months": column_duration,
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
            "entity_parent_kind": _graph_parent_kind(selected.graph),
        }
        flow_duration = column_duration
        if cumulative_only and rule.statement == "FLOW":
            # Cumulative-only path: keep real duration, never pretend it is 3M.
            if flow_duration not in {6, 9, 12}:
                flow_duration = (
                    _page_flow_duration(
                        selected.page,
                        document_has_quarter_heading=_document_has_quarter_flow_heading(
                            document
                        ),
                    )
                    or _duration_months(selected.page.text)
                    or 6
                )
            evidence["duration_months"] = flow_duration
        elif rule.statement == "FLOW":
            # Column binding wins over page-level FY cues (Hayleys Fibre).
            if flow_duration == 3:
                evidence["duration_months"] = 3
            elif flow_duration in {6, 9, 12}:
                status = "CUMULATIVE_ONLY"
                review_status = "REVIEW"
                evidence["duration_months"] = flow_duration
            elif flow_duration is None:
                flow_duration = 3 if not cumulative_only else 6
                evidence["duration_months"] = flow_duration
            else:
                evidence["duration_months"] = flow_duration
        if status == "EXTRACTED" and comparison_role != "CURRENT":
            status = "VALUE_CONTEXT_UNRESOLVED"
            review_status = "REVIEW"
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
                comparison_role=comparison_role,
                duration_months=flow_duration if rule.statement == "FLOW" else None,
                validation_status="PASSED" if status == "EXTRACTED" else "REVIEW",
                review_status=review_status,
                evidence_json=json.dumps(evidence, separators=(",", ":")),
            )
        )

    # Contract: do not publish Assets-Equity or assembled current+non-current
    # liabilities without an explicit Total Liabilities source row.
    # `_assemble_standalone_liabilities` remains available for diagnostics only.
    facts = _drop_unreconciled_overlay_equity(facts, entity)
    fact_map = facts_by_code(facts)

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
            navps=fact_map.get("NAVPS"),
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
                or re.search(r"\bclosing\s+(?:share|market)?\s*price\b", lowered)
                or re.search(r"\bmarket\s+price\s+as\s+at\b", lowered)
                or re.search(r"\bmarket\s+price\s+per\s+share\b", lowered)
                or re.search(r"\bhighest\b.+\blowest\b.+\blast\s+traded\b", lowered)
                or (section_present and re.match(r"^\s*closing\b", lowered))
                or (section_present and re.match(r"^\s*share\s+price\b", lowered))
                or (section_present and re.match(r"^\s*last\s+traded\b", lowered))
                or (
                    section_present
                    and re.match(r"^\s*(?:period|quarter|year)\s+end(?:ed)?\b", lowered)
                )
            )
            if not price_label and not (
                re.match(r"^\s*(?:non[- ]?voting|voting)\b", lowered)
                and any(
                    term in local_context
                    for term in ("price per share", "last traded", "market price", "closing price")
                )
            ):
                continue
            # Section titles ("8.5 ... Highest, Lowest and Last Traded ... given below")
            # are not value rows.
            if re.search(r"\bgiven below\b|\bshown below\b|\bas follows\b", lowered):
                continue
            if re.match(r"^\s*\d+(?:\.\d+)?\s+\S+", lowered) and re.search(
                r"\bhighest\b.+\blowest\b.+\blast\s+traded\b", lowered
            ):
                continue
            numeric: list[tuple[TokenIR, Decimal]] = []
            has_month = bool(
                re.search(
                    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|"
                    r"july?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
                    r"dec(?:ember)?)\b",
                    lowered,
                )
            )
            for token in line.numeric_tokens:
                value = _decimal(token.text)
                if value is None:
                    continue
                if value == value.to_integral() and 1900 <= abs(value) <= 2100:
                    continue
                if has_month and value == value.to_integral() and 1 <= abs(value) <= 31:
                    continue
                if abs(value) > 100_000:
                    continue
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
            # Single row with Highest / Lowest / Last traded: take last-traded (3rd).
            # Pure "Last traded current comparative" rows: take current (1st).
            if (
                re.search(r"\bhighest\b.+\blowest\b.+\blast\s+traded\b", lowered)
                and len(numeric) >= 3
            ):
                token, value = numeric[-1]
            else:
                token, value = numeric[0]
            if re.match(r"^\s*non[- ]?voting\b", lowered):
                class_values.setdefault("X", (page, line, value, token))
            elif re.match(r"^\s*voting\b", lowered):
                class_values.setdefault("N", (page, line, value, token))
            else:
                score = 0.78
                if "last traded" in lowered:
                    score += 0.15
                if "highest" in lowered and "lowest" in lowered:
                    score += 0.05
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
