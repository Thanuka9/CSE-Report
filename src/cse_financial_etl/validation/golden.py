from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from cse_financial_etl.extraction.statement_extractor import (
    extract_filing,
    extract_quarter_prices,
    facts_by_code,
)


def _same_value(actual: Decimal | None, expected: str) -> bool:
    return actual is not None and actual == Decimal(expected)


def validate_golden(project_root: Path, as_of_date: date) -> dict[str, Any]:
    fixture_path = project_root / "tests" / "fixtures" / "golden_financial_facts.json"
    fixtures: list[dict[str, Any]] = json.loads(fixture_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    by_metric: dict[str, Counter[str]] = defaultdict(Counter)
    overall: Counter[str] = Counter()

    for fixture in fixtures:
        pdf_path = project_root / fixture["pdf"]
        if not pdf_path.exists():
            results.append({"pdf": fixture["pdf"], "status": "SKIPPED_PDF_NOT_AVAILABLE"})
            continue
        period_end = date.fromisoformat(fixture["period_end"])
        verification = str(fixture.get("verification_status") or "UNKNOWN")
        facts = facts_by_code(
            extract_filing(
                pdf_path,
                fixture["issuer_name"],
                fixture["symbol"],
                period_end,
            )
        )
        for metric_code, expected in fixture["facts"].items():
            fact = facts.get(metric_code)
            passed = bool(fact and _same_value(fact.normalized_value, expected))
            status = "PASS" if passed else "FAIL"
            by_metric[metric_code][status] += 1
            overall[status] += 1
            results.append(
                {
                    "pdf": fixture["pdf"],
                    "issuer_name": fixture["issuer_name"],
                    "period_end": fixture["period_end"],
                    "metric_code": metric_code,
                    "expected": expected,
                    "actual": (
                        str(fact.normalized_value)
                        if fact and fact.normalized_value is not None
                        else None
                    ),
                    "source_page": fact.source_page if fact else None,
                    "status": status,
                    "verification_status": verification,
                }
            )
        symbols = list(fixture.get("prices", {}))
        prices = {
            price.symbol: price
            for price in extract_quarter_prices(
                pdf_path,
                fixture["issuer_name"],
                symbols,
                period_end,
            )
        }
        for symbol, expected in fixture.get("prices", {}).items():
            price = prices.get(symbol)
            passed = bool(price and _same_value(price.value, expected))
            status = "PASS" if passed else "FAIL"
            by_metric["MARKET_PRICE_QUARTER_END"][status] += 1
            overall[status] += 1
            results.append(
                {
                    "pdf": fixture["pdf"],
                    "issuer_name": fixture["issuer_name"],
                    "period_end": fixture["period_end"],
                    "metric_code": "MARKET_PRICE_QUARTER_END",
                    "symbol": symbol,
                    "expected": expected,
                    "actual": str(price.value) if price and price.value is not None else None,
                    "source_page": price.source_page if price else None,
                    "status": status,
                    "verification_status": verification,
                }
            )

    sample_size = overall["PASS"] + overall["FAIL"]
    payload = {
        "as_of_date": as_of_date.isoformat(),
        "sample_size": sample_size,
        "passed": overall["PASS"],
        "failed": overall["FAIL"],
        "accuracy": overall["PASS"] / sample_size if sample_size else None,
        "by_metric": {
            metric: {
                "sample_size": counts["PASS"] + counts["FAIL"],
                "passed": counts["PASS"],
                "failed": counts["FAIL"],
                "accuracy": (
                    counts["PASS"] / (counts["PASS"] + counts["FAIL"])
                    if counts["PASS"] + counts["FAIL"]
                    else None
                ),
            }
            for metric, counts in sorted(by_metric.items())
        },
        "results": results,
    }
    from cse_financial_etl.reporting.accuracy import accuracy_dashboard_payload

    payload["field_accuracy"] = accuracy_dashboard_payload(
        fixture_path=fixture_path,
        golden_validation=payload,
    )
    payload["issuer_count"] = payload["field_accuracy"].get("issuer_count")
    output_path = project_root / "outputs" / f"golden_validation_{as_of_date.isoformat()}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(output_path)
    return payload
