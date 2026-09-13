from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalPage, CanonicalToken
from cse_financial_etl.v2.contracts.enums import (
    EntityScope,
    ExtractionMode,
    FactKind,
    StatementType,
)
from cse_financial_etl.v2.contracts.facts import DerivedFact, FactCandidate, SourceFact
from cse_financial_etl.v2.contracts.statement import (
    CanonicalStatement,
    StatementCell,
    StatementColumn,
)
from tests.v2.helpers import VALID_SHA, source_fact, source_ref


def test_source_ref_requires_sha_and_parser() -> None:
    with pytest.raises(ValidationError):
        source_ref(source_sha256="")
    with pytest.raises(ValidationError):
        source_ref(parser_name="  ")
    with pytest.raises(ValidationError):
        source_ref(source_sha256="deadbeef")


def test_source_fact_requires_provenance_and_schema_version() -> None:
    fact = source_fact()
    assert fact.schema_version == SCHEMA_VERSION
    assert fact.fact_kind == FactKind.SOURCE
    assert fact.source_ref.source_sha256 == VALID_SHA
    dumped = fact.model_dump()
    restored = SourceFact.model_validate(dumped)
    assert restored == fact


def test_source_fact_rejects_missing_source_ref() -> None:
    payload = source_fact().model_dump()
    del payload["source_ref"]
    with pytest.raises(ValidationError):
        SourceFact.model_validate(payload)


def test_source_fact_rejects_unknown_entity_scope() -> None:
    with pytest.raises(ValidationError):
        source_fact(entity_scope=EntityScope.UNKNOWN)


def test_group_is_not_company() -> None:
    assert EntityScope.GROUP != EntityScope.COMPANY
    group = source_fact(entity_scope=EntityScope.GROUP)
    assert group.entity_scope is EntityScope.GROUP
    mutated = group.model_dump()
    mutated["entity_scope"] = EntityScope.COMPANY
    converted = SourceFact.model_validate(mutated)
    assert converted.entity_scope is EntityScope.COMPANY
    assert converted.fact_id == group.fact_id
    # Contracts never coerce GROUP→COMPANY in place.
    assert group.entity_scope is EntityScope.GROUP


def test_contracts_are_frozen() -> None:
    fact = source_fact()
    with pytest.raises(ValidationError):
        fact.metric_code = "PBT"  # type: ignore[misc]


def test_derived_fact_cannot_masquerade_as_source() -> None:
    derived = DerivedFact(
        fact_id="derived-1",
        issuer_id="issuer-1",
        metric_code="NPM",
        formula_id="npm.pat_over_top_line",
        input_fact_ids=("fact-pat", "fact-topline"),
        normalized_value=Decimal("0.12"),
        entity_scope=EntityScope.COMPANY,
        period_end=date(2026, 6, 30),
        duration_months=3,
        comparison_role=source_fact().comparison_role,
        unit_dimension=source_fact().unit_dimension,
    )
    assert derived.fact_kind == FactKind.DERIVED
    assert "cell_id" not in derived.model_dump()
    with pytest.raises(ValidationError):
        DerivedFact.model_validate({**derived.model_dump(), "cell_id": "cell-1"})


def test_fact_candidate_requires_source_ref() -> None:
    candidate = FactCandidate(
        candidate_id="cand-1",
        statement_id="stmt-1",
        cell_id="cell-1",
        row_id="row-1",
        column_id="col-1",
        source_ref=source_ref(),
    )
    assert candidate.required_context_resolved() is False
    assert candidate.schema_version == SCHEMA_VERSION


def test_canonical_document_roundtrip() -> None:
    token = CanonicalToken(
        text="PAT",
        page_number=1,
        bbox=(1.0, 2.0, 20.0, 12.0),
        source_parser="v2.native_pymupdf",
    )
    document = CanonicalDocument(
        filing_version_id="fv-1",
        source_sha256=VALID_SHA,
        pages=(
            CanonicalPage(
                page_number=1,
                width=612.0,
                height=792.0,
                lines=(),
                extraction_mode=ExtractionMode.NATIVE,
            ),
        ),
        parser_manifest={"parser_name": "v2.native_pymupdf"},
    )
    restored = CanonicalDocument.model_validate_json(document.model_dump_json())
    assert restored == document
    assert token.center_y == 7.0


def test_canonical_statement_requires_source_refs() -> None:
    with pytest.raises(ValidationError):
        CanonicalStatement(
            statement_id="stmt-1",
            filing_version_id="fv-1",
            statement_type=StatementType.INCOME_STATEMENT,
            pages=(1,),
            source_refs=(),
        )
    cell = StatementCell(
        cell_id="cell-1",
        row_id="row-1",
        column_id="col-1",
        raw_text="1,234",
        parsed_numeric_value=Decimal("1234"),
        source_ref=source_ref(),
    )
    statement = CanonicalStatement(
        statement_id="stmt-1",
        filing_version_id="fv-1",
        statement_type=StatementType.INCOME_STATEMENT,
        pages=(1,),
        columns=(StatementColumn(column_id="col-1"),),
        source_refs=(source_ref(),),
    )
    assert statement.columns[0].confidence is None
    assert cell.source_ref.page_number == 1


def test_v2_package_does_not_use_process_global_release_mode() -> None:
    root = Path(__file__).resolve().parents[3] / "src" / "cse_financial_etl" / "v2"
    forbidden = {"set_release_mode", "current_release_mode", "_release_mode"}
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Name):
                names.append(node.id)
            elif isinstance(node, ast.Attribute):
                names.append(node.attr)
            elif isinstance(node, ast.alias):
                names.extend([node.name, node.asname or ""])
            elif isinstance(node, ast.ImportFrom):
                names.extend(alias.name for alias in node.names)
            hit = forbidden.intersection(names)
            assert not hit, f"{path} references forbidden {sorted(hit)}"
