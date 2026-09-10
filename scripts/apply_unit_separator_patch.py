from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/cse_financial_etl/compiler/structure_normalizer.py",
    '    (Decimal("1000"), re.compile(r"[\'’‘]\\s?000s?(?!\\d)|(?<![\\d,.])000s?(?![\\d,])|(?<![a-z])thousands?(?![a-z])", re.I)),\n',
    '''    (\n        Decimal("1000"),\n        re.compile(\n            r"(?:(?<![a-z])(?:rs|lkr)\\.?\\s*0{3}s?(?!\\d)|"\n            r"[\'’‘]\\s?0{3}s?(?!\\d)|(?<![\\d,.])0{3}s?(?![\\d,])|"\n            r"(?<![a-z])thousands?(?![a-z]))",\n            re.I,\n        ),\n    ),\n''',
)
replace_once(
    "src/cse_financial_etl/extraction/unit_detector.py",
    '        re.compile(r"\\b(?:rs\\.?|lkr)\\s+0{3}s?\\b", re.I),\n',
    '        re.compile(r"\\b(?:rs|lkr)\\.?\\s*0{3}s?\\b", re.I),\n',
)
replace_once(
    "configs/unit_patterns.yml",
    r"    regex: '(?i)\b(?:rs\.?|lkr)\s+0{3}s?\b'" + "\n",
    r"    regex: '(?i)\b(?:rs|lkr)\.?\s*0{3}s?\b'" + "\n",
)
replace_once(
    "src/cse_financial_etl/compiler/units.py",
    '    r"(?:\\s|^)(rs\\.?|lkr|usd|cents?|\'000|rs\\.?\\s*\'000|rs\\.?\\s*mn)\\.?\\s*$", re.I\n',
    '    r"(?:\\s|^)(rs\\.?|lkr|usd|cents?|\'000|rs\\.?\\s*\'000|rs\\.?\\s*0{3}|rs\\.?\\s*mn)\\.?\\s*$", re.I\n',
)

test_path = Path("tests/unit/redesign/test_unit_typing.py")
text = test_path.read_text(encoding="utf-8")
if "test_rs_dot_000_is_explicit_thousands" not in text:
    text += '''\n\ndef test_rs_dot_000_is_explicit_thousands() -> None:\n    from decimal import Decimal\n\n    from cse_financial_etl.compiler.structure_normalizer import parse_unit_text\n\n    parsed = parse_unit_text("Rs.000")\n    assert parsed.currency == "LKR"\n    assert parsed.scale == Decimal("1000")\n    assert parsed.scale_explicit is True\n'''
    test_path.write_text(text, encoding="utf-8")

legacy_test = Path("tests/unit/test_unit_detector.py")
text = legacy_test.read_text(encoding="utf-8")
if "test_rs_dot_000_detects_thousands" not in text:
    text += '''\n\ndef test_rs_dot_000_detects_thousands() -> None:\n    from cse_financial_etl.domain.enums import UnitScope\n    from cse_financial_etl.extraction.unit_detector import detect_candidates\n\n    candidates = detect_candidates("Rs.000", scope=UnitScope.TABLE, page=1)\n    assert any(item.currency == "LKR" and item.scale_factor == 1000 for item in candidates)\n'''
    legacy_test.write_text(text, encoding="utf-8")

Path("scripts/apply_unit_separator_patch.py").unlink(missing_ok=True)
Path(".github/workflows/apply-unit-separator-patch.yml").unlink(missing_ok=True)
print("unit separator patch applied")
