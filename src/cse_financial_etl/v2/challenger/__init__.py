"""Challenger package: V1-assisted source observations into V2 contracts."""

from cse_financial_etl.v2.challenger.models import V1SourceObservation
from cse_financial_etl.v2.challenger.observation_union import (
    observations_to_discovery_candidates,
    union_candidates,
)
from cse_financial_etl.v2.challenger.v1_source_observations import collect_v1_source_observations

__all__ = [
    "V1SourceObservation",
    "collect_v1_source_observations",
    "observations_to_discovery_candidates",
    "union_candidates",
]
