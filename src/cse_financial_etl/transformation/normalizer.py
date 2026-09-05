from collections.abc import Iterable
from decimal import Decimal

from cse_financial_etl.domain.enums import MetricType, UnitScope
from cse_financial_etl.domain.models import NormalizationResult, UnitCandidate
from cse_financial_etl.extraction.unit_detector import resolve_unit

LOCAL_PER_SHARE_SCOPES = {UnitScope.METRIC, UnitScope.ROW, UnitScope.CELL}


def normalize_value(
    raw_value: Decimal,
    metric_type: MetricType,
    candidates: Iterable[UnitCandidate],
) -> NormalizationResult:
    """Apply statement scale only when the metric type permits it."""

    all_candidates = list(candidates)

    if metric_type is MetricType.MONETARY_ABSOLUTE:
        unit = resolve_unit(all_candidates)
        return NormalizationResult(
            raw_value=raw_value,
            normalized_value=raw_value * unit.scale_factor,
            metric_type=metric_type,
            currency=unit.currency,
            scale_factor=unit.scale_factor,
            unit_candidate=unit,
            status="NORMALIZED",
        )

    if metric_type is MetricType.MONETARY_PER_SHARE:
        local_candidates = [
            candidate for candidate in all_candidates if candidate.scope in LOCAL_PER_SHARE_SCOPES
        ]
        local_unit = resolve_unit(local_candidates) if local_candidates else None
        scale = local_unit.scale_factor if local_unit else 1
        return NormalizationResult(
            raw_value=raw_value,
            normalized_value=raw_value * scale,
            metric_type=metric_type,
            currency=local_unit.currency if local_unit else None,
            scale_factor=scale,
            unit_candidate=local_unit,
            status="LOCAL_UNIT" if local_unit else "UNSCALED_PER_SHARE",
        )

    return NormalizationResult(
        raw_value=raw_value,
        normalized_value=raw_value,
        metric_type=metric_type,
        currency=None,
        scale_factor=1,
        unit_candidate=None,
        status="NOT_MONETARY_SCALED",
    )
