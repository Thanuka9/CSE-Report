"""V2 run identity. Replay and publication consume this, not process globals."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.release import ReleaseContext


class RunManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    release: ReleaseContext
    python_version: str
    platform: str
    uv_lock_sha256: str | None = None
    pymupdf_version: str | None = None
    extra: dict[str, str] = {}
