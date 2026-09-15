"""Collect the investigation freeze: runtime, config, and registry hashes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.diagnostics.replay import collect_runtime_pin
from cse_financial_etl.v2.governance.historical_floors import HISTORICAL_MIN_DRAFT_PUBLISHABLE

INVESTIGATION_BASE_SHA = "91a9c68bf940d3d9c2a86245f127de88ad4b4b6d"
FREEZE_PATH = Path("tests/v2/universe/investigation_freeze.json")

_PINNED_FILES = (
    "uv.lock",
    "configs/app.yml",
    "configs/coverage_baseline.yml",
    "src/cse_financial_etl/v2/taxonomy/registry.py",
    "tests/v2/golden/real_filings_lock.json",
    "tests/v2/universe/locked_source_manifest.json",
)


class InvestigationFreeze(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    investigation_base_sha: str
    actual_code_sha: str
    code_sha: str
    branch: str | None = None
    working_tree_dirty: bool = False
    source_snapshot_id: str | None = None
    python_version: str
    platform: str
    uv_lock_sha256: str | None = None
    config_hash: str | None = None
    concept_registry_hash: str | None = None
    pymupdf_version: str | None = None
    tesseract_version: str | None = None
    pytesseract_version: str | None = None
    extraction_engine: str
    min_draft_publishable: int
    file_sha256: dict[str, str] = Field(default_factory=dict)
    issuer_master_sha256: str | None = None
    container_digest: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tesseract_version() -> str | None:
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    first = (result.stdout or result.stderr).splitlines()
    return first[0].strip() if first else None


def _git_identity(project_root: Path) -> tuple[str, str | None, bool, str]:
    def _run(args: list[str]) -> str:
        result = subprocess.run(
            args,
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    head = _run(["git", "rev-parse", "HEAD"]) or "unknown"
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or None
    porcelain = _run(["git", "status", "--porcelain"])
    dirty = bool(porcelain)
    if dirty:
        tree = hashlib.sha256(porcelain.encode("utf-8")).hexdigest()[:12]
        actual = f"{head}:dirty:{tree}"
    else:
        actual = head
    return head, branch, dirty, actual


def collect_investigation_freeze(project_root: Path) -> InvestigationFreeze:
    pin = collect_runtime_pin(project_root)
    head, branch, dirty, actual = _git_identity(project_root)
    app_yml = (project_root / "configs" / "app.yml").read_text(encoding="utf-8")
    engine = "v1"
    for line in app_yml.splitlines():
        if line.strip().startswith("engine:"):
            engine = line.split(":", 1)[1].strip()
            break
    hashes = {}
    for relative in _PINNED_FILES:
        digest = _file_sha256(project_root / relative)
        if digest is not None:
            hashes[relative] = digest
    issuer_master = _file_sha256(project_root / "data" / "master" / "issuer_security_master.json")
    pytesseract_version = None
    try:
        from importlib.metadata import PackageNotFoundError, version

        pytesseract_version = version("pytesseract")
    except PackageNotFoundError:
        pytesseract_version = None
    return InvestigationFreeze(
        investigation_base_sha=INVESTIGATION_BASE_SHA,
        actual_code_sha=actual,
        code_sha=head,
        branch=branch,
        working_tree_dirty=dirty,
        source_snapshot_id=hashes.get("tests/v2/universe/locked_source_manifest.json"),
        python_version=pin.python_version,
        platform=pin.platform,
        uv_lock_sha256=pin.uv_lock_sha256,
        config_hash=hashes.get("configs/app.yml"),
        concept_registry_hash=hashes.get("src/cse_financial_etl/v2/taxonomy/registry.py"),
        pymupdf_version=pin.pymupdf_version,
        tesseract_version=_tesseract_version(),
        pytesseract_version=pytesseract_version,
        extraction_engine=engine,
        min_draft_publishable=HISTORICAL_MIN_DRAFT_PUBLISHABLE,
        file_sha256=hashes,
        issuer_master_sha256=issuer_master,
        container_digest=os.environ.get("CONTAINER_DIGEST") or os.environ.get("IMAGE_DIGEST"),
        extra=dict(pin.extra),
    )


def freeze_run_identity(freeze: InvestigationFreeze, *, run_id: str) -> dict[str, str]:
    """Identity columns stamped on every canonical investigation artefact."""

    return {
        "run_id": run_id,
        "investigation_base_sha": freeze.investigation_base_sha,
        "actual_code_sha": freeze.actual_code_sha,
        "source_snapshot_id": freeze.source_snapshot_id or "",
        "python_version": freeze.python_version,
        "platform": freeze.platform,
        "branch": freeze.branch or "",
        "working_tree_dirty": "true" if freeze.working_tree_dirty else "false",
    }


def write_investigation_freeze(
    project_root: Path,
    path: Path | None = None,
    freeze: InvestigationFreeze | None = None,
) -> Path:
    payload = freeze or collect_investigation_freeze(project_root)
    destination = path or (project_root / FREEZE_PATH)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload.model_dump(), indent=2) + "\n", encoding="utf-8")
    return destination
