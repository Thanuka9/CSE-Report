"""V1 vs V2 frozen-universe shadow diff."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping

from cse_financial_etl.v2.diagnostics.fact_diff import (
    FactDiffClass,
    classify_fact_pair,
    fact_identity_from_mapping,
)


def shadow_diff(
    reference: tuple[Mapping[str, object], ...],
    current: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    ref_map = {fact_identity_from_mapping(item).key(): item for item in reference}
    cur_map = {fact_identity_from_mapping(item).key(): item for item in current}
    keys = set(ref_map) | set(cur_map)
    counts: Counter[str] = Counter()
    by_metric: dict[str, Counter[str]] = defaultdict(Counter)
    by_reason: dict[str, Counter[str]] = defaultdict(Counter)
    by_issuer: dict[str, Counter[str]] = defaultdict(Counter)
    by_parser: dict[str, Counter[str]] = defaultdict(Counter)
    by_sector: dict[str, Counter[str]] = defaultdict(Counter)
    for key in keys:
        classified = classify_fact_pair(ref_map.get(key), cur_map.get(key))
        counts[classified.value] += 1
        metric = key[-1]
        by_metric[str(metric)][classified.value] += 1
        payload = cur_map.get(key) or ref_map.get(key) or {}
        reason = str(payload.get("reason_code") or payload.get("reason_codes") or "")
        if reason:
            by_reason[reason][classified.value] += 1
        issuer = str(payload.get("issuer_id") or "")
        if issuer:
            by_issuer[issuer][classified.value] += 1
        parser = str(payload.get("parser_path") or payload.get("parser_name") or "")
        if parser:
            by_parser[parser][classified.value] += 1
        sector = str(payload.get("sector") or "")
        if sector:
            by_sector[sector][classified.value] += 1
    return {
        "counts": dict(counts),
        "by_metric": {metric: dict(values) for metric, values in by_metric.items()},
        "by_reason": {reason: dict(values) for reason, values in by_reason.items()},
        "by_issuer": {issuer: dict(values) for issuer, values in by_issuer.items()},
        "by_parser": {parser: dict(values) for parser, values in by_parser.items()},
        "by_sector": {sector: dict(values) for sector, values in by_sector.items()},
        "classes": [item.value for item in FactDiffClass],
    }
