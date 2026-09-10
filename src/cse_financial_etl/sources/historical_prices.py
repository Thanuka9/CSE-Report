from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _snapshot_date(path: Path) -> date | None:
    if path.parent.name.startswith("date="):
        try:
            return date.fromisoformat(path.parent.name.removeprefix("date="))
        except ValueError:
            return None
    stem = path.stem
    for prefix in ("historical_", "market_cap_"):
        if stem.startswith(prefix):
            try:
                return date.fromisoformat(stem.removeprefix(prefix)[:10])
            except ValueError:
                return None
    return None


def _rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() != ".json":
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "data", "prices", "history"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _last_traded_price(row: dict[str, Any]) -> Decimal | None:
    """Read only fields that can represent an actual last-traded/trade price.

    Generic closing-price fields are intentionally excluded because a CSE filing may
    report both closing market price and last traded price with different values.
    """

    for key in ("last_traded_price", "last_trade_price", "trade_price", "price"):
        raw = row.get(key)
        if raw in (None, ""):
            continue
        try:
            value = Decimal(str(raw).replace(",", ""))
        except (InvalidOperation, ValueError):
            continue
        if value > 0:
            return value
    return None


def resolve_quarter_end_price(
    project_root: Path,
    symbol: str,
    period_end: date,
) -> tuple[Decimal, date, str] | None:
    """Resolve last-traded price from explicit stored CSE historical evidence only.

    A live market-cap snapshot is not historical evidence and is never used here.  The
    returned date is an actual row trade/observation date when present, otherwise the
    explicit historical-file observation date.  It is never labelled as a trade date
    merely because a cache file happened to be written on that date.
    """

    official_dir = project_root / "data" / "raw" / "market" / "historical_prices"
    if not official_dir.exists():
        return None

    candidates: list[tuple[date, float, Decimal]] = []
    for path in official_dir.rglob("*.json"):
        file_date = _snapshot_date(path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        for row in _rows(path):
            if str(row.get("symbol") or "").strip().upper() != symbol.strip().upper():
                continue
            observed = (
                _parse_date(row.get("trade_date"))
                or _parse_date(row.get("date"))
                or _parse_date(row.get("observation_date"))
                or file_date
            )
            if observed is None or observed > period_end:
                continue
            value = _last_traded_price(row)
            if value is not None:
                candidates.append((observed, mtime, value))

    if not candidates:
        return None
    observed, _mtime, value = max(candidates, key=lambda item: (item[0], item[1]))
    return value, observed, "CSE_HISTORICAL_LAST_TRADED"
