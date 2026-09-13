from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from cse_financial_etl.v2.contracts.enums import PublicationStatus, ValidationStatus
from cse_financial_etl.v2.exceptions import ReleaseContextRequiredError
from cse_financial_etl.v2.reporting.workbook import render_workbook
from tests.v2.helpers import release_context, source_fact


def test_workbook_writes_numeric_cells_and_reconciles(tmp_path: Path) -> None:
    fact = source_fact(
        validation_status=ValidationStatus.PASSED,
        publication_status=PublicationStatus.ELIGIBLE,
        normalized_value=Decimal("1234"),
    )
    path = render_workbook(
        release=release_context(),
        source_facts=(fact,),
        destination=tmp_path / "draft.xlsx",
    )
    workbook = load_workbook(path)
    assert "Snapshot" in workbook.sheetnames
    assert "Missing_Values" in workbook.sheetnames
    assert "Review_Summary" in workbook.sheetnames
    snapshot = workbook["Snapshot"]
    values = [cell.value for row in snapshot.iter_rows(min_row=4, max_row=4) for cell in row]
    assert 1234.0 in values or 1234 in values
    assert "ENTITY_NOT_RESOLVED" not in {cell.value for row in snapshot.iter_rows() for cell in row}


def test_zero_is_a_number_not_a_missing_status(tmp_path: Path) -> None:
    fact = source_fact(
        validation_status=ValidationStatus.PASSED,
        publication_status=PublicationStatus.ELIGIBLE,
        normalized_value=Decimal("0"),
        raw_value=Decimal("0"),
        period_end=date(2026, 6, 30),
    )
    path = render_workbook(
        release=release_context(), source_facts=(fact,), destination=tmp_path / "zero.xlsx"
    )
    snapshot = load_workbook(path)["Snapshot"]
    numeric = [
        cell.value
        for row in snapshot.iter_rows(min_row=4, max_row=4)
        for cell in row
        if isinstance(cell.value, (int, float))
    ]
    assert 0 in numeric or 0.0 in numeric


def test_workbook_requires_explicit_release_context(tmp_path: Path) -> None:
    with pytest.raises(ReleaseContextRequiredError):
        render_workbook(
            release=None, source_facts=(source_fact(),), destination=tmp_path / "no-ctx.xlsx"
        )


def test_withheld_facts_are_not_written_as_snapshot_status_strings(tmp_path: Path) -> None:
    fact = source_fact(
        validation_status=ValidationStatus.FAILED,
        publication_status=PublicationStatus.WITHHELD,
        reason_codes=("ENTITY_NOT_RESOLVED",),
    )
    path = render_workbook(
        release=release_context(), source_facts=(fact,), destination=tmp_path / "withheld.xlsx"
    )
    snapshot = load_workbook(path)["Snapshot"]
    written = {cell.value for row in snapshot.iter_rows() for cell in row}
    assert "ENTITY_NOT_RESOLVED" not in written
    assert "WITHHELD" not in written
