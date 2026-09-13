"""Detect unauthorized coverage-floor reductions.

Normal implementation changes may keep or raise floors. They may not lower them.
Lowering requires a separate governed record with ACKNOWLEDGED_REGRESSION.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cse_financial_etl.v2.exceptions import UnauthorizedCoverageFloorReduction
from cse_financial_etl.v2.governance.historical_floors import (
    HISTORICAL_MIN_PUBLISHABLE_BY_METRIC,
    HISTORICAL_MIN_PUBLISHABLE_BY_SECTOR_METRIC,
    HISTORICAL_SCALAR_MAXES,
    HISTORICAL_SCALAR_MINS,
    SCALAR_MAX_KEYS,
    SCALAR_MIN_KEYS,
)

REQUIRED_GOVERNANCE_FIELDS: tuple[str, ...] = (
    "old_value",
    "new_value",
    "affected_metrics",
    "affected_sectors",
    "reason",
    "incident_id",
    "source_snapshot_id",
    "reference_run_id",
    "new_run_id",
    "code_sha",
    "evidence",
    "ACKNOWLEDGED_REGRESSION",
    "approver",
)


@dataclass(frozen=True, slots=True)
class FloorReduction:
    path: str
    old_value: int
    new_value: int
    kind: str  # MIN_LOWERED | MAX_RAISED | KEY_REMOVED


@dataclass(frozen=True, slots=True)
class FloorCheckReport:
    reductions: tuple[FloorReduction, ...]
    unauthorized: tuple[FloorReduction, ...]
    authorized: tuple[FloorReduction, ...]

    @property
    def ok(self) -> bool:
        return not self.unauthorized


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return loaded


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _collect_reductions(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[FloorReduction]:
    reductions: list[FloorReduction] = []
    for key in SCALAR_MIN_KEYS:
        old_value = _as_int(old.get(key))
        new_value = _as_int(new.get(key))
        if old_value is None:
            continue
        if new_value is None:
            reductions.append(FloorReduction(key, old_value, 0, "KEY_REMOVED"))
        elif new_value < old_value:
            reductions.append(FloorReduction(key, old_value, new_value, "MIN_LOWERED"))
    for key in SCALAR_MAX_KEYS:
        old_value = _as_int(old.get(key))
        new_value = _as_int(new.get(key))
        if old_value is None:
            continue
        if new_value is None:
            reductions.append(FloorReduction(key, old_value, old_value, "KEY_REMOVED"))
        elif new_value > old_value:
            reductions.append(FloorReduction(key, old_value, new_value, "MAX_RAISED"))
    old_metrics = old.get("min_publishable_by_metric") or {}
    new_metrics = new.get("min_publishable_by_metric") or {}
    if isinstance(old_metrics, Mapping):
        new_metric_map = new_metrics if isinstance(new_metrics, Mapping) else {}
        for metric, raw in old_metrics.items():
            old_value = _as_int(raw)
            if old_value is None:
                continue
            path = f"min_publishable_by_metric.{metric}"
            new_value = _as_int(new_metric_map.get(metric))
            if new_value is None:
                reductions.append(FloorReduction(path, old_value, 0, "KEY_REMOVED"))
            elif new_value < old_value:
                reductions.append(FloorReduction(path, old_value, new_value, "MIN_LOWERED"))
    old_sector = old.get("min_publishable_by_sector_metric") or {}
    new_sector = new.get("min_publishable_by_sector_metric") or {}
    if isinstance(old_sector, Mapping):
        new_sector_map = new_sector if isinstance(new_sector, Mapping) else {}
        for sector, metrics in old_sector.items():
            if not isinstance(metrics, Mapping):
                continue
            new_metrics_for_sector = (
                new_sector_map.get(sector) if isinstance(new_sector_map, Mapping) else None
            )
            new_metrics_map = (
                new_metrics_for_sector if isinstance(new_metrics_for_sector, Mapping) else {}
            )
            for metric, raw in metrics.items():
                old_value = _as_int(raw)
                if old_value is None:
                    continue
                path = f"min_publishable_by_sector_metric.{sector}.{metric}"
                new_value = _as_int(new_metrics_map.get(metric))
                if new_value is None:
                    reductions.append(FloorReduction(path, old_value, 0, "KEY_REMOVED"))
                elif new_value < old_value:
                    reductions.append(FloorReduction(path, old_value, new_value, "MIN_LOWERED"))
    return reductions


def historical_lock_payload() -> dict[str, Any]:
    return {
        **HISTORICAL_SCALAR_MINS,
        **HISTORICAL_SCALAR_MAXES,
        "min_publishable_by_metric": dict(HISTORICAL_MIN_PUBLISHABLE_BY_METRIC),
        "min_publishable_by_sector_metric": {
            sector: dict(metrics)
            for sector, metrics in HISTORICAL_MIN_PUBLISHABLE_BY_SECTOR_METRIC.items()
        },
    }


def governance_authorizes(record: Mapping[str, Any] | None, reduction: FloorReduction) -> bool:
    if not record:
        return False
    if any(field not in record for field in REQUIRED_GOVERNANCE_FIELDS):
        return False
    acknowledged = record.get("ACKNOWLEDGED_REGRESSION")
    if acknowledged is not True and str(acknowledged).strip().upper() not in {"TRUE", "YES", "1"}:
        return False
    if not str(record.get("approver") or "").strip():
        return False
    try:
        if int(record["old_value"]) != reduction.old_value:
            return False
        if int(record["new_value"]) != reduction.new_value:
            return False
    except (TypeError, ValueError):
        return False
    path = str(record.get("path") or "").strip()
    return path == "" or path == reduction.path


def _load_governance_records(raw: object) -> list[Mapping[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, Mapping) and "exceptions" in raw:
        raw = raw["exceptions"]
    if isinstance(raw, Mapping):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, Mapping)]
    return []


def evaluate_coverage_floors(
    *,
    current: Mapping[str, Any],
    previous: Mapping[str, Any] | None = None,
    historical: Mapping[str, Any] | None = None,
    governance: object | None = None,
) -> FloorCheckReport:
    lock = historical if historical is not None else historical_lock_payload()
    records = _load_governance_records(governance)
    reductions = _collect_reductions(lock, current)
    if previous is not None:
        seen = {item.path: item for item in reductions}
        for item in _collect_reductions(previous, current):
            seen[item.path] = item
        reductions = list(seen.values())
    authorized: list[FloorReduction] = []
    unauthorized: list[FloorReduction] = []
    for reduction in reductions:
        if any(governance_authorizes(record, reduction) for record in records):
            authorized.append(reduction)
        else:
            unauthorized.append(reduction)
    return FloorCheckReport(
        reductions=tuple(reductions),
        unauthorized=tuple(unauthorized),
        authorized=tuple(authorized),
    )


def assert_coverage_floors_not_lowered(
    *,
    current: Mapping[str, Any],
    previous: Mapping[str, Any] | None = None,
    historical: Mapping[str, Any] | None = None,
    governance: object | None = None,
) -> FloorCheckReport:
    report = evaluate_coverage_floors(
        current=current,
        previous=previous,
        historical=historical,
        governance=governance,
    )
    if not report.ok:
        details = "; ".join(
            f"{item.path}: {item.old_value} -> {item.new_value} ({item.kind})"
            for item in report.unauthorized
        )
        raise UnauthorizedCoverageFloorReduction(
            "unauthorized coverage floor reduction: " + details
        )
    return report


def check_baseline_files(
    *,
    current_path: Path,
    previous_path: Path | None = None,
    governance_path: Path | None = None,
) -> FloorCheckReport:
    current = load_yaml_mapping(current_path)
    previous = load_yaml_mapping(previous_path) if previous_path is not None else None
    governance: object | None = None
    if governance_path is not None and governance_path.exists():
        governance = yaml.safe_load(governance_path.read_text(encoding="utf-8"))
    return assert_coverage_floors_not_lowered(
        current=current,
        previous=previous,
        governance=governance,
    )
