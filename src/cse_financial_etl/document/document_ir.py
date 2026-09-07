"""Canonical raw document IR (Revision 2 §7)."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cse_financial_etl.documents import document_ir as legacy


@dataclass(frozen=True, slots=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True, slots=True)
class TokenIR:
    text: str
    bbox: BBox
    page_number: int
    font_name: str | None = None
    font_size: float | None = None
    is_bold: bool | None = None
    source_method: str = "native"


@dataclass(frozen=True, slots=True)
class LineIR:
    tokens: tuple[TokenIR, ...]
    bbox: BBox
    text: str
    page_number: int = 1
    line_id: str = ""


@dataclass(frozen=True, slots=True)
class TableCellIR:
    row_idx: int
    col_idx: int
    raw_text: str
    bbox: BBox
    rowspan: int = 1
    colspan: int = 1


@dataclass(frozen=True, slots=True)
class TableIR:
    page_number: int
    bbox: BBox
    cells: tuple[TableCellIR, ...]
    header_rows: tuple[int, ...] = ()
    source_method: str = "geometry"


@dataclass(frozen=True, slots=True)
class PageIR:
    page_number: int
    width: float
    height: float
    tokens: tuple[TokenIR, ...]
    lines: tuple[LineIR, ...]
    tables: tuple[TableIR, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentQuality:
    page_count: int
    token_count: int
    numeric_token_count: int
    text_page_ratio: float
    extraction_method: str
    requires_ocr: bool
    reconstruction_gaps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CanonicalDocumentIR:
    pages: tuple[PageIR, ...]
    quality: DocumentQuality
    source_sha256: str
    source_path: str = ""

    def evidence_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "quality": asdict(self.quality),
            "pages": [
                {
                    "page": page.page_number,
                    "width": page.width,
                    "height": page.height,
                    "line_count": len(page.lines),
                    "table_count": len(page.tables),
                    "token_count": len(page.tokens),
                }
                for page in self.pages
            ],
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def from_legacy_document_ir(
    document: legacy.DocumentIR,
    *,
    source_method: str = "native",
    source_sha256: str | None = None,
) -> CanonicalDocumentIR:
    """Adapt the existing DocumentIR into Revision 2 CanonicalDocumentIR."""

    pages: list[PageIR] = []
    for page in document.pages:
        tokens: list[TokenIR] = []
        lines: list[LineIR] = []
        for line in page.lines:
            line_tokens = tuple(
                TokenIR(
                    text=token.text,
                    bbox=BBox(token.bbox.x0, token.bbox.y0, token.bbox.x1, token.bbox.y1),
                    page_number=page.number,
                    source_method=source_method,
                )
                for token in line.tokens
            )
            tokens.extend(line_tokens)
            lines.append(
                LineIR(
                    tokens=line_tokens,
                    bbox=BBox(line.bbox.x0, line.bbox.y0, line.bbox.x1, line.bbox.y1),
                    text=line.text,
                    page_number=page.number,
                    line_id=line.line_id,
                )
            )
        pages.append(
            PageIR(
                page_number=page.number,
                width=page.width,
                height=page.height,
                tokens=tuple(tokens),
                lines=tuple(lines),
            )
        )
    quality = DocumentQuality(
        page_count=document.quality.page_count,
        token_count=document.quality.token_count,
        numeric_token_count=document.quality.numeric_token_count,
        text_page_ratio=document.quality.text_page_ratio,
        extraction_method=document.quality.extraction_method,
        requires_ocr=document.quality.requires_ocr,
    )
    digest = source_sha256
    if digest is None:
        path = Path(document.source_path)
        digest = sha256_file(path) if path.exists() else ""
    return CanonicalDocumentIR(
        pages=tuple(pages),
        quality=quality,
        source_sha256=digest,
        source_path=document.source_path,
    )
