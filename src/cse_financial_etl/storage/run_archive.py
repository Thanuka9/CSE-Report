from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

MANIFESTS_DIRNAME = "manifests"


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def archive_existing(path: Path, archive_dir: Path, stamp: str) -> Path | None:
    """Copy an existing artifact aside before the next run overwrites it."""

    if not path.exists() or not path.is_file():
        return None
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, destination)
    return destination


def archive_pipeline_artifacts(project_root: Path, as_of_date: str, stamp: str) -> list[Path]:
    """Preserve the previous market snapshot and output files for the same as-of date."""

    archived: list[Path] = []
    as_of = as_of_date
    market_path = project_root / "data" / "raw" / "api" / f"market_cap_{as_of}.json"
    copied = archive_existing(market_path, project_root / "data" / "raw" / "api" / "history", stamp)
    if copied is not None:
        archived.append(copied)
    archive_dir = project_root / "outputs" / "archive"
    for folder in (project_root / "outputs", project_root / "outputs" / "workbooks"):
        copied = archive_existing(folder / f"CSE_Financial_Snapshot_{as_of}.xlsx", archive_dir, stamp)
        if copied is not None:
            archived.append(copied)
    output_names = (
        f"normalized_facts_{as_of}.csv",
        f"review_queue_{as_of}.csv",
        f"quarter_end_prices_{as_of}.csv",
        f"pipeline_errors_{as_of}.json",
        f"golden_validation_{as_of}.json",
    )
    for name in output_names:
        copied = archive_existing(project_root / "outputs" / name, archive_dir, stamp)
        if copied is not None:
            archived.append(copied)
    manifests_dir = project_root / "outputs" / MANIFESTS_DIRNAME
    copied = archive_existing(manifests_dir / f"run_manifest_{as_of}.json", archive_dir, stamp)
    if copied is not None:
        archived.append(copied)
    leftover = project_root / "outputs" / f"run_manifest_{as_of}.json"
    copied = archive_existing(leftover, archive_dir, stamp)
    if copied is not None:
        archived.append(copied)
    return archived
