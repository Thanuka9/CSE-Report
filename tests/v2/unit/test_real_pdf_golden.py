from __future__ import annotations

from decimal import Decimal

import pytest

from cse_financial_etl.v2.contracts.enums import EntityScope, PublicationStatus, ValidationStatus
from cse_financial_etl.v2.diagnostics.golden import score_golden
from cse_financial_etl.v2.diagnostics.real_filings import (
    load_gold_lock,
    load_real_filing_cases,
    resolve_filing_pdf,
)
from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline

AUDITED = (
    (
        "data/raw/filings/JAT_HOLDINGS_PLC/2026-06-30_2353_1786011152811.27_Q1_SIGNED.pdf",
        "JAT.N0000",
        EntityScope.COMPANY,
        Decimal("108959808"),
    ),
    (
        "data/raw/filings/COMMERCIAL_BANK_OF_CEYLON_PLC/2026-06-30_369_1786618965674.pdf",
        "COMB.N0000",
        EntityScope.BANK,
        Decimal("16621006000"),
    ),
    (
        "data/raw/filings/DIALOG_AXIATA_PLC/2026-06-30_389_1786711190916.pdf",
        "DIAL.N0000",
        EntityScope.COMPANY,
        Decimal("8187022000"),
    ),
    (
        "data/raw/filings/JOHN_KEELLS_HOLDINGS_PLC/2026-06-30_508_1785229278745.pdf",
        "JKH.N0000",
        EntityScope.COMPANY,
        Decimal("5378093000"),
    ),
)


def _published_pat(pdf, issuer_id: str, entity: EntityScope):
    _statements, facts, _derived, _metrics = run_pdf_pipeline(
        pdf,
        issuer_id=issuer_id,
        filing_version_id=issuer_id,
        expected_entity_scope=entity,
        target_period_end=None,
    )
    return [
        fact
        for fact in facts
        if fact.metric_code == "PAT"
        and fact.publication_status is not PublicationStatus.WITHHELD
        and fact.validation_status is not ValidationStatus.FAILED
    ]


@pytest.mark.parametrize("relative, issuer_id, entity, expected", AUDITED)
def test_audited_vendor_pat_matches_manual_truth(relative, issuer_id, entity, expected) -> None:
    pdf = resolve_filing_pdf(relative)
    if pdf is None:
        pytest.skip(f"real filing PDF is not present: {relative}")
    published = _published_pat(pdf, issuer_id, entity)
    assert any(fact.normalized_value == expected for fact in published), (
        f"{issuer_id} PAT {expected} missing from {[str(fact.normalized_value) for fact in published]}"
    )


def test_real_cse_golden_corpus_runs_on_available_filings() -> None:
    lock = load_gold_lock()
    cases = load_real_filing_cases(limit=40, locked=True)
    if len(cases) < 6:
        pytest.skip(f"only {len(cases)} locked CSE PDFs are available locally")
    hits = 0
    expected_total = 0
    for case in cases:
        _statements, facts, _derived, _metrics = run_pdf_pipeline(
            case.pdf_path,
            issuer_id=case.issuer_id,
            filing_version_id=case.case_id,
            expected_entity_scope=case.entity_scope,
            target_period_end=case.period_end,
        )
        report = score_golden(case.expected, facts)
        hits += report.true_positives
        expected_total += report.expected_count
    assert {case.issuer_id for case in cases} <= set(lock.scoring_symbols)
    assert expected_total >= 20
    audited = {"JKH.N0000", "COMB.N0000", "DIAL.N0000", "JAT.N0000"}
    if audited <= {case.issuer_id for case in cases}:
        assert hits >= 4, "locked V2 gold set should recover the audited PAT truths"
    else:
        assert hits >= 1, "V2 extracted no adjudicated gold values from available CSE PDFs"
