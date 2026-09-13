"""Fixed-input replay skeleton. Runs in parallel with V2 and does not gate V2 start."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.diagnostics.fact_diff import FactDiffClass, diff_fact_populations
from cse_financial_etl.v2.diagnostics.serialization import mapping_sort_key


def facts_are_deterministic(
    first: tuple[dict[str, object], ...],
    second: tuple[dict[str, object], ...],
) -> bool:
    left = tuple(sorted(first, key=mapping_sort_key))
    right = tuple(sorted(second, key=mapping_sort_key))
    return left == right


class RuntimePin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    code_sha: str
    python_version: str
    platform: str
    uv_lock_sha256: str | None = None
    pymupdf_version: str | None = None
    pdfplumber_version: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _git_sha(project_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip()


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def collect_runtime_pin(project_root: Path) -> RuntimePin:
    return RuntimePin(
        code_sha=_git_sha(project_root),
        python_version=sys.version.split()[0],
        platform=f"{platform.system()}-{platform.release()}-{platform.machine()}",
        uv_lock_sha256=_file_sha256(project_root / "uv.lock"),
        pymupdf_version=_package_version("PyMuPDF"),
        pdfplumber_version=_package_version("pdfplumber"),
        extra={
            "implementation": platform.python_implementation(),
        },
    )


def replay_fact_diff(
    reference_facts: tuple[dict[str, object], ...],
    current_facts: tuple[dict[str, object], ...],
) -> dict[str, int]:
    counts = diff_fact_populations(reference_facts, current_facts)
    return {cls.value: count for cls, count in counts.items()}


__all__ = [
    "FactDiffClass",
    "RuntimePin",
    "collect_runtime_pin",
    "facts_are_deterministic",
    "replay_fact_diff",
]
