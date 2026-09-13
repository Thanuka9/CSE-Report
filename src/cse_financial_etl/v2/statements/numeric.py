"""Parse source numbers without float. Blank dashes are missing, not zero."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NUMERIC_TOKEN = re.compile(r"^\(?-?\d[\d,]*(?:\.\d+)?\)?%?$|^[-–—−]$")
_EMBEDDED_NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")


def is_numeric_token(text: str) -> bool:
    return _NUMERIC_TOKEN.fullmatch(text.strip()) is not None


def parse_numeric(text: str) -> Decimal | None:
    raw = text.strip()
    if not raw or raw in {"-", "–", "—", "−", "n/a", "N/A", "NA"}:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = raw.strip("()").replace(",", "").replace("%", "").strip()
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -value if negative else value


def split_label_and_values(text: str) -> tuple[str, tuple[str, ...]]:
    """Split a concatenated row into a label and trailing numeric cells."""

    matches = list(_EMBEDDED_NUMBER.finditer(text))
    if not matches:
        return text.strip(), ()
    first = matches[0]
    # Values are trailing numbers; keep the prefix as the row label.
    label = text[: first.start()].strip(" \t:-")
    values = tuple(match.group(0) for match in matches)
    if not label:
        return text.strip(), ()
    return label, values
