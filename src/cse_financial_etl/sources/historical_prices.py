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


def _positive_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed > 0 else None


def _last_traded_price(row: dict[str, Any]) -> Decimal | None:
    """Read fields that can represent an actual last-traded/trade price."""

    for key in ("last_traded_price", "last_trade_price", "trade_price", "price"):
        value = _positive_decimal(row.get(key))
        if value is not None:
            return value
    return None


def _official_historical_price(
    project_root: Path,
    symbol: str,
    period_end: date,
) -> tuple[Decimal, date, str] | None:
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


def _legacy_snapshot_price(
    project_root: Path,
    symbol: str,
    period_end: date,
) -> tuple[Decimal, date, str] | None:
    """Compatibility fallback for non-governed callers and historical tests.

    This reads only snapshots dated on or before the requested period. A snapshot dated
    after period end can never leak into the result. Governed R4 production does not use
    this fallback: it monkey-patches the pipeline resolver with the strict last-traded
    history implementation in ``production.r4_hardening``.
    """

    api_dir = project_root / "data" / "raw" / "api"
    if not api_dir.exists():
        return None

    candidates: list[tuple[date, float, Decimal]] = []
    paths = [*api_dir.glob("market_cap_*.json")]
    history_dir = api_dir / "history"
    if history_dir.exists():
        paths.extend(history_dir.glob("market_cap_*.json"))

    for path in paths:
        snapshot_date = _snapshot_date(path)
        if snapshot_date is None or snapshot_date > period_end:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        for row in _rows(path):
            if str(row.get("symbol") or "").strip().upper() != symbol.strip().upper():
                continue
            value = _positive_decimal(row.get("price"))
            if value is not None:
                candidates.append((snapshot_date, mtime, value))

    if not candidates:
        return None
    snapshot_date, _mtime, value = max(candidates, key=lambda item: (item[0], item[1]))
    return value, snapshot_date, "LAST_TRADE_ON_OR_BEFORE_QUARTER_END"


def resolve_quarter_end_price(
    project_root: Path,
    symbol: str,
    period_end: date,
) -> tuple[Decimal, date, str] | None:
    """Resolve quarter-end price without allowing a future snapshot to leak backward.

    Explicit historical trade evidence is preferred. The legacy dated-snapshot fallback
    remains for backwards-compatible non-governed callers. R4 production replaces this
    callable at runtime with a strict last-traded-only resolver.
    """

    official = _official_historical_price(project_root, symbol, period_end)
    if official is not None:
        return official
    return _legacy_snapshot_price(project_root, symbol, period_end)
