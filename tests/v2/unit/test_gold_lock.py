from __future__ import annotations

from cse_financial_etl.v2.diagnostics.real_filings import load_gold_lock, load_real_filing_cases


def test_locked_gold_set_is_diverse_and_honest() -> None:
    lock = load_gold_lock()
    assert 25 <= len(lock.scoring_symbols) <= 40
    for symbol in lock.required_manual_qa_symbols:
        assert symbol in lock.scoring_symbols
    for symbol in lock.known_timeout_symbols:
        assert symbol not in lock.scoring_symbols
        assert symbol not in lock.regression_symbols
    assert "ABAN.N0000" in lock.regression_symbols
    assert "CDB.N0000" in lock.regression_symbols
    assert "CRL.N0000" in lock.regression_symbols
    assert "not newly human-re-adjudicated" in lock.note.casefold()
    cases = load_real_filing_cases(limit=40, locked=True)
    if not cases:
        return
    assert all(case.gold_role == "scoring" for case in cases)
    assert all(case.issuer_id not in lock.known_timeout_symbols for case in cases)
    present = {case.issuer_id for case in cases}
    if set(lock.required_manual_qa_symbols) <= present:
        assert "MANUAL_QA" in {case.verification_status for case in cases}
    if len(cases) >= 20:
        assert {"BANK", "FINANCE", "INSURANCE", "HOLDING", "GENERAL"} <= {
            case.issuer_type for case in cases
        }
