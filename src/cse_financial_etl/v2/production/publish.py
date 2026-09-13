"""Authoritative V2 production publication. ReleaseContext is the only authority."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact
from cse_financial_etl.v2.contracts.release import ReleaseContext
from cse_financial_etl.v2.reporting.workbook import render_workbook


def publish_production_workbook(
    *,
    release: ReleaseContext,
    source_facts: Sequence[SourceFact] = (),
    derived_facts: Sequence[DerivedFact] = (),
    destination: Path,
) -> Path:
    """Render the V2 workbook from an explicit ReleaseContext.

    This path must never call the V1 process-global release-mode setter. V1
    ``cse-etl run`` remains the production command while ``extraction.engine``
    is ``v1``.
    """

    return render_workbook(
        release=release,
        source_facts=source_facts,
        derived_facts=derived_facts,
        destination=destination,
    )
