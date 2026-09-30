"""Governed V2 production smoke: signed review reaches the OFFICIAL workbook.

Does not flip configs/app.yml. Does not invent MANUAL_QA gold.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from cse_financial_etl.contracts.release import (
    apply_review_decisions,
    fact_fingerprint,
    make_decision,
    sign_decision,
)
from cse_financial_etl.v2.contracts.enums import (
    PublicationStatus,
    ReleaseMode,
    ReviewStatus,
    ValidationStatus,
)
from cse_financial_etl.v2.production.adapter import _from_source
from cse_financial_etl.v2.production.engine import extract_for_production
from cse_financial_etl.v2.production.facts_store import write_v2_publication_facts
from cse_financial_etl.v2.production.publish import publish_production_workbook
from cse_financial_etl.v2.production.review_propagation import (
    propagate_review_status_to_native_facts,
)
from cse_financial_etl.v2.reporting.release_view import count_eligible_facts
from cse_financial_etl.v2.taxonomy.registry import load_registry
from tests.v2.helpers import release_context, source_fact

ROOT = Path(__file__).resolve().parents[3]
FILING_SHA = "a" * 64


def _committed_engine() -> str:
    app = yaml.safe_load((ROOT / "configs" / "app.yml").read_text(encoding="utf-8"))
    return str(app["extraction"]["engine"])


def _committed_release_mode() -> str:
    app = yaml.safe_load((ROOT / "configs" / "app.yml").read_text(encoding="utf-8"))
    return str(app["publication"]["release_mode"])


def test_signed_approval_survives_into_official_v2_workbook(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CSE_REVIEW_KEY_SMOKE_REVIEW_1", "smoke-secret")
    native = source_fact(
        fact_id="fact-1",
        issuer_id="ACM.N0000",
        review_status=ReviewStatus.REVIEW,
        publication_status=PublicationStatus.ELIGIBLE,
        validation_status=ValidationStatus.PASSED,
        normalized_value=Decimal("1234000"),
        raw_value=Decimal("1234"),
    )
    extracted = _from_source(
        native,
        issuer_name="Acme PLC",
        symbol="ACM.N0000",
        registry=load_registry(),
    )
    assert extracted.review_status == "REVIEW"
    assert count_eligible_facts((native,), (), mode=ReleaseMode.OFFICIAL) == 0

    signed = sign_decision(
        make_decision(
            issuer_name=extracted.issuer_name,
            symbol=extracted.symbol,
            period_end=extracted.period_end.isoformat(),
            metric_code=extracted.metric_code,
            filing_sha256=FILING_SHA,
            fact_fingerprint=fact_fingerprint(extracted),
            reviewer_id="smoke-reviewer",
            decision="APPROVED",
        ),
        secret="smoke-secret",
        key_id="SMOKE-REVIEW-1",
    )
    reviewed, summary = apply_review_decisions(
        [extracted],
        [signed],
        filing_sha256=FILING_SHA,
    )
    assert summary.approved_applied == 1
    assert reviewed[0].review_status == "APPROVED"

    stamped, derived = propagate_review_status_to_native_facts(reviewed, (native,), ())
    assert stamped[0].review_status == ReviewStatus.APPROVED
    assert count_eligible_facts(stamped, derived, mode=ReleaseMode.DRAFT) == 1
    assert count_eligible_facts(stamped, derived, mode=ReleaseMode.OFFICIAL) == 1

    write_v2_publication_facts(
        tmp_path,
        date(2026, 9, 22),
        source_facts=stamped,
        derived_facts=derived,
    )
    official = publish_production_workbook(
        release=release_context(mode=ReleaseMode.OFFICIAL),
        source_facts=stamped,
        derived_facts=derived,
        destination=tmp_path / "official.xlsx",
    )
    draft = publish_production_workbook(
        release=release_context(mode=ReleaseMode.DRAFT),
        source_facts=stamped,
        derived_facts=derived,
        destination=tmp_path / "draft.xlsx",
    )
    assert official.exists()
    assert draft.exists()
    assert _committed_engine() == "v2"
    assert _committed_release_mode() == "DRAFT"


def test_v1_rollback_override_does_not_rewrite_committed_v2_default(monkeypatch) -> None:
    called = {"v1": 0, "v2": 0}

    def fake_v1(*_args, **_kwargs):
        called["v1"] += 1
        return []

    def fake_v2(*_args, **_kwargs):
        called["v2"] += 1
        return []

    monkeypatch.setattr(
        "cse_financial_etl.v2.production.engine.extract_filing", fake_v1
    )
    monkeypatch.setattr(
        "cse_financial_etl.v2.production.engine.extract_filing_v2", fake_v2
    )
    extract_for_production(
        Path("missing.pdf"), "Acme", "ACM.N0000", date(2026, 6, 30), engine="v2"
    )
    extract_for_production(
        Path("missing.pdf"), "Acme", "ACM.N0000", date(2026, 6, 30), engine="v1"
    )
    assert called == {"v1": 1, "v2": 1}
    assert _committed_engine() == "v2"
    assert _committed_release_mode() == "DRAFT"
