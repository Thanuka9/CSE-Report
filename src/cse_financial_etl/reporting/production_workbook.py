"""Route production workbook generation by extraction engine."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path

from cse_financial_etl.config import AppConfig, load_coverage_baseline
from cse_financial_etl.reporting.excel import generate_excel
from cse_financial_etl.v2.contracts.enums import ReleaseMode
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact
from cse_financial_etl.v2.contracts.release import ReleaseContext
from cse_financial_etl.v2.production.facts_store import load_v2_publication_facts
from cse_financial_etl.v2.production.publish import publish_production_workbook
from cse_financial_etl.v2.production.release_context import build_production_release_context
from cse_financial_etl.v2.reporting.release_view import build_release_view


def resolve_extraction_engine(app_config: AppConfig, engine: str | None) -> str:
    """Resolve the extraction engine for this run (default V1 from config)."""

    chosen = str(engine or app_config.extraction_engine or "v1").strip().lower()
    if chosen not in {"v1", "v2"}:
        raise ValueError(f"extraction engine must be v1 or v2, got {chosen!r}")
    return chosen



def _assert_v2_official_completeness(
    project_root: Path,
    *,
    release: ReleaseContext,
    source_facts: Sequence[SourceFact],
    derived_facts: Sequence[DerivedFact],
) -> None:
    """Prevent a thin approved subset from masquerading as a full OFFICIAL release."""

    mode = getattr(release, "mode", None)
    if mode != ReleaseMode.OFFICIAL:
        return
    baseline = load_coverage_baseline(project_root)
    floor = int(baseline.get("min_draft_publishable") or 0)
    if floor <= 0:
        raise RuntimeError("OFFICIAL_RELEASE_FLOOR_MISSING")

    official = build_release_view(
        release=release,
        source_facts=source_facts,
        derived_facts=derived_facts,
    )
    draft_release = release.model_copy(update={"mode": ReleaseMode.DRAFT})
    draft = build_release_view(
        release=draft_release,
        source_facts=source_facts,
        derived_facts=derived_facts,
    )
    if len(draft.eligible) < floor:
        raise RuntimeError(
            "V2_DRAFT_NATIVE_COVERAGE_BELOW_FLOOR:"
            f"{len(draft.eligible)}<{floor}"
        )
    if len(official.eligible) < floor:
        raise RuntimeError(
            "V2_OFFICIAL_COVERAGE_BELOW_FLOOR:"
            f"{len(official.eligible)}<{floor}"
        )


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
        _assert_v2_official_completeness(
            project_root,
            release=release,
            source_facts=source,
            derived_facts=derived,
        )
        return publish_production_workbook(
            release=release,
            source_facts=source,
            derived_facts=derived,
            destination=destination,
        )
    return generate_excel(project_root, as_of_date, periods, run_id)
