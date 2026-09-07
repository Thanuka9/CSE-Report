"""Normalization layers before target fact selection (§8)."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_PAREN_RE = re.compile(r"^\((.+)\)$")
_WS_NUM_RE = re.compile(r"(?<=\d)\s+(?=\d)")


def normalize_search_text(raw: str) -> str:
    return " ".join(raw.lower().replace("'", "").replace("'", "").split())


def parse_numeric(raw_text: str) -> Decimal | None:
    text = raw_text.strip()
    if not text or text in {"-", "–", "—", "n/a", "N/A"}:
        return None  # dash is not zero without established convention
    negative = False
    if _PAREN_RE.match(text):
        negative = True
        text = _PAREN_RE.match(text).group(1)  # type: ignore[union-attr]
    if text.endswith("-"):
        negative = True
        text = text[:-1]
    if text.startswith("-") or text.startswith("−"):
        negative = True
        text = text[1:]
    text = _WS_NUM_RE.sub("", text).replace(",", "").replace("%", "")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return -value if negative else value


def normalize_duration_phrase(text: str) -> int | None:
    lower = text.lower()
    if re.search(r"three months|3 months|for the quarter|quarter ended", lower):
        return 3
    if re.search(r"six months|6 months", lower):
        return 6
    if re.search(r"nine months|9 months", lower):
        return 9
    if re.search(r"twelve months|12 months|year ended|\bfy\b", lower):
        return 12
    return None


def normalize_date(text: str) -> date | None:
    cleaned = text.strip().replace(",", " ")
    for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def normalize_unit_declaration(text: str) -> tuple[str | None, Decimal | None]:
    lower = text.lower().replace("'", "")
    currency = "LKR" if any(k in lower for k in ("rs", "lkr", "rupee")) else None
    scale: Decimal | None = None
    if re.search(r"mn|million", lower):
        scale = Decimal("1000000")
    elif re.search(r"bn|billion", lower):
        scale = Decimal("1000000000")
    elif re.search(r"000|thousand", lower):
        scale = Decimal("1000")
    elif currency:
        scale = Decimal("1")
    return currency, scale


def normalize_entity_term(text: str) -> str | None:
    lower = text.lower()
    if "group" in lower or "consolidated" in lower:
        return "GROUP"
    if "bank" in lower:
        return "BANK"
    if "company" in lower or "separate" in lower:
        return "COMPANY"
    return None
