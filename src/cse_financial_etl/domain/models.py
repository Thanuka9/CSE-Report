from dataclasses import dataclass
from decimal import Decimal

from .enums import MetricType, UnitScope


@dataclass(frozen=True, slots=True)
class UnitCandidate:
    source_text: str
    currency: str
    scale_factor: int
    scope: UnitScope
    page: int | None = None
    distance: float = 0.0
    pattern_id: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    raw_value: Decimal
    normalized_value: Decimal
    metric_type: MetricType
    currency: str | None
    scale_factor: int
    unit_candidate: UnitCandidate | None
    status: str
