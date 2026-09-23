"""Fixed-input replay skeleton. Runs in parallel with V2 and does not gate V2 start."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.diagnostics.fact_diff import FactDiffClass, diff_fact_populations
from cse_financial_etl.v2.diagnostics.serialization import (
    derived_fact_to_mapping,
    mapping_sort_key,
    source_fact_to_mapping,
)


def facts_are_deterministic(
    first: tuple[dict[str, object], ...],
    second: tuple[dict[str, object], ...],
) -> bool:
    left = tuple(sorted(first, key=mapping_sort_key))
    right = tuple(sorted(second, key=mapping_sort_key))
    return left == right


def documents_are_deterministic(left: CanonicalDocument, right: CanonicalDocument) -> bool:
    return _document_fingerprint(left) == _document_fingerprint(right)


def pipeline_results_are_deterministic(left: Any, right: Any) -> bool:
    return (
        _statement_fingerprint(left.statements) == _statement_fingerprint(right.statements)
        and _candidate_fingerprint(left.candidates) == _candidate_fingerprint(right.candidates)
        and facts_are_deterministic(
            tuple(source_fact_to_mapping(item) for item in left.source_facts),
            tuple(source_fact_to_mapping(item) for item in right.source_facts),
        )
        and tuple(derived_fact_to_mapping(item) for item in left.derived_facts)
        == tuple(derived_fact_to_mapping(item) for item in right.derived_facts)
        and [item.fact_id for item in left.production_selected_source]
        == [item.fact_id for item in right.production_selected_source]
        and [item.fact_id for item in left.production_selected_derived]
        == [item.fact_id for item in right.production_selected_derived]
        and [item.candidate_id for item in left.traces]
        == [item.candidate_id for item in right.traces]
        and [item.source_fact_id for item in left.traces]
        == [item.source_fact_id for item in right.traces]
        and [item.first_failure_stage for item in left.traces]
        == [item.first_failure_stage for item in right.traces]
        and [item.production_selected for item in left.traces]
        == [item.production_selected for item in right.traces]
        and [item.production_selection_reason for item in left.traces]
        == [item.production_selection_reason for item in right.traces]
    )


def _candidate_fingerprint(candidates: tuple[Any, ...]) -> tuple[object, ...]:
    return tuple(
        (
            item.candidate_id,
            item.cell_id,
            item.entity_scope,
            item.period_end,
            item.duration_months,
            item.comparison_role,
            item.currency,
            item.monetary_scale,
            item.unit_dimension,
            item.reason_codes,
        )
        for item in candidates
    )


def _document_fingerprint(document: CanonicalDocument) -> tuple[object, ...]:
    return (
        document.source_sha256,
        tuple(
            (
                page.page_number,
                page.extraction_mode.value,
                tuple(
                    (token.text, token.bbox)
                    for line in page.lines
                    for token in line.tokens
                ),
            )
            for page in document.pages
        ),
    )


def _statement_fingerprint(statements: tuple[Any, ...]) -> tuple[object, ...]:
    rows = []
    for statement in statements:
        rows.append(
            (
                statement.statement_id,
                statement.statement_type.value,
                tuple(column.column_id for column in statement.columns),
                tuple(
                    (
                        row.row_id,
                        tuple((cell.cell_id, cell.raw_text) for cell in row.cells),
                    )
                    for row in statement.rows
                ),
            )
        )
    return tuple(rows)


class RuntimePin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    code_sha: str
    python_version: str
    platform: str
    uv_lock_sha256: str | None = None
    pymupdf_version: str | None = None
    pdfplumber_version: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _git_sha(project_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip()


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def collect_runtime_pin(project_root: Path) -> RuntimePin:
    return RuntimePin(
        code_sha=_git_sha(project_root),
        python_version=sys.version.split()[0],
        platform=f"{platform.system()}-{platform.release()}-{platform.machine()}",
        uv_lock_sha256=_file_sha256(project_root / "uv.lock"),
        pymupdf_version=_package_version("PyMuPDF"),
        pdfplumber_version=_package_version("pdfplumber"),
        extra={
            "implementation": platform.python_implementation(),
        },
    )


def replay_fact_diff(
    reference_facts: tuple[dict[str, object], ...],
    current_facts: tuple[dict[str, object], ...],
) -> dict[str, int]:
    counts = diff_fact_populations(reference_facts, current_facts)
    return {cls.value: count for cls, count in counts.items()}


__all__ = [
    "FactDiffClass",
    "RuntimePin",
    "collect_runtime_pin",
    "documents_are_deterministic",
    "facts_are_deterministic",
    "pipeline_results_are_deterministic",
    "replay_fact_diff",
]
