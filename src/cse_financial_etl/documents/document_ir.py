from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TokenIR:
    text: str
    page_number: int
    x0: float
    y0: float
    x1: float
    y1: float
    block_no: int | None = None
    line_no: int | None = None
    word_no: int | None = None
    source: str = "PYMUPDF"

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2.0


@dataclass(frozen=True)
class TextBlockIR:
    text: str
    page_number: int
    x0: float
    y0: float
    x1: float
    y1: float
    source: str = "PYMUPDF"


@dataclass
class PageIR:
    page_number: int
    width: float
    height: float
    tokens: list[TokenIR] = field(default_factory=list)
    blocks: list[TextBlockIR] = field(default_factory=list)
    text: str = ""
    source: str = "PYMUPDF"


@dataclass
class DocumentIR:
    pdf_path: Path
    pages: list[PageIR]
    extraction_method: str
    quality_score: float
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()


def _pymupdf_pages(pdf_path: Path) -> list[PageIR] | None:
    try:
        import fitz
    except ImportError:
        return None

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None

    pages: list[PageIR] = []
    try:
        for index, page in enumerate(doc, start=1):
            tokens: list[TokenIR] = []
            try:
                words = page.get_text("words", sort=False)
            except Exception:
                words = []
            for word in words:
                if len(word) < 5:
                    continue
                text = _normalize_text(str(word[4]))
                if not text:
                    continue
                tokens.append(
                    TokenIR(
                        text=text,
                        page_number=index,
                        x0=float(word[0]),
                        y0=float(word[1]),
                        x1=float(word[2]),
                        y1=float(word[3]),
                        block_no=int(word[5]) if len(word) > 5 else None,
                        line_no=int(word[6]) if len(word) > 6 else None,
                        word_no=int(word[7]) if len(word) > 7 else None,
                    )
                )

            blocks: list[TextBlockIR] = []
            try:
                raw_blocks = page.get_text("blocks", sort=False)
            except Exception:
                raw_blocks = []
            for block in raw_blocks:
                if len(block) < 5:
                    continue
                text = _normalize_text(str(block[4]))
                if not text:
                    continue
                blocks.append(
                    TextBlockIR(
                        text=text,
                        page_number=index,
                        x0=float(block[0]),
                        y0=float(block[1]),
                        x1=float(block[2]),
                        y1=float(block[3]),
                    )
                )

            try:
                page_text = page.get_text("text", sort=True)
            except Exception:
                page_text = "\n".join(block.text for block in blocks)

            pages.append(
                PageIR(
                    page_number=index,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    tokens=tokens,
                    blocks=blocks,
                    text=page_text,
                    source="PYMUPDF",
                )
            )
    finally:
        doc.close()
    return pages


def _pdfplumber_pages(pdf_path: Path) -> list[PageIR] | None:
    try:
        import pdfplumber
    except ImportError:
        return None

    pages: list[PageIR] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                tokens: list[TokenIR] = []
                for word in page.extract_words() or []:
                    text = _normalize_text(str(word.get("text") or ""))
                    if not text:
                        continue
                    tokens.append(
                        TokenIR(
                            text=text,
                            page_number=index,
                            x0=float(word.get("x0") or 0.0),
                            y0=float(word.get("top") or 0.0),
                            x1=float(word.get("x1") or 0.0),
                            y1=float(word.get("bottom") or 0.0),
                            source="PDFPLUMBER",
                        )
                    )
                text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
                pages.append(
                    PageIR(
                        page_number=index,
                        width=float(page.width),
                        height=float(page.height),
                        tokens=tokens,
                        blocks=[],
                        text=text,
                        source="PDFPLUMBER",
                    )
                )
    except Exception:
        return None
    return pages


def _quality(pages: list[PageIR]) -> tuple[float, dict[str, Any]]:
    if not pages:
        return 0.0, {"page_count": 0, "token_count": 0, "numeric_count": 0}
    token_count = sum(len(page.tokens) for page in pages)
    numeric_count = sum(
        1
        for page in pages
        for token in page.tokens
        if re.search(r"\d", token.text)
    )
    character_count = sum(len(page.text) for page in pages)
    bad_character_count = sum(
        page.text.count("�") + page.text.count("\x00") for page in pages
    )
    token_component = min(1.0, token_count / max(1.0, len(pages) * 50.0))
    numeric_component = min(1.0, numeric_count / max(1.0, len(pages) * 5.0))
    text_component = min(1.0, character_count / max(1.0, len(pages) * 1000.0))
    corruption_penalty = min(0.5, bad_character_count / max(1.0, character_count))
    score = max(
        0.0,
        min(
            1.0,
            0.45 * token_component + 0.25 * numeric_component + 0.30 * text_component - corruption_penalty,
        ),
    )
    return score, {
        "page_count": len(pages),
        "token_count": token_count,
        "numeric_count": numeric_count,
        "character_count": character_count,
        "bad_character_count": bad_character_count,
    }


def _ocr_pdf(pdf_path: Path, temp_dir: Path) -> Path | None:
    if os.getenv("CSE_ETL_DISABLE_OCR", "").lower() in {"1", "true", "yes"}:
        return None
    output = temp_dir / f"{pdf_path.stem}.ocr.pdf"
    try:
        subprocess.run(
            [
                "ocrmypdf",
                "--skip-text",
                "--deskew",
                "--clean",
                str(pdf_path),
                str(output),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=240,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    return output if output.exists() and output.stat().st_size > 0 else None


def _docling_to_pages(document: Any) -> list[PageIR]:
    pages: list[PageIR] = []
    page_map: dict[int, PageIR] = {}
    for item, _level in document.iterate_items():
        prov = getattr(item, "prov", None) or []
        text = _normalize_text(str(getattr(item, "text", "") or ""))
        if not text:
            continue
        for origin in prov:
            page_number = int(getattr(origin, "page_no", 1) or 1)
            bbox = getattr(origin, "bbox", None)
            if bbox is None:
                continue
            page = page_map.setdefault(
                page_number,
                PageIR(
                    page_number=page_number,
                    width=0.0,
                    height=0.0,
                    source="DOCLING",
                ),
            )
            token = TokenIR(
                text=text,
                page_number=page_number,
                x0=float(getattr(bbox, "l", 0.0)),
                y0=float(getattr(bbox, "t", 0.0)),
                x1=float(getattr(bbox, "r", 0.0)),
                y1=float(getattr(bbox, "b", 0.0)),
                source="DOCLING",
            )
            page.tokens.append(token)
            page.blocks.append(
                TextBlockIR(
                    text=text,
                    page_number=page_number,
                    x0=token.x0,
                    y0=token.y0,
                    x1=token.x1,
                    y1=token.y1,
                    source="DOCLING",
                )
            )
    for page_number in sorted(page_map):
        page = page_map[page_number]
        page.text = "\n".join(block.text for block in page.blocks)
        pages.append(page)
    return pages


def _extract_docling_pages(pdf_path: Path) -> list[PageIR] | None:
    """Optional complex-layout engine. Never required; skipped if Docling is absent."""

    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        return None
    try:
        converted = DocumentConverter().convert(str(pdf_path))
        document = converted.document
    except Exception:
        return None
    pages = _docling_to_pages(document)
    return pages or None


def build_document_ir(pdf_path: Path, temp_dir: Path | None = None) -> DocumentIR:
    temp_dir = temp_dir or pdf_path.parent / ".tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    methods: list[tuple[str, list[PageIR] | None]] = [
        ("PYMUPDF", _pymupdf_pages(pdf_path)),
    ]
    best_method = "PYMUPDF"
    best_pages = methods[0][1] or []
    best_score, best_diag = _quality(best_pages)

    if best_score < 0.72:
        plumber_pages = _pdfplumber_pages(pdf_path)
        methods.append(("PDFPLUMBER", plumber_pages))
        score, diag = _quality(plumber_pages or [])
        if score > best_score:
            best_method, best_pages, best_score, best_diag = "PDFPLUMBER", plumber_pages or [], score, diag

    if best_score < 0.58:
        docling_pages = _extract_docling_pages(pdf_path)
        methods.append(("DOCLING", docling_pages))
        score, diag = _quality(docling_pages or [])
        if score > best_score:
            best_method, best_pages, best_score, best_diag = "DOCLING", docling_pages or [], score, diag

    if best_score < 0.45:
        ocr_path = _ocr_pdf(pdf_path, temp_dir)
        if ocr_path:
            ocr_pages = _pymupdf_pages(ocr_path) or _pdfplumber_pages(ocr_path) or []
            score, diag = _quality(ocr_pages)
            if score > best_score:
                best_method, best_pages, best_score, best_diag = "OCR", ocr_pages, score, diag

    return DocumentIR(
        pdf_path=pdf_path,
        pages=best_pages,
        extraction_method=best_method,
        quality_score=best_score,
        diagnostics={
            "quality": best_diag,
            "attempted_methods": [name for name, _pages in methods],
        },
    )


def write_document_diagnostics(document: DocumentIR, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pdf_path": str(document.pdf_path),
        "extraction_method": document.extraction_method,
        "quality_score": document.quality_score,
        "diagnostics": document.diagnostics,
        "pages": [
            {
                "page_number": page.page_number,
                "width": page.width,
                "height": page.height,
                "source": page.source,
                "token_count": len(page.tokens),
                "block_count": len(page.blocks),
            }
            for page in document.pages
        ],
    }
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
