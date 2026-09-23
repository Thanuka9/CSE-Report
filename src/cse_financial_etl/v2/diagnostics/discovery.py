"""Whole-PDF exact-alias discovery. Diagnostic only; does not publish."""

from __future__ import annotations

from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.taxonomy.matcher import accounting_regime_for, regimes_for
from cse_financial_etl.v2.taxonomy.registry import load_registry, normalize_label


def discover_exact_aliases(
    document: CanonicalDocument,
    *,
    issuer_id: str = "",
    issuer_name: str = "",
    issuer_type: str = "",
) -> tuple[dict[str, object], ...]:
    registry = load_registry()
    regime = accounting_regime_for(
        issuer_id=issuer_id, issuer_name=issuer_name, issuer_type=issuer_type
    )
    regimes = regimes_for(regime)
    hits: list[dict[str, object]] = []
    for page in document.pages:
        for line in page.lines:
            label = normalize_label(line.text)
            if not label:
                continue
            matched = registry.match_alias(label, regimes=regimes)
            if matched is None:
                continue
            hits.append(
                {
                    "page": page.page_number,
                    "line_id": line.line_id,
                    "text": line.text,
                    "metric_code": matched.concept.code,
                    "matched_alias": matched.matched_alias,
                    "bbox": line.bbox,
                }
            )
    return tuple(hits)
