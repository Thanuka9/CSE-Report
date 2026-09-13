"""Explicit release context. V2 must never use process-global release mode."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import ReleaseMode
from cse_financial_etl.v2.exceptions import ReleaseContextRequiredError


class ReleaseContext(BaseModel):
    """Per-generation release identity passed explicitly through V2 publication."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    generation_id: str
    run_id: str
    mode: ReleaseMode
    code_sha: str
    policy_hash: str
    source_snapshot_id: str

    @field_validator("generation_id", "run_id", "code_sha", "policy_hash", "source_snapshot_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("ReleaseContext fields must be non-empty")
        return stripped


def require_release_context(release: ReleaseContext | None) -> ReleaseContext:
    """Fail closed if a V2 publication path is invoked without explicit context."""

    if release is None:
        raise ReleaseContextRequiredError(
            "V2 publication requires an explicit ReleaseContext; "
            "process-global release mode is not authoritative"
        )
    return release
