"""Single canonical document representation used by every V2 downstream module."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.contracts.provenance import BBox, union_bbox


class CanonicalToken(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    text: str
    page_number: int
    bbox: BBox
    confidence: float | None = None
    source_parser: str

    @field_validator("text", "source_parser")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("token text and source_parser must be non-empty")
        return value

    @field_validator("page_number")
    @classmethod
    def _page_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page_number must be >= 1")
        return value

    @property
    def center_y(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2.0


class CanonicalLine(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    line_id: str
    tokens: tuple[CanonicalToken, ...]
    bbox: BBox

    @field_validator("line_id")
    @classmethod
    def _line_id_present(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("line_id must be non-empty")
        return value

    @field_validator("tokens")
    @classmethod
    def _tokens_present(cls, value: tuple[CanonicalToken, ...]) -> tuple[CanonicalToken, ...]:
        if not value:
            raise ValueError("a canonical line must contain at least one token")
        return value

    @property
    def text(self) -> str:
        return " ".join(token.text for token in self.tokens)


class CanonicalPage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    page_number: int
    width: float
    height: float
    lines: tuple[CanonicalLine, ...]
    extraction_mode: ExtractionMode

    @field_validator("page_number")
    @classmethod
    def _page_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page_number must be >= 1")
        return value

    @field_validator("width", "height")
    @classmethod
    def _positive_dimension(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("page width and height must be positive")
        return value


class CanonicalDocument(BaseModel):
    """Exactly one canonical document IR for native, OCR, and hybrid parsers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    filing_version_id: str
    source_sha256: str
    pages: tuple[CanonicalPage, ...]
    parser_manifest: dict[str, str] = Field(default_factory=dict)

    @field_validator("filing_version_id")
    @classmethod
    def _filing_present(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("filing_version_id must be non-empty")
        return stripped

    @field_validator("source_sha256")
    @classmethod
    def _sha256_hex(cls, value: str) -> str:
        digest = value.strip().lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("source_sha256 must be a 64-character lowercase hex digest")
        return digest

    @field_validator("pages")
    @classmethod
    def _pages_present(cls, value: tuple[CanonicalPage, ...]) -> tuple[CanonicalPage, ...]:
        if not value:
            raise ValueError("CanonicalDocument must contain at least one page")
        numbers = [page.page_number for page in value]
        if numbers != list(range(1, len(value) + 1)):
            raise ValueError("pages must be ordered as 1..N with no gaps")
        return value


def line_bbox_from_tokens(tokens: tuple[CanonicalToken, ...]) -> BBox:
    return union_bbox(tuple(token.bbox for token in tokens))
