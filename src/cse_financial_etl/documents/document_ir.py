from __future__ import annotations

import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pdfplumber
import pymupdf as fitz

NUMERIC_TOKEN_RE = re.compile(r"^\(?-?\d[\d,]*(?:\.\d+)?\)?%?$|^-$")


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
    block_no: int
    line_no: int
    word_no: int

    @property
    def is_numeric(self) -> bool:
        return NUMERIC_TOKEN_RE.fullmatch(self.text.replace(" ", "")) is not None


@dataclass(frozen=True, slots=True)
class LineIR:
    page: int
    line_id: str
    text: str
    bbox: BBox
    tokens: tuple[TokenIR, ...]

    @property
    def numeric_tokens(self) -> tuple[TokenIR, ...]:
        return tuple(token for token in self.tokens if token.is_numeric)


@dataclass(frozen=True, slots=True)
class PageIR:
    number: int
    width: float
    height: float
    lines: tuple[LineIR, ...]
    text: str


@dataclass(frozen=True, slots=True)
class DocumentQuality:
    page_count: int
    token_count: int
    numeric_token_count: int
    text_page_ratio: float
    extraction_method: str
    requires_ocr: bool


@dataclass(frozen=True, slots=True)
class DocumentIR:
    source_path: str
    pages: tuple[PageIR, ...]
    quality: DocumentQuality

    def evidence_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "quality": asdict(self.quality),
            "pages": [
                {
                    "page": page.number,
                    "width": page.width,
                    "height": page.height,
                    "line_count": len(page.lines),
                }
                for page in self.pages
            ],
        }


def _bbox(tokens: list[TokenIR]) -> BBox:
    return BBox(
        min(token.bbox.x0 for token in tokens),
        min(token.bbox.y0 for token in tokens),
        max(token.bbox.x1 for token in tokens),
        max(token.bbox.y1 for token in tokens),
    )


def _page_from_words(number: int, width: float, height: float, words: list[Any]) -> PageIR:
    """Create visual rows, not just PDF-internal text lines.

    Financial-table labels and their numeric cells are commonly emitted as separate
    PDF blocks even though they share the same visual baseline. Grouping by the PDF
    block/line identifiers therefore disconnects values from labels. A small
    baseline cluster reconstructs the row while retaining every word coordinate.
    """

    tokens: list[TokenIR] = []
    for item in words:
        if len(item) < 8:
            continue
        x0, y0, x1, y1, text, block_no, line_no, word_no = item[:8]
        token = TokenIR(
            text=str(text),
            bbox=BBox(float(x0), float(y0), float(x1), float(y1)),
            block_no=int(block_no),
            line_no=int(line_no),
            word_no=int(word_no),
        )
        tokens.append(token)

    rows: list[list[TokenIR]] = []
    row_centres: list[float] = []
    for token in sorted(tokens, key=lambda item: (item.bbox.center_y, item.bbox.x0)):
        best_index: int | None = None
        best_distance = float("inf")
        for index in range(max(0, len(rows) - 4), len(rows)):
            distance = abs(token.bbox.center_y - row_centres[index])
            tolerance = max(2.2, min(token.bbox.y1 - token.bbox.y0, 12.0) * 0.28)
            if distance <= tolerance and distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index is None:
            rows.append([token])
            row_centres.append(token.bbox.center_y)
        else:
            rows[best_index].append(token)
            row_centres[best_index] = sum(item.bbox.center_y for item in rows[best_index]) / len(
                rows[best_index]
            )

    lines: list[LineIR] = []
    for row_index, row_tokens in enumerate(rows):
        ordered = sorted(row_tokens, key=lambda token: (token.bbox.x0, token.word_no))
        lines.append(
            LineIR(
                page=number,
                line_id=f"p{number}-r{row_index}",
                text=" ".join(token.text for token in ordered),
                bbox=_bbox(ordered),
                tokens=tuple(ordered),
            )
        )
    lines.sort(key=lambda line: (round(line.bbox.y0, 1), line.bbox.x0))
    return PageIR(
        number=number,
        width=width,
        height=height,
        lines=tuple(lines),
        text="\n".join(line.text for line in lines),
    )


def _quality(pages: list[PageIR], method: str) -> DocumentQuality:
    """Measure whether a coordinate extraction is good enough for table parsing."""

    token_count = sum(len(line.tokens) for page in pages for line in page.lines)
    numeric_count = sum(
        sum(token.is_numeric for token in line.tokens) for page in pages for line in page.lines
    )
    text_pages = sum(bool(page.text.strip()) for page in pages)
    page_count = len(pages)
    text_page_ratio = text_pages / page_count if page_count else 0.0
    requires_ocr = page_count == 0 or text_page_ratio < 0.8 or token_count < page_count * 25
    return DocumentQuality(
        page_count=page_count,
        token_count=token_count,
        numeric_token_count=numeric_count,
        text_page_ratio=round(text_page_ratio, 4),
        extraction_method=method,
        requires_ocr=requires_ocr,
    )


def _extract_pdfplumber_pages(pdf_path: Path) -> list[PageIR]:
    """Use a second coordinate engine when the primary PDF reading order is sparse."""

    pages: list[PageIR] = []
    with pdfplumber.open(pdf_path) as document:
        for index, page in enumerate(document.pages, start=1):
            words: list[tuple[float, float, float, float, str, int, int, int]] = []
            for word_no, word in enumerate(page.extract_words(keep_blank_chars=False)):
                words.append(
                    (
                        float(word["x0"]),
                        float(word["top"]),
                        float(word["x1"]),
                        float(word["bottom"]),
                        str(word["text"]),
                        0,
                        0,
                        word_no,
                    )
                )
            pages.append(_page_from_words(index, float(page.width), float(page.height), words))
    return pages


def _extract_pymupdf_pages(pdf_path: Path) -> list[PageIR]:
    pages: list[PageIR] = []
    with fitz.open(pdf_path) as document:  # type: ignore[no-untyped-call]
        for index, page in enumerate(document, start=1):
            words = page.get_text("words", sort=True)
            pages.append(
                _page_from_words(index, float(page.rect.width), float(page.rect.height), words)
            )
    return pages


def _ocr_derivative(pdf_path: Path, ocr_dir: Path) -> Path | None:
    """Create a searchable OCR PDF beside the immutable original. Never overwrite source."""

    ocr_dir.mkdir(parents=True, exist_ok=True)
    destination = ocr_dir / f"{pdf_path.stem}.ocr.pdf"
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    try:
        import ocrmypdf
    except ImportError:
        return None
    if shutil.which("tesseract") is None:
        return None
    try:
        ocrmypdf.ocr(
            str(pdf_path),
            str(destination),
            skip_text=True,
            optimize=0,
            progress_bar=False,
            output_type="pdf",
        )
    except Exception:
        if destination.exists():
            destination.unlink(missing_ok=True)
        return None
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    return None


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
    pages_by_number: dict[int, list[tuple[float, float, float, float, str, int, int, int]]] = {}
    try:
        for item, _level in document.iterate_items():
            text = str(getattr(item, "text", "") or "").strip()
            if not text:
                continue
            provenance = getattr(item, "prov", None) or []
            for proof in provenance:
                page_no = int(getattr(proof, "page_no", 1) or 1)
                bbox = getattr(proof, "bbox", None)
                if bbox is None:
                    continue
                x0 = float(getattr(bbox, "l", getattr(bbox, "x0", 0.0)))
                y0 = float(getattr(bbox, "t", getattr(bbox, "y0", 0.0)))
                x1 = float(getattr(bbox, "r", getattr(bbox, "x1", x0 + 8)))
                y1 = float(getattr(bbox, "b", getattr(bbox, "y1", y0 + 8)))
                pages_by_number.setdefault(page_no, []).append(
                    (x0, y0, x1, y1, text, 0, 0, len(pages_by_number.get(page_no, [])))
                )
    except Exception:
        return None
    if not pages_by_number:
        return None
    pages: list[PageIR] = []
    for number in sorted(pages_by_number):
        words = pages_by_number[number]
        width = max(item[2] for item in words) + 12
        height = max(item[3] for item in words) + 12
        pages.append(_page_from_words(number, width, height, words))
    return pages or None


def extract_document_ir(
    pdf_path: Path,
    *,
    ocr_dir: Path | None = None,
    enable_ocr: bool = True,
) -> DocumentIR:
    """Build coordinate-preserving IR with measured fallbacks.

    Order: PyMuPDF → pdfplumber → Docling → OCRmyPDF. Source PDFs are never overwritten.
    """

    pages = _extract_pymupdf_pages(pdf_path)
    quality = _quality(pages, "PYMUPDF_WORDS")
    if quality.requires_ocr:
        try:
            fallback_pages = _extract_pdfplumber_pages(pdf_path)
            fallback_quality = _quality(fallback_pages, "PDFPLUMBER_WORDS")
            if (
                fallback_quality.token_count > quality.token_count
                or fallback_quality.numeric_token_count > quality.numeric_token_count
            ):
                pages = fallback_pages
                quality = fallback_quality
        except Exception:
            pass
    if quality.requires_ocr:
        docling_pages = _extract_docling_pages(pdf_path)
        if docling_pages:
            docling_quality = _quality(docling_pages, "DOCLING")
            if (
                docling_quality.token_count > quality.token_count
                or docling_quality.numeric_token_count > quality.numeric_token_count
            ):
                pages = docling_pages
                quality = docling_quality
    if quality.requires_ocr and enable_ocr and ocr_dir is not None:
        ocr_pdf = _ocr_derivative(pdf_path, ocr_dir)
        if ocr_pdf is not None:
            try:
                ocr_pages = _extract_pymupdf_pages(ocr_pdf)
                ocr_quality = _quality(ocr_pages, "OCR_OCRMYPDF")
                if (
                    ocr_quality.token_count > quality.token_count
                    or ocr_quality.numeric_token_count > quality.numeric_token_count
                ):
                    pages = ocr_pages
                    quality = ocr_quality
            except Exception:
                pass
    return DocumentIR(
        source_path=str(pdf_path),
        pages=tuple(pages),
        quality=quality,
    )


def _greedy_column_centers(positions: list[float], width: float) -> tuple[float, ...]:
    epsilon = max(8.0, width * 0.012)
    clusters: list[list[float]] = []
    for position in sorted(positions):
        if not clusters or position - clusters[-1][-1] > epsilon:
            clusters.append([position])
        else:
            clusters[-1].append(position)
    return tuple(sorted(round(sum(cluster) / len(cluster), 2) for cluster in clusters))


def cluster_numeric_columns(page: PageIR, *, min_y: float = 0.0) -> tuple[float, ...]:
    """Return x-centres of numeric columns using 1-D DBSCAN, with a greedy fallback.

    Clusters are transient document-understanding evidence; vectors are never persisted.
    """

    positions = [
        token.bbox.center_x
        for line in page.lines
        if line.bbox.y0 >= min_y
        for token in line.numeric_tokens
    ]
    if not positions:
        return ()
    if len(positions) < 2:
        return (round(positions[0], 2),)
    try:
        import numpy as np
        from sklearn.cluster import DBSCAN

        array = np.asarray(positions, dtype=float).reshape(-1, 1)
        epsilon = max(8.0, page.width * 0.012)
        labels = DBSCAN(eps=epsilon, min_samples=2).fit_predict(array)
        centers: list[float] = []
        for label in sorted(set(labels.tolist())):
            if label < 0:
                continue
            cluster = array[labels == label].ravel()
            centers.append(float(cluster.mean()))
        if centers:
            return tuple(sorted(round(center, 2) for center in centers))
    except Exception:
        pass
    return _greedy_column_centers(positions, page.width)


def compact_line(line: LineIR) -> dict[str, Any]:
    return {
        "line_id": line.line_id,
        "page": line.page,
        "text": line.text,
        "bbox": asdict(line.bbox),
        "tokens": [{"text": token.text, "bbox": asdict(token.bbox)} for token in line.tokens],
    }
