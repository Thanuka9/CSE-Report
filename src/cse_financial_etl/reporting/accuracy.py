"""Field-level gold accuracy reporting (Phase One §40–41)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def summarize_gold_fixture(fixture_path: Path) -> dict[str, Any]:
    fixtures: list[dict[str, Any]] = json.loads(fixture_path.read_text(encoding="utf-8"))
    samples = sum(len(row.get("facts", {})) + len(row.get("prices", {})) for row in fixtures)
    by_status = Counter(str(row.get("verification_status") or "UNKNOWN") for row in fixtures)
    by_type = Counter(str(row.get("issuer_type") or "GENERAL") for row in fixtures)
    manual = sum(
        1
        for row in fixtures
        if row.get("verification_status") in {"MANUAL_OR_PRIOR", "MANUAL_QA"}
    )
    seeded = sum(1 for row in fixtures if row.get("verification_status") == "PIPELINE_SEEDED")
    return {
        "issuer_count": len(fixtures),
        "sample_count": samples,
        "manual_issuers": manual,
        "seeded_issuers": seeded,
        "verification_status_counts": dict(by_status),
        "issuer_type_counts": dict(by_type),
    }


def field_accuracy_from_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute field-oriented rates from golden validation result rows.

    Numeric gold rows carry optional expected_* context when present on the fixture.
    Missing context fields are reported as not_applicable rather than failures.
    """

    fields = (
        "numeric",
        "entity_scope",
        "duration_months",
        "comparison_role",
        "unit",
    )
    tallies: dict[str, Counter[str]] = {field: Counter() for field in fields}
    wrong_populated = 0
    false_missing = 0
    published = 0

    for row in results:
        status = row.get("status")
        if status not in {"PASS", "FAIL"}:
            continue
        published += 1
        expected = row.get("expected")
        actual = row.get("actual")
        if status == "FAIL" and actual not in (None, ""):
            wrong_populated += 1
        if status == "FAIL" and actual in (None, "") and expected not in (None, ""):
            false_missing += 1

        tallies["numeric"]["PASS" if status == "PASS" else "FAIL"] += 1
        for field in ("entity_scope", "duration_months", "comparison_role", "unit"):
            exp = row.get(f"expected_{field}")
            act = row.get(f"actual_{field}")
            if exp in (None, ""):
                tallies[field]["N/A"] += 1
            elif str(exp) == str(act):
                tallies[field]["PASS"] += 1
            else:
                tallies[field]["FAIL"] += 1

    def rate(counter: Counter[str]) -> float | None:
        total = counter["PASS"] + counter["FAIL"]
        return (counter["PASS"] / total) if total else None

    return {
        "numeric_accuracy": rate(tallies["numeric"]),
        "entity_accuracy": rate(tallies["entity_scope"]),
        "period_duration_accuracy": rate(tallies["duration_months"]),
        "comparison_role_accuracy": rate(tallies["comparison_role"]),
        "unit_accuracy": rate(tallies["unit"]),
        "wrong_populated_value_rate": (wrong_populated / published) if published else None,
        "false_missing_rate": (false_missing / published) if published else None,
        "published_checks": published,
        "field_tallies": {key: dict(value) for key, value in tallies.items()},
    }


def attach_fixture_context(
    results: list[dict[str, Any]], fixtures: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Enrich result rows with expected context from the gold fixture when available."""

    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fixture in fixtures:
        key = (
            str(fixture.get("issuer_name")),
            str(fixture.get("symbol")),
            str(fixture.get("period_end")),
        )
        index[key] = fixture
    enriched: list[dict[str, Any]] = []
    for row in results:
        item = dict(row)
        fixture = index.get(
            (
                str(row.get("issuer_name")),
                str(row.get("symbol") or ""),
                str(row.get("period_end")),
            )
        )
        if fixture is None:
            # Price rows may key only by symbol inside prices map.
            for candidate in fixtures:
                if candidate.get("issuer_name") == row.get("issuer_name") and candidate.get(
                    "period_end"
                ) == row.get("period_end"):
                    fixture = candidate
                    break
        if fixture is not None:
            item.setdefault("expected_entity_scope", fixture.get("entity_scope"))
            item.setdefault(
                "verification_status", fixture.get("verification_status", "PIPELINE_SEEDED")
            )
            contexts = fixture.get("fact_context") or {}
            metric = row.get("metric_code")
            context = contexts.get(metric) if isinstance(contexts, dict) else None
            if isinstance(context, dict):
                for field in ("duration_months", "comparison_role", "unit", "entity_scope"):
                    if field in context:
                        item[f"expected_{field}"] = context[field]
        enriched.append(item)
    return enriched


def accuracy_dashboard_payload(
    *,
    fixture_path: Path,
    golden_validation: dict[str, Any],
) -> dict[str, Any]:
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    summary = summarize_gold_fixture(fixture_path)
    results = attach_fixture_context(list(golden_validation.get("results") or []), fixtures)
    field = field_accuracy_from_results(results)
    by_verification: dict[str, Counter[str]] = defaultdict(Counter)
    for row in results:
        bucket = str(row.get("verification_status") or "UNKNOWN")
        by_verification[bucket][str(row.get("status") or "SKIP")] += 1
    return {
        **summary,
        "field_accuracy": field,
        "by_verification_status": {
            key: dict(value) for key, value in sorted(by_verification.items())
        },
        "numeric_accuracy": golden_validation.get("accuracy"),
        "sample_size": golden_validation.get("sample_size"),
        "passed": golden_validation.get("passed"),
        "failed": golden_validation.get("failed"),
    }
