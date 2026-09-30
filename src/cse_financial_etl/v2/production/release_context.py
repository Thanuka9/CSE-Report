"""Build explicit ReleaseContext for production V2 publication."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from cse_financial_etl.config import code_version, config_hash, git_identity
from cse_financial_etl.v2.contracts.enums import ReleaseMode
from cse_financial_etl.v2.contracts.release import ReleaseContext


def source_snapshot_id(project_root: Path, as_of_date: date) -> str:
    """Identity for the market universe snapshot consumed by this run."""

    market_path = (
        project_root / "data" / "raw" / "api" / f"market_cap_{as_of_date.isoformat()}.json"
    )
    if market_path.exists():
        digest = hashlib.sha256(market_path.read_bytes()).hexdigest()
        return f"market:{digest[:16]}"
    return f"market:missing:{as_of_date.isoformat()}"


def build_production_release_context(
    project_root: Path,
    *,
    run_id: str,
    as_of_date: date,
    release_mode: str,
) -> ReleaseContext:
    """Construct the per-run ReleaseContext passed to V2 publication."""

    root = project_root.resolve()
    identity = git_identity(root)
    code_sha = (identity.commit_sha or code_version()).strip()
    mode = ReleaseMode(str(release_mode or "DRAFT").strip().upper())
    return ReleaseContext(
        generation_id=run_id,
        run_id=run_id,
        mode=mode,
        code_sha=code_sha,
        policy_hash=config_hash(root),
        source_snapshot_id=source_snapshot_id(root, as_of_date),
    )
