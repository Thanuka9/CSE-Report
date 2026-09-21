"""Choose the production extraction engine. V1 extract_filing is never deleted."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.extraction.statement_extractor import ExtractedFact, extract_filing
from cse_financial_etl.v2.production.adapter import extract_filing_v2


def extract_for_production(
    pdf_path: Path,
    issuer_name: str,
    symbol: str,
    period_end: date,
    *,
    engine: str = "v1",
    issuers: dict[str, Any] | None = None,
    **kwargs: object,
) -> list[ExtractedFact]:
    """Run V1 by default until cutover. ``engine='v2'`` is the hybrid
    orchestrator: V1 baseline facts unioned with native V2 recovery, then V2
    validation, lineage and production selection.
    """

    chosen = str(engine or "v1").strip().lower()
    if chosen == "v2":
        sidecar = kwargs.pop("v2_native_sidecar", None)
        sidecar_path = sidecar if isinstance(sidecar, Path) else None
        return extract_filing_v2(
            pdf_path,
            issuer_name,
            symbol,
            period_end,
            issuers=issuers,
            v2_native_sidecar=sidecar_path,
        )
    if issuers is not None:
        kwargs = {**kwargs, "issuers": issuers}
    return extract_filing(pdf_path, issuer_name, symbol, period_end, **kwargs)  # type: ignore[arg-type]
