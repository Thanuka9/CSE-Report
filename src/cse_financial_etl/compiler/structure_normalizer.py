"""Normalization layers before target fact selection (§8).

All matching here is bounded (word boundaries): ``rs`` inside ``Shareholders`` is
never a currency, ``000`` inside ``1,000,000`` is never a scale word.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

_PAREN_RE = re.compile(r"^\((.+)\)$")
_WS_NUM_RE = re.compile(r"(?<=\d)\s+(?=\d)")

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
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_LONG_DATE_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s,.-]*({_MONTH_ALT})\.?[\s,.-]*((?:19|20)\d{{2}})\b",
    re.I,
)
_MONTH_FIRST_DATE_RE = re.compile(
    rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{{2}})\b",
    re.I,
)
_DAY_MONTH_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s,.-]*({_MONTH_ALT})\b\.?(?!\s*(?:19|20)\d{{2}})", re.I
)
_NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-]((?:19|20)\d{2}|\d{2})\b")
_ISO_DATE_RE = re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b")
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_CURRENCY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "LKR",
        re.compile(
            r"(?<![a-z])(?:rs|lkr|slr)(?![a-z])\.?|\brupees?\b|\bsri\s+lankan?\s+rupees?\b", re.I
        ),
    ),
    ("USD", re.compile(r"(?<![a-z])(?:usd|us\$|us\s+dollars?)(?![a-z])|(?<![a-z])\$", re.I)),
    ("EUR", re.compile(r"(?<![a-z])eur(?![a-z])|€", re.I)),
    ("GBP", re.compile(r"(?<![a-z])gbp(?![a-z])|£", re.I)),
)
_SCALE_PATTERNS: tuple[tuple[Decimal, re.Pattern[str]], ...] = (
    (Decimal("1000000000"), re.compile(r"(?<![a-z])(?:bn|billions?)(?![a-z])", re.I)),
    (Decimal("1000000"), re.compile(r"(?<![a-z])(?:mn|mio|millions?)(?![a-z])", re.I)),
    (
        Decimal("1000"),
        re.compile(
            r"(?:(?<![a-z])(?:rs|lkr)\.?\s*0{3}s?(?!\d)|"
            r"['’‘]\s?0{3}s?(?!\d)|(?<![\d,.])0{3}s?(?![\d,])|"
            r"(?<![a-z])thousands?(?![a-z]))",
            re.I,
        ),
    ),
)
_PER_SHARE_RE = re.compile(r"\bper\s+(?:ordinary\s+)?share\b|\bcents?\b", re.I)
_CENTS_RE = re.compile(r"\bcents?\b", re.I)


def normalize_search_text(raw: str) -> str:
    return " ".join(raw.lower().replace("'", "").replace("'", "").split())


def parse_numeric(raw_text: str) -> Decimal | None:
    text = raw_text.strip()
    if not text or text in {"-", "–", "—", "‑", "−", "n/a", "N/A", "nil", "Nil"}:
        return None  # dash is not zero without established convention
    negative = False
    if _PAREN_RE.match(text):
        negative = True
        text = _PAREN_RE.match(text).group(1)  # type: ignore[union-attr]
    text = text.strip()
    if text.endswith("-"):
        negative = True
        text = text[:-1]
    if text.startswith("-") or text.startswith("−"):
        negative = True
        text = text[1:]
    text = _WS_NUM_RE.sub("", text).replace(",", "").replace("%", "").strip()
    if not text or not re.fullmatch(r"\d+(?:\.\d+)?|\.\d+", text):
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return -value if negative else value


def normalize_duration_phrase(text: str) -> int | None:
    """Return months for a duration phrase; ``None`` when absent or 'period ended' only."""

    lower = " ".join(text.lower().split())
    if re.search(r"\b(?:three|3)\s*months?\b|\bquarter\b|\b1st\s+quarter\b|\bq[1-4]\b", lower):
        return 3
    if re.search(r"\b(?:six|6)\s*months?\b|\bhalf\s*year\b", lower):
        return 6
    if re.search(r"\b(?:nine|9)\s*months?\b", lower):
        return 9
    if re.search(
        r"\b(?:twelve|12)\s*months?\b|\byear\s+(?:ended|ending|to)\b|\bfy\b|\bfinancial\s+year\b",
        lower,
    ):
        return 12
    return None


def is_instant_phrase(text: str) -> bool:
    return re.search(r"\bas\s+at\b|\bas\s+of\b", text.lower()) is not None


def normalize_date(text: str) -> date | None:
    """Parse an explicit full date (day, month and year all present)."""

    cleaned = " ".join(text.strip().replace(",", " ").split())
    match = _ISO_DATE_RE.search(cleaned)
    if match:
        return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = _LONG_DATE_RE.search(cleaned)
    if match:
        return _safe_date(int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1)))
    match = _MONTH_FIRST_DATE_RE.search(cleaned)
    if match:
        return _safe_date(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)))
    match = _NUMERIC_DATE_RE.search(cleaned)
    if match:
        first, second, year_s = int(match.group(1)), int(match.group(2)), match.group(3)
        year = int(year_s) if len(year_s) == 4 else 2000 + int(year_s)
        # Sri Lankan convention is day/month; an impossible month means month/day.
        if second > 12 and first <= 12:
            return _safe_date(year, first, second)
        return _safe_date(year, second, first)
    return None


def parse_day_month(text: str) -> tuple[int, int] | None:
    """Return (day, month) for phrases like ``ended 30 June`` (year absent)."""

    cleaned = " ".join(text.strip().replace(",", " ").split())
    match = _DAY_MONTH_RE.search(cleaned)
    if match:
        return int(match.group(1)), _MONTHS[match.group(2).lower()]
    return None


def parse_year(text: str) -> int | None:
    match = _YEAR_RE.search(text)
    return int(match.group(1)) if match else None


def compose_date(year: int, month: int, day: int) -> date | None:
    return _safe_date(year, month, day)


def _safe_date(year: int, month: int, day: int) -> date | None:
    if not 1 <= month <= 12:
        return None
    last = calendar.monthrange(year, month)[1]
    if day > last:
        day = last  # "31 June" style typos clamp to month end, never to another month
    if day < 1:
        return None
    return date(year, month, day)


@dataclass(frozen=True, slots=True)
class ParsedUnit:
    currency: str | None
    scale: Decimal | None
    scale_explicit: bool
    per_share: bool
    percent: bool
    text: str

    @property
    def is_empty(self) -> bool:
        return (
            self.currency is None and self.scale is None and not self.per_share and not self.percent
        )


def parse_unit_text(text: str) -> ParsedUnit:
    """Bounded unit parsing: currency and scale are independent dimensions."""

    lower = " ".join(text.lower().split())
    currency: str | None = None
    for code, pattern in _CURRENCY_PATTERNS:
        if pattern.search(lower):
            currency = code
            break
    scale: Decimal | None = None
    explicit = False
    for factor, pattern in _SCALE_PATTERNS:
        if pattern.search(lower):
            scale = factor
            explicit = True
            break
    per_share = bool(_PER_SHARE_RE.search(lower))
    if _CENTS_RE.search(lower):
        scale = Decimal("0.01")
        explicit = True
        per_share = True
    percent = "%" in lower or bool(re.search(r"\bpercent(?:age)?\b", lower))
    if scale is None and currency is not None and not percent:
        scale = Decimal("1")  # bare currency means whole units of that currency
    return ParsedUnit(
        currency=currency,
        scale=scale,
        scale_explicit=explicit,
        per_share=per_share,
        percent=percent,
        text=text.strip(),
    )


def normalize_unit_declaration(text: str) -> tuple[str | None, Decimal | None]:
    """Backward compatible (currency, scale) view of :func:`parse_unit_text`."""

    parsed = parse_unit_text(text)
    if parsed.percent and parsed.currency is None:
        return None, None
    return parsed.currency, parsed.scale


def normalize_entity_term(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"\b(?:group|consolidated)\b", lower):
        return "GROUP"
    if re.search(r"\bbank\b", lower):
        return "BANK"
    if re.search(r"\b(?:company|separate)\b", lower):
        return "COMPANY"
    return None
