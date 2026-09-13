from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from cse_financial_etl.extraction.statement_extractor import (
    ExtractedFact,
    extract_quarter_prices,
)
from cse_financial_etl.validation.acceptance import is_publishable_fact
from cse_financial_etl.validation.calibration import calibration_from_results


def _same_value(actual: Decimal | None, expected: str) -> bool:
    return actual is not None and actual == Decimal(expected)


def _extract_production_facts(
    project_root: Path,
    pdf_path: Path,
    issuer_name: str,
    symbol: str,
    period_end: date,
) -> list[ExtractedFact]:
    from cse_financial_etl.config import load_app_config, load_issuers
    from cse_financial_etl.v2.production.engine import extract_for_production

    config = load_app_config(project_root)
    return extract_for_production(
        pdf_path,
        issuer_name,
        symbol,
        period_end,
        engine=str(config.extraction_engine or "v2"),
        issuers=load_issuers(project_root),
    )


def _select_golden_fact(
    facts: list[ExtractedFact],
    *,
    metric_code: str,
    period_end: date,
    fixture_entity: str,
    expected_context: dict[str, Any],
) -> ExtractedFact | None:
    candidates = [fact for fact in facts if fact.metric_code == metric_code]
    if not candidates:
        return None
    wanted_entity = str(expected_context.get("entity_scope") or fixture_entity or "")
    wanted_duration = expected_context.get("duration_months")
    wanted_role = str(expected_context.get("comparison_role") or "CURRENT")

    def score(fact: ExtractedFact) -> tuple[int, int]:
        points = 0
        if wanted_entity and str(fact.entity_scope) == wanted_entity:
            points += 8
        if fact.period_end == period_end:
            points += 4
        if str(fact.comparison_role or "") == wanted_role:
            points += 2
        if wanted_duration is not None and fact.duration_months == wanted_duration:
            points += 1
        page = fact.source_page if fact.source_page is not None else 10**6
        return (points, -page)

    return max(candidates, key=score)


def _context_matches(
    actual_context: dict[str, Any],
    expected_context: dict[str, Any],
) -> bool:
    if not expected_context:
        return False
    for key, value in expected_context.items():
        actual = actual_context.get(key)
        if key == "duration_months" and actual is None:
            continue
        if str(actual) != str(value):
            return False
    return True


def validate_golden(project_root: Path, as_of_date: date) -> dict[str, Any]:
    fixture_path = project_root / "tests" / "fixtures" / "golden_financial_facts.json"
    fixtures: list[dict[str, Any]] = json.loads(fixture_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    by_metric: dict[str, Counter[str]] = defaultdict(Counter)
    overall: Counter[str] = Counter()
    by_verification: dict[str, Counter[str]] = defaultdict(Counter)

    for fixture in fixtures:
        pdf_path = project_root / fixture["pdf"]
        if not pdf_path.exists():
            pdf_path = project_root / "tests" / "fixtures" / "pdf" / pdf_path.name
        if not pdf_path.exists():
            results.append({"pdf": fixture["pdf"], "status": "SKIPPED_PDF_NOT_AVAILABLE"})
            continue
        period_end = date.fromisoformat(fixture["period_end"])
        verification = str(fixture.get("verification_status") or "UNKNOWN")
        extracted = _extract_production_facts(
            project_root,
            pdf_path,
            fixture["issuer_name"],
            fixture["symbol"],
            period_end,
        )
        for metric_code, expected in fixture["facts"].items():
            expected_context = fixture.get("fact_context", {}).get(metric_code, {})
            fact = _select_golden_fact(
                extracted,
                metric_code=metric_code,
                period_end=period_end,
                fixture_entity=str(fixture.get("entity_scope") or ""),
                expected_context=expected_context,
            )
            actual_context = {
                "entity_scope": fact.entity_scope if fact else None,
                "period_end": fact.period_end.isoformat() if fact else None,
                "duration_months": fact.duration_months if fact else None,
                "comparison_role": fact.comparison_role if fact else None,
                "unit": fact.currency if fact else None,
                "scale_factor": fact.scale_factor if fact else None,
            }
            context_ok = _context_matches(actual_context, expected_context)
            numeric_match = bool(fact and _same_value(fact.normalized_value, expected))
            passed = bool(
                numeric_match
                and fact
                and is_publishable_fact(fact, release_mode="DRAFT")
                and (context_ok or verification != "MANUAL_QA")
            )
            status = "PASS" if passed else "FAIL"
            by_metric[metric_code][status] += 1
            overall[status] += 1
            by_verification[verification][status] += 1
            results.append(
                {
                    "pdf": fixture["pdf"],
                    "issuer_name": fixture["issuer_name"],
                    "symbol": fixture.get("symbol"),
                    "period_end": fixture["period_end"],
                    "metric_code": metric_code,
                    "expected": expected,
                    "actual": str(fact.normalized_value) if fact and fact.normalized_value is not None else None,
                    "actual_status": fact.status if fact else None,
                    "actual_duration_months": fact.duration_months if fact else None,
                    "actual_entity_scope": fact.entity_scope if fact else None,
                    "source_page": fact.source_page if fact else None,
                    "overall_certainty": fact.overall_certainty if fact else None,
                    "certainty_band": fact.certainty_band if fact else None,
                    "status": status,
                    "verification_status": verification,
                    **{f"expected_{key}": value for key, value in expected_context.items()},
                    **{f"actual_{key}": value for key, value in actual_context.items()},
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
            by_verification[verification][status] += 1
            results.append(
                {
                    "pdf": fixture["pdf"],
                    "issuer_name": fixture["issuer_name"],
                    "symbol": symbol,
                    "period_end": fixture["period_end"],
                    "metric_code": "MARKET_PRICE_QUARTER_END",
                    "expected": expected,
                    "actual": str(price.value) if price and price.value is not None else None,
                    "source_page": price.source_page if price else None,
                    "overall_certainty": price.confidence_score if price else None,
                    "certainty_band": price.certainty_band if price else None,
                    "status": status,
                    "verification_status": verification,
                }
            )

    by_metric = defaultdict(Counter)
    for row in results:
        if row.get("verification_status") == "MANUAL_QA":
            by_metric[row["metric_code"]][row["status"]] += 1
    manual = by_verification["MANUAL_QA"]
    sample_size = manual["PASS"] + manual["FAIL"]
    manual_issuers = {
        str(row.get("issuer_name"))
        for row in results
        if row.get("verification_status") == "MANUAL_QA"
        and row.get("status") in {"PASS", "FAIL"}
        and row.get("issuer_name")
    }
    payload: dict[str, Any] = {
        "as_of_date": as_of_date.isoformat(),
        "sample_size": sample_size,
        "manual_issuer_count": len(manual_issuers),
        "passed": manual["PASS"],
        "failed": manual["FAIL"],
        "accuracy": manual["PASS"] / sample_size if sample_size else None,
        "regression_checks": sum(overall.values()),
        "accuracy_basis": "MANUAL_QA_CONTEXT",
        "accuracy_disclaimer": (
            "Headline accuracy uses MANUAL_QA fixtures only. Other rows are regression anchors, "
            "not independent truth. Sample accuracy is not population accuracy."
        ),
        "by_verification_status": {
            key: {
                "sample_size": counts["PASS"] + counts["FAIL"],
                "passed": counts["PASS"],
                "failed": counts["FAIL"],
                "accuracy": (
                    counts["PASS"] / (counts["PASS"] + counts["FAIL"])
                    if counts["PASS"] + counts["FAIL"]
                    else None
                ),
            }
            for key, counts in sorted(by_verification.items())
        },
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
    payload["certainty_calibration"] = calibration_from_results(results)

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
