"""Collect the investigation freeze: runtime, config, and registry hashes."""

from __future__ import annotations

import hashlib
import json
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
)


class InvestigationFreeze(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    investigation_base_sha: str
    code_sha: str
    python_version: str
    platform: str
    uv_lock_sha256: str | None = None
    pymupdf_version: str | None = None
    tesseract_version: str | None = None
    pytesseract_version: str | None = None
    extraction_engine: str
    min_draft_publishable: int
    file_sha256: dict[str, str] = Field(default_factory=dict)
    issuer_master_sha256: str | None = None
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


def collect_investigation_freeze(project_root: Path) -> InvestigationFreeze:
    pin = collect_runtime_pin(project_root)
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
        code_sha=pin.code_sha,
        python_version=pin.python_version,
        platform=pin.platform,
        uv_lock_sha256=pin.uv_lock_sha256,
        pymupdf_version=pin.pymupdf_version,
        tesseract_version=_tesseract_version(),
        pytesseract_version=pytesseract_version,
        extraction_engine=engine,
        min_draft_publishable=HISTORICAL_MIN_DRAFT_PUBLISHABLE,
        file_sha256=hashes,
        issuer_master_sha256=issuer_master,
        extra=dict(pin.extra),
    )


def write_investigation_freeze(project_root: Path, path: Path | None = None) -> Path:
    freeze = collect_investigation_freeze(project_root)
    destination = path or (project_root / FREEZE_PATH)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(freeze.model_dump(), indent=2) + "\n", encoding="utf-8")
    return destination
