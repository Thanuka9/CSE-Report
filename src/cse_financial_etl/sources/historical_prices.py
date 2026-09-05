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
    if stem.startswith("market_cap_"):
        try:
            return date.fromisoformat(stem.removeprefix("market_cap_")[:10])
        except ValueError:
            return None
    if stem.startswith("historical_"):
        try:
            return date.fromisoformat(stem.removeprefix("historical_")[:10])
        except ValueError:
            return None
    return None


def _rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    return []


def _price(row: dict[str, Any]) -> Decimal | None:
    raw = row.get("price")
    if raw in (None, ""):
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return value if value > 0 else None


def resolve_quarter_end_price(
    project_root: Path,
    symbol: str,
    period_end: date,
) -> tuple[Decimal, date, str] | None:
    """Official CSE history, else last stored trade on or before quarter end.

    Never uses a live market snapshot dated after the target quarter end.
    """

    candidates: list[tuple[date, float, Path, str]] = []

    def consider(path: Path, method: str) -> None:
        snapshot_date = _snapshot_date(path)
        if snapshot_date is None or snapshot_date > period_end:
            return
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        candidates.append((snapshot_date, mtime, path, method))

    api_dir = project_root / "data" / "raw" / "api"
    if api_dir.exists():
        for path in api_dir.glob("market_cap_*.json"):
            consider(path, "LAST_TRADE_ON_OR_BEFORE_QUARTER_END")
    history_dir = api_dir / "history"
    if history_dir.exists():
        for path in history_dir.glob("market_cap_*.json"):
            consider(path, "LAST_TRADE_ON_OR_BEFORE_QUARTER_END")
    official_dir = project_root / "data" / "raw" / "market" / "historical_prices"
    if official_dir.exists():
        for path in official_dir.glob("*.json"):
            consider(path, "CSE_HISTORICAL")

    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda item: (item[3] == "CSE_HISTORICAL", item[0], item[1]))
    for snapshot_date, _mtime, path, method in reversed(ranked):
        for row in _rows(path):
            if row.get("symbol") == symbol:
                value = _price(row)
                if value is not None:
                    return value, snapshot_date, method
    return None
