"""Release view construction. Requires an explicit ReleaseContext."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import (
    PublicationStatus,
    ReleaseMode,
    ReviewStatus,
    ValidationStatus,
)
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact
from cse_financial_etl.v2.contracts.release import ReleaseContext, require_release_context
from cse_financial_etl.v2.reporting.reconciliation import EligibleReleaseFact


class ReleaseView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    release: ReleaseContext
    eligible: tuple[EligibleReleaseFact, ...]
    withheld_reason_codes: tuple[str, ...] = ()


def _is_draft_eligible(fact: SourceFact | DerivedFact) -> bool:
    return (
        fact.validation_status == ValidationStatus.PASSED
        and fact.review_status != ReviewStatus.REJECTED
        and fact.publication_status != PublicationStatus.WITHHELD
    )


def _is_official_eligible(fact: SourceFact | DerivedFact) -> bool:
    return _is_draft_eligible(fact) and fact.review_status in {
        ReviewStatus.APPROVED,
        ReviewStatus.CURATED,
    }


def build_release_view(
    *,
    release: ReleaseContext | None,
    source_facts: Sequence[SourceFact] = (),
    derived_facts: Sequence[DerivedFact] = (),
) -> ReleaseView:
    context = require_release_context(release)
    eligible: list[EligibleReleaseFact] = []
    withheld: list[str] = []
    predicate = (
        _is_official_eligible if context.mode == ReleaseMode.OFFICIAL else _is_draft_eligible
    )
    facts: list[SourceFact | DerivedFact] = []
    facts.extend(source_facts)
    facts.extend(derived_facts)
    for fact in facts:
        if not predicate(fact):
            withheld.extend(fact.reason_codes)
            continue
        eligible.append(
            EligibleReleaseFact(
                fact_id=fact.fact_id,
                issuer_id=fact.issuer_id,
                metric_code=fact.metric_code,
                period_end=fact.period_end,
                duration_months=fact.duration_months,
                comparison_role=fact.comparison_role,
                entity_scope=fact.entity_scope,
                normalized_value=fact.normalized_value,
            )
        )
    return ReleaseView(
        release=context,
        eligible=tuple(eligible),
        withheld_reason_codes=tuple(withheld),
    )


def count_eligible_facts(
    source_facts: Sequence[SourceFact] = (),
    derived_facts: Sequence[DerivedFact] = (),
    *,
    mode: ReleaseMode,
) -> int:
    """Count facts that would appear in the DRAFT or OFFICIAL release view."""

    predicate = (
        _is_official_eligible if mode == ReleaseMode.OFFICIAL else _is_draft_eligible
    )
    facts: tuple[SourceFact | DerivedFact, ...] = tuple(source_facts) + tuple(derived_facts)
    return sum(1 for fact in facts if predicate(fact))
