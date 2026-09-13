from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_production_dockerfile_packages_ocr_runtime() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "tesseract-ocr" in dockerfile
    assert "ghostscript" in dockerfile
    assert "--extra ocr" in dockerfile
    assert "canonical_fallback" not in dockerfile


def test_ocr_runtime_smoke_script_is_image_only_gate() -> None:
    script = (ROOT / "scripts" / "v2_ocr_runtime_smoke.py").read_text(encoding="utf-8")
    assert "PARSER_NAME_OCR" in script
    assert "native_token_count" in script
    assert "bbox" in script
