from datetime import date
from pathlib import Path

import pytest

from cse_financial_etl.validation.golden import validate_golden


def test_available_golden_financial_facts() -> None:
    project_root = Path(__file__).resolve().parents[2]
    fixture_pdf = project_root / "data" / "raw" / "filings"
    if not fixture_pdf.exists():
        pytest.skip("Golden CSE PDFs have not been downloaded")
    result = validate_golden(project_root, date(2026, 9, 3))
    if not result["sample_size"]:
        pytest.skip("Golden CSE PDFs have not been downloaded")
    assert result["sample_size"] >= 30
    failures = [row for row in result["results"] if row.get("status") == "FAIL"]
    assert failures == []
