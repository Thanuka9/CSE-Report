"""Route production workbook generation by extraction engine."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path

from cse_financial_etl.config import AppConfig
from cse_financial_etl.reporting.excel import generate_excel
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact
from cse_financial_etl.v2.production.facts_store import load_v2_publication_facts
from cse_financial_etl.v2.production.publish import publish_production_workbook
from cse_financial_etl.v2.production.release_context import build_production_release_context


def resolve_extraction_engine(app_config: AppConfig, engine: str | None) -> str:
    """Resolve the extraction engine for this run (default V1 from config)."""

    chosen = str(engine or app_config.extraction_engine or "v1").strip().lower()
    if chosen not in {"v1", "v2"}:
        raise ValueError(f"extraction engine must be v1 or v2, got {chosen!r}")
    return chosen


def generate_production_workbook(
    project_root: Path,
    as_of_date: date,
    periods: Iterable[date],
    run_id: str,
    *,
    engine: str,
    app_config: AppConfig,
    v2_source_facts: Sequence[SourceFact] | None = None,
    v2_derived_facts: Sequence[DerivedFact] | None = None,
) -> Path:
    """Generate the governed workbook for the active extraction engine."""

    chosen = resolve_extraction_engine(app_config, engine)
    if chosen == "v2":
        source = (
            tuple(v2_source_facts)
            if v2_source_facts is not None
            else load_v2_publication_facts(project_root, as_of_date)[0]
        )
        derived = (
            tuple(v2_derived_facts)
            if v2_derived_facts is not None
            else load_v2_publication_facts(project_root, as_of_date)[1]
        )
        release = build_production_release_context(
            project_root,
            run_id=run_id,
            as_of_date=as_of_date,
            release_mode=app_config.release_mode,
        )
        workbook_dir = project_root.resolve() / "outputs" / "workbooks"
        workbook_dir.mkdir(parents=True, exist_ok=True)
        destination = workbook_dir / f"CSE_Financial_Snapshot_{as_of_date.isoformat()}.xlsx"
        return publish_production_workbook(
            release=release,
            source_facts=source,
            derived_facts=derived,
            destination=destination,
        )
    return generate_excel(project_root, as_of_date, periods, run_id)
