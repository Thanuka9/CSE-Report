from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from cse_financial_etl.validation.row_safety import (
    is_narrative_unit_amount,
    ratio_plausibility_issue,
    suspicious_selected_numeric,
)

PUBLISHABLE = {"EXTRACTED", "EXTRACTED_DERIVED"}
SOURCE_EPS = ("EPS_DILUTED", "EPS_BASIC")
ABSOLUTE_MONETARY = {
    "TOP_LINE",
    "OPERATING_PROFIT",
    "PBT",
    "PAT",
    "TOTAL_ASSETS",
    "TOTAL_EQUITY",
    "TOTAL_LIABILITIES",
}


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _fact_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("issuer_name", ""),
        row.get("symbol", ""),
        row.get("period_end", ""),
        row.get("metric_code", ""),
    )


def audit(facts_path: Path, prices_path: Path) -> dict[str, Any]:
    facts = _read_csv(facts_path)
    prices = _read_csv(prices_path)
    violations: dict[str, list[dict[str, Any]]] = defaultdict(list)

    seen: dict[tuple[str, str, str, str], int] = defaultdict(int)
    by_slot: dict[tuple[str, str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in facts:
        key = _fact_key(row)
        seen[key] += 1
        by_slot[key[:3]][key[3]] = row

        status = row.get("status", "")
        validation = row.get("validation_status", "")
        normalized = _decimal(row.get("normalized_value"))
        raw_value = _decimal(row.get("raw_value"))
        scale = _decimal(row.get("scale_factor"))
        metric = row.get("metric_code", "")

        if status in PUBLISHABLE and validation != "PASSED":
            violations["publishable_without_passed_validation"].append(
                {"key": key, "status": status, "validation_status": validation}
            )
        if status not in PUBLISHABLE and normalized is not None:
            violations["withheld_fact_has_value"].append(
                {"key": key, "status": status, "normalized_value": str(normalized)}
            )
        if (
            status in PUBLISHABLE
            and metric in ABSOLUTE_MONETARY
            and is_narrative_unit_amount(row.get("unit_source_text"))
        ):
            violations["narrative_unit_published"].append(
                {"key": key, "unit_source_text": row.get("unit_source_text")}
            )
        if (
            status in PUBLISHABLE
            and metric in ABSOLUTE_MONETARY
            and suspicious_selected_numeric(
                metric,
                raw_value,
                int(scale) if scale is not None and scale == scale.to_integral() else None,
                row.get("source_line"),
            )
        ):
            violations["unsafe_numeric_source_published"].append(
                {
                    "key": key,
                    "raw_value": row.get("raw_value"),
                    "source_line": row.get("source_line"),
                }
            )
        if status in PUBLISHABLE and metric in {"ROA", "ROE", "NPM", "DEBT_TO_EQUITY"}:
            if normalized is not None:
                issue = ratio_plausibility_issue(metric, normalized)
                if issue is not None:
                    violations["implausible_ratio_published"].append(
                        {"key": key, "normalized_value": str(normalized), "issue": issue}
                    )

    for key, count in seen.items():
        if count > 1:
            violations["duplicate_fact_key"].append({"key": key, "count": count})

    for slot, metrics in by_slot.items():
        selected = metrics.get("EPS_SELECTED")
        if selected is None or selected.get("status") not in PUBLISHABLE:
            continue
        preferred: dict[str, str] | None = None
        for code in SOURCE_EPS:
            candidate = metrics.get(code)
            if (
                candidate is not None
                and candidate.get("status") in PUBLISHABLE
                and candidate.get("validation_status") == "PASSED"
                and _decimal(candidate.get("normalized_value")) is not None
            ):
                preferred = candidate
                break
        selected_value = _decimal(selected.get("normalized_value"))
        if (
            preferred is None
            or selected_value != _decimal(preferred.get("normalized_value"))
            or selected.get("entity_scope") != preferred.get("entity_scope")
            or selected.get("comparison_role") != preferred.get("comparison_role")
        ):
            violations["eps_selected_invalid_lineage"].append(
                {
                    "slot": slot,
                    "selected_value": str(selected_value) if selected_value is not None else None,
                    "preferred_source": preferred.get("metric_code") if preferred is not None else None,
                    "preferred_value": preferred.get("normalized_value") if preferred is not None else None,
                }
            )

    for row in prices:
        if row.get("status") not in {"EXTRACTED", "RESOLVED_HISTORICAL"}:
            continue
        value = _decimal(row.get("value"))
        if value is None or value <= 0:
            violations["nonpositive_published_price"].append(
                {
                    "issuer_name": row.get("issuer_name"),
                    "symbol": row.get("symbol"),
                    "period_end": row.get("period_end"),
                    "value": row.get("value"),
                    "status": row.get("status"),
                }
            )

    payload: dict[str, Any] = {
        "facts_path": str(facts_path),
        "prices_path": str(prices_path),
        "fact_rows": len(facts),
        "price_rows": len(prices),
        "violation_counts": {name: len(rows) for name, rows in sorted(violations.items())},
        "violations": {name: rows[:100] for name, rows in sorted(violations.items())},
    }
    payload["row_safety"] = "PASS" if not any(violations.values()) else "FAIL"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit fail-closed row-level safety invariants.")
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = audit(args.facts, args.prices)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["row_safety"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
