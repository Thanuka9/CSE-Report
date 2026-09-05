from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

MANIFESTS_DIRNAME = "manifests"
RUNS_DIRNAME = "runs"


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def run_output_dir(project_root: Path, as_of_date: str, run_id: str) -> Path:
    return project_root / "outputs" / RUNS_DIRNAME / f"{as_of_date}_{run_id}"


def preserve_current_run_folder(project_root: Path, as_of_date: str) -> Path | None:
    """Copy the latest dated outputs into a per-run folder before they are overwritten."""

    manifests_dir = project_root / "outputs" / MANIFESTS_DIRNAME
    latest = manifests_dir / f"run_manifest_{as_of_date}.json"
    if not latest.exists():
        return None
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    previous_id = str(payload.get("run_id") or "").strip()
    if not previous_id:
        return None
    destination = run_output_dir(project_root, as_of_date, previous_id)
    if destination.exists():
        return destination
    destination.mkdir(parents=True, exist_ok=True)
    mapping = {
        project_root / "outputs" / f"normalized_facts_{as_of_date}.csv": destination / "normalized_facts.csv",
        project_root / "outputs" / f"review_queue_{as_of_date}.csv": destination / "review_queue.csv",
        project_root / "outputs" / f"quarter_end_prices_{as_of_date}.csv": destination / "quarter_end_prices.csv",
        project_root / "outputs" / f"pipeline_errors_{as_of_date}.json": destination / "pipeline_errors.json",
        project_root / "outputs" / f"golden_validation_{as_of_date}.json": destination / "golden_validation.json",
        latest: destination / "run_manifest.json",
        project_root
        / "outputs"
        / "workbooks"
        / f"CSE_Financial_Snapshot_{as_of_date}.xlsx": destination / "CSE_Financial_Snapshot.xlsx",
    }
    copied = False
    for source, target in mapping.items():
        if source.exists() and source.is_file():
            shutil.copy2(source, target)
            copied = True
    return destination if copied else None


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
