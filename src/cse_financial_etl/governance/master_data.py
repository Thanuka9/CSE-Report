"""File-based issuer/security master construction.

No database is required. The generated master is a versioned JSON artifact keyed by a
stable local issuer_id and exact CSE security_id/symbol pairs. Names are attributes,
not downstream join keys.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.config import IssuerProfile, infer_issuer_type, load_issuers
from cse_financial_etl.governance.regulatory_policy import canonical_issuer_id


def build_master_records(
    market_rows: list[dict[str, Any]],
    configured: dict[str, IssuerProfile],
    *,
    as_of_date: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    display_name: dict[str, str] = {}
    for row in market_rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("company_name") or row.get("name") or "").strip()
        symbol = str(row.get("symbol") or "").strip()
        security_id = row.get("security_id", row.get("id"))
        if not name or not symbol or security_id in (None, ""):
            continue
        key = " ".join(name.upper().split())
        display_name.setdefault(key, name)
        grouped[key].append(
            {
                "security_id": int(security_id),
                "symbol": symbol,
                "security_class": row.get("security_class"),
                "voting_flag": row.get("voting_flag"),
                "trading_currency": row.get("trading_currency"),
                "active": True,
            }
        )

    records: list[dict[str, Any]] = []
    for key in sorted(grouped):
        name = display_name[key]
        profile = configured.get(name.casefold())
        issuer_type = profile.issuer_type if profile else infer_issuer_type(name)
        issuer_id = canonical_issuer_id(name, profile.issuer_id if profile else None)
        records.append(
            {
                "issuer_id": issuer_id,
                "legal_name": name,
                "issuer_type": issuer_type,
                "standalone_scope_label": (
                    profile.standalone_scope_label
                    if profile
                    else "BANK"
                    if issuer_type == "BANK"
                    else "COMPANY"
                ),
                "listing_segment": getattr(profile, "listing_segment", None) if profile else None,
                "reporting_currency": getattr(profile, "reporting_currency", None) if profile else None,
                "fiscal_year_end_month": profile.fiscal_year_end_month if profile else None,
                "classification_source": "CONFIGURED" if profile else "DETERMINISTIC_INFERENCE",
                "identity_source": "CONFIGURED" if profile else "LOCAL_STABLE_HASH",
                "as_of_date": as_of_date,
                "securities": sorted(
                    grouped[key], key=lambda item: (item["symbol"], item["security_id"])
                ),
            }
        )
    return records


def write_canonical_issuer_master(project_root: Path, as_of_date: date) -> Path:
    """Build the production issuer/security master from the captured CSE universe."""

    market_path = (
        project_root / "data" / "raw" / "api" / f"market_cap_{as_of_date.isoformat()}.json"
    )
    payload = json.loads(market_path.read_text(encoding="utf-8")) if market_path.exists() else []
    rows = payload if isinstance(payload, list) else []
    records = build_master_records(
        rows,
        load_issuers(project_root),
        as_of_date=as_of_date.isoformat(),
    )
    destination = project_root / "outputs" / f"issuer_master_{as_of_date.isoformat()}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return destination
