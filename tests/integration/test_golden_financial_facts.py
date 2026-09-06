from datetime import date
from pathlib import Path

import pytest

from cse_financial_etl.validation.golden import validate_golden

_MANUAL_STATUSES = {"MANUAL_QA", "MANUAL_OR_PRIOR"}


def test_available_golden_financial_facts() -> None:
    project_root = Path(__file__).resolve().parents[2]
    fixture_pdf = project_root / "data" / "raw" / "filings"
    if not fixture_pdf.exists():
        pytest.skip("Golden CSE PDFs have not been downloaded")
    result = validate_golden(project_root, date(2026, 9, 3))
    if not result["sample_size"]:
        pytest.skip("Golden CSE PDFs have not been downloaded")
    assert result["sample_size"] >= 100
    assert result["accuracy"] is not None
    assert result["accuracy"] >= 0.95

    fixtures = __import__("json").loads(
        (project_root / "tests" / "fixtures" / "golden_financial_facts.json").read_text(
            encoding="utf-8"
        )
    )
    manual_pdfs = {
        row["pdf"]
        for row in fixtures
        if row.get("verification_status") in _MANUAL_STATUSES
    }
    manual_failures = [
        row
        for row in result["results"]
        if row.get("status") == "FAIL" and row.get("pdf") in manual_pdfs
    ]
    assert manual_failures == []
