from pathlib import Path

path = Path("src/cse_financial_etl/extraction/statement_extractor.py")
text = path.read_text(encoding="utf-8")
old = """from cse_financial_etl.extraction.unit_detector import (
    compose_unit_text,
    detect_candidates,
    resolve_unit,
    UnitDetectionError,
)"""
new = """from cse_financial_etl.extraction.unit_detector import (
    UnitDetectionError,
    compose_unit_text,
    detect_candidates,
    resolve_unit,
)"""
if text.count(old) != 1:
    raise SystemExit(f"import block matches={text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
Path(".github/scripts/fix_legacy_import_order.py").unlink()
Path(".github/workflows/temporary-fix-legacy-import.yml").unlink()
