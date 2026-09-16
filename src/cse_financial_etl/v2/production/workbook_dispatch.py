"""Select the production workbook publisher by extraction engine.

V1 remains the default. When ``extraction.engine`` is ``v2`` (opt-in or after
OFFICIAL promotion), ``publish_production_workbook`` + explicit ``ReleaseContext``
is the only authoritative workbook path.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from cse_financial_etl.v2.contracts.enums import ReleaseMode
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact
from cse_financial_etl.v2.contracts.release import ReleaseContext
from cse_financial_etl.v2.production.publish import publish_production_workbook


def resolve_extraction_engine(configured: str | None, override: str | None = None) -> str:
    chosen = str(override or configured or "v1").strip().lower()
    if chosen not in {"v1", "v2"}:
        raise ValueError(f"extraction engine must be v1 or v2, got {chosen!r}")
    return chosen


def publish_for_engine(
    *,
    engine: str,
    release: ReleaseContext | None = None,
    source_facts: Sequence[SourceFact] = (),
    derived_facts: Sequence[DerivedFact] = (),
    destination: Path,
    v1_publisher: Callable[[], Path] | None = None,
) -> Path:
    """Dispatch workbook rendering. Never promotes V2; caller chooses engine."""

    chosen = resolve_extraction_engine(engine)
    if chosen == "v1":
        if v1_publisher is None:
            raise ValueError("v1 workbook rendering requires v1_publisher")
        return v1_publisher()
    if release is None:
        raise ValueError("V2 workbook rendering requires an explicit ReleaseContext")
    if release.mode is ReleaseMode.OFFICIAL and not source_facts and not derived_facts:
        # Fail closed: OFFICIAL empty books are not a silent success path.
        raise ValueError("V2 OFFICIAL workbook requires source or derived facts")
    return publish_production_workbook(
        release=release,
        source_facts=source_facts,
        derived_facts=derived_facts,
        destination=destination,
    )
