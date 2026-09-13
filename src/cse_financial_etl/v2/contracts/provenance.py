"""Source-bound provenance. No source fact may exist without a SourceRef."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from cse_financial_etl.v2 import SCHEMA_VERSION

BBox = tuple[float, float, float, float]


class SourceRef(BaseModel):
    """Immutable pointer to the exact filing evidence that produced an object."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    filing_id: str
    filing_version_id: str
    source_sha256: str
    page_number: int
    bbox: BBox | None = None
    raw_text: str | None = None
    parser_name: str
    parser_version: str

    @field_validator(
        "filing_id", "filing_version_id", "source_sha256", "parser_name", "parser_version"
    )
    @classmethod
    def _non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("source reference fields must be non-empty")
        return stripped

    @field_validator("page_number")
    @classmethod
    def _page_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page_number must be >= 1")
        return value

    @field_validator("source_sha256")
    @classmethod
    def _sha256_hex(cls, value: str) -> str:
        digest = value.strip().lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("source_sha256 must be a 64-character lowercase hex digest")
        return digest

    @field_validator("bbox")
    @classmethod
    def _bbox_ordered(cls, value: BBox | None) -> BBox | None:
        if value is None:
            return value
        x0, y0, x1, y1 = value
        if x1 < x0 or y1 < y0:
            raise ValueError("bbox must have x1 >= x0 and y1 >= y0")
        return (float(x0), float(y0), float(x1), float(y1))


def union_bbox(boxes: tuple[BBox, ...]) -> BBox:
    if not boxes:
        raise ValueError("cannot union an empty bbox sequence")
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )
