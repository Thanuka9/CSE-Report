"""OCR image-only N17 PDFs into text dumps (PDF-only; no engine outputs)."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/n17_blind_pdf_text"
TARGETS = ("SDB.N0000-2025-12-31", "HUNA.N0000-2025-12-31", "AFSL.N0000-2025-12-31")


def main() -> int:
    identity = json.loads(
        (ROOT / "tests/v2/source_truth/holdout_v2_identity_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {it["filing_version_id"]: it for it in identity["items"]}
    OUT.mkdir(parents=True, exist_ok=True)
    for fid in TARGETS:
        meta = by_id[fid]
        pdf = ROOT / meta["local_file"]
        doc = pymupdf.open(pdf)
        pages: list[str] = []
        chars = 0
        for i, page in enumerate(doc, start=1):
            # Prefer native text if present; else OCR.
            native = page.get_text("text").strip()
            if len(native) >= 80:
                text = native
                source = "native"
            else:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                text = pytesseract.image_to_string(img)
                source = "ocr"
            chars += len(text.strip())
            pages.append(f"===== PAGE {i} ({source}) =====\n{text}")
        doc.close()
        out_path = OUT / f"{fid}.ocr.txt"
        out_path.write_text("\n".join(pages), encoding="utf-8")
        print(json.dumps({"filing": fid, "pages": len(pages), "chars": chars, "out": str(out_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
