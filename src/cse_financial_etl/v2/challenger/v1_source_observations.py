"""Collect PDF-anchored source observations via V1 native geometry + table reconstructor.

Does **not** call V1 publication, KnownContext fills, or issuer-specific patches.
Outputs are challenger-only inputs for V2 verification.
"""

from __future__ import annotations

from pathlib import Path

from cse_financial_etl.document.table_reconstructor import reconstruct_tables
from cse_financial_etl.ingestion.native_cache import cached_native_document
from cse_financial_etl.v2.challenger.models import V1SourceObservation
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.statements.numeric import parse_numeric

READER_ID = "v1_physical_table_reconstructor"
READER_VERSION = "1"


def collect_v1_source_observations(
    pdf_path: Path,
    *,
    filing_version_id: str,
    filing_id: str | None = None,
) -> tuple[V1SourceObservation, ...]:
    """Return cell-level observations with SourceRef anchoring to the PDF SHA."""

    path = Path(pdf_path)
    document = reconstruct_tables(cached_native_document(path))
    sha = document.source_sha256
    fid = (filing_id or filing_version_id).strip() or filing_version_id
    out: list[V1SourceObservation] = []

    for page in document.pages:
        for table_index, table in enumerate(page.tables):
            table_id = f"p{page.page_number:04d}-t{table_index:02d}"
            # Build row labels from LABEL-kind cells when present.
            label_by_row: dict[int, str] = {}
            for cell in table.cells:
                if cell.col_idx == 0 and (cell.raw_text or "").strip():
                    label_by_row[cell.row_idx] = cell.raw_text.strip()
            for cell in table.cells:
                if cell.col_idx == 0:
                    continue
                raw = (cell.raw_text or "").strip()
                if not raw:
                    continue
                value = parse_numeric(raw)
                if value is None:
                    continue
                label = label_by_row.get(cell.row_idx, "")
                bbox = (cell.bbox.x0, cell.bbox.y0, cell.bbox.x1, cell.bbox.y1)
                reasons: list[str] = [
                    "V1_PHYSICAL_OBSERVATION",
                    "CONTEXT_UNRESOLVED_PENDING_V2_VERIFY",
                    "DISCOVERY_ONLY",
                ]
                obs_id = f"{table_id}-r{cell.row_idx}-c{cell.col_idx}"
                out.append(
                    V1SourceObservation(
                        observation_id=obs_id,
                        reader_id=READER_ID,
                        reader_version=READER_VERSION,
                        source_ref=SourceRef(
                            filing_id=fid,
                            filing_version_id=filing_version_id,
                            source_sha256=sha,
                            page_number=page.page_number,
                            bbox=bbox,
                            raw_text=raw if not label else f"{label} | {raw}",
                            parser_name=READER_ID,
                            parser_version=READER_VERSION,
                        ),
                        statement_hint=_hint_from_titles(table.title_texts),
                        table_id=table_id,
                        row_index=cell.row_idx,
                        col_index=cell.col_idx,
                        row_label=label,
                        raw_text=raw,
                        raw_value=value,
                        publishable=False,
                        reason_codes=tuple(reasons),
                        evidence_notes=("raw_cell_only",),
                    )
                )
    return tuple(out)


def _hint_from_titles(titles: tuple[str, ...]) -> str | None:
    if not titles:
        return None
    blob = " ".join(titles).casefold()
    if "profit" in blob or "income" in blob or "comprehensive" in blob:
        return "INCOME_STATEMENT"
    if "financial position" in blob or "balance" in blob:
        return "BALANCE_SHEET"
    if "cash flow" in blob:
        return "CASH_FLOW"
    if "equity" in blob and "change" in blob:
        return "CHANGES_IN_EQUITY"
    return None
