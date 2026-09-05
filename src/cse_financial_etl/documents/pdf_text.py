from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PdfPage:
    number: int
    text: str


def extract_layout_pages(pdf_path: Path, text_cache_dir: Path | None = None) -> list[PdfPage]:
    """Extract layout-preserving text, preferring Poppler and falling back to pypdf."""

    cache_path = None
    if text_cache_dir is not None:
        text_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = text_cache_dir / f"{pdf_path.stem}.txt"
        if cache_path.exists() and cache_path.stat().st_size:
            return _split_pages(cache_path.read_text(encoding="utf-8", errors="replace"))

    if shutil.which("pdftotext"):
        command = ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"]
        completed = subprocess.run(command, check=True, capture_output=True, timeout=240)
        text = completed.stdout.decode("utf-8", errors="replace")
    else:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        text = "\f".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)

    if cache_path is not None:
        cache_path.write_text(text, encoding="utf-8")
    return _split_pages(text)


def _split_pages(text: str) -> list[PdfPage]:
    raw_pages = text.replace("\r\n", "\n").replace("\r", "\n").split("\f")
    pages = [
        PdfPage(number=index + 1, text=page) for index, page in enumerate(raw_pages) if page.strip()
    ]
    return pages
