from __future__ import annotations

import pytest
from pydantic import ValidationError

from cse_financial_etl.v2.contracts.enums import ReleaseMode, ReviewStatus
from cse_financial_etl.v2.contracts.release import ReleaseContext, require_release_context
from cse_financial_etl.v2.exceptions import ReleaseContextRequiredError
from cse_financial_etl.v2.reporting.release_view import build_release_view
from tests.v2.helpers import release_context, source_fact


def test_release_context_fields_are_required() -> None:
    with pytest.raises(ValidationError):
        ReleaseContext.model_validate(
            {
                "generation_id": "g",
                "run_id": "r",
                "mode": "DRAFT",
                "code_sha": "c",
                "policy_hash": "p",
            }
        )
    with pytest.raises(ValidationError):
        release_context(run_id="  ")


def test_require_release_context_rejects_none() -> None:
    with pytest.raises(ReleaseContextRequiredError):
        require_release_context(None)


def test_release_view_requires_explicit_context() -> None:
    with pytest.raises(ReleaseContextRequiredError):
        build_release_view(release=None, source_facts=(source_fact(),))  # type: ignore[arg-type]
    view = build_release_view(release=release_context(), source_facts=(source_fact(),))
    assert len(view.eligible) == 1
    assert view.release.mode == release_context().mode


def test_official_release_excludes_unreviewed_facts() -> None:
    official = release_context(mode=ReleaseMode.OFFICIAL)
    pending = source_fact(review_status=ReviewStatus.REVIEW)
    approved = source_fact(
        fact_id="fact-approved", cell_id="cell-approved", review_status=ReviewStatus.APPROVED
    )
    draft = build_release_view(release=release_context(), source_facts=(pending, approved))
    gated = build_release_view(release=official, source_facts=(pending, approved))
    assert {fact.fact_id for fact in draft.eligible} == {"fact-1", "fact-approved"}
    assert {fact.fact_id for fact in gated.eligible} == {"fact-approved"}
