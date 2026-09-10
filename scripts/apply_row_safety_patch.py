from __future__ import annotations

import re
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one replacement, found {count}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, block: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if marker not in text:
        p.write_text(text.rstrip() + "\n\n" + block.strip() + "\n", encoding="utf-8")


# 1. Shared legacy unit detector: page/statement scans must not interpret narrative
# transaction amounts (e.g. a corporate guarantee of LKR 25 Mn) as statement units.
replace_once(
    "src/cse_financial_etl/extraction/unit_detector.py",
    "from cse_financial_etl.domain.models import UnitCandidate\n",
    "from cse_financial_etl.domain.models import UnitCandidate\n"
    "from cse_financial_etl.validation.row_safety import is_narrative_unit_amount\n",
)
replace_once(
    "src/cse_financial_etl/extraction/unit_detector.py",
    '    """Return the most specific non-overlapping unit matches in one text block."""\n\n    candidates: list[UnitCandidate] = []\n',
    '    """Return the most specific non-overlapping unit matches in one text block."""\n\n'
    '    if scope in {UnitScope.STATEMENT, UnitScope.PAGE, UnitScope.REPORT} and is_narrative_unit_amount(text):\n'
    '        return []\n\n'
    '    candidates: list[UnitCandidate] = []\n',
)

# 2. Compiler unit ownership has the same failure mode through table/page footer text.
replace_once(
    "src/cse_financial_etl/compiler/units.py",
    "from cse_financial_etl.compiler.structure_normalizer import ParsedUnit, parse_unit_text\n",
    "from cse_financial_etl.compiler.structure_normalizer import ParsedUnit, parse_unit_text\n"
    "from cse_financial_etl.validation.row_safety import is_narrative_unit_amount\n",
)
replace_once(
    "src/cse_financial_etl/compiler/units.py",
    "    ) -> UnitDeclaration | None:\n        parsed: ParsedUnit = parse_unit_text(text)\n",
    "    ) -> UnitDeclaration | None:\n"
    "        if scope in {SCOPE_TABLE, SCOPE_PAGE} and is_narrative_unit_amount(text):\n"
    "            return None\n"
    "        parsed: ParsedUnit = parse_unit_text(text)\n",
)

# 3. Materialization is the last publication boundary.  Fail closed on invalid EPS
# lineage, narrative unit contamination, OCR tiny-fragment selection, and catastrophic
# derived ratios instead of stamping them PASSED.
replace_once(
    "src/cse_financial_etl/transformation/ratios.py",
    "from cse_financial_etl.validation.acceptance import is_publishable_fact\n",
    "from cse_financial_etl.validation.acceptance import is_publishable_fact\n"
    "from cse_financial_etl.validation.row_safety import (\n"
    "    is_narrative_unit_amount,\n"
    "    ratio_plausibility_issue,\n"
    "    suspicious_selected_numeric,\n"
    ")\n",
)
replace_once(
    "src/cse_financial_etl/transformation/ratios.py",
    "    evidence = _evidence(fact)\n    if fact.validation_status in {\"FAILED\", \"REJECTED\"}:\n",
    "    evidence = _evidence(fact)\n"
    "    if is_narrative_unit_amount(fact.unit_source_text):\n"
    "        evidence[\"row_safety\"] = \"NARRATIVE_UNIT_EVIDENCE\"\n"
    "        return replace(\n"
    "            fact,\n"
    "            status=\"UNIT_NOT_RESOLVED\",\n"
    "            normalized_value=None,\n"
    "            validation_status=\"FAILED\",\n"
    "            overall_certainty=0.0,\n"
    "            certainty_band=\"NONE\",\n"
    "            confidence=\"LOW\",\n"
    "            evidence_json=json.dumps(evidence, separators=(\",\", \":\")),\n"
    "        )\n"
    "    if suspicious_selected_numeric(\n"
    "        fact.metric_code, fact.raw_value, fact.scale_factor, fact.source_line\n"
    "    ):\n"
    "        evidence[\"row_safety\"] = \"SUSPICIOUS_OCR_SELECTED_NUMERIC\"\n"
    "        return replace(\n"
    "            fact,\n"
    "            status=\"VALUE_CONTEXT_UNRESOLVED\",\n"
    "            normalized_value=None,\n"
    "            validation_status=\"FAILED\",\n"
    "            overall_certainty=0.0,\n"
    "            certainty_band=\"NONE\",\n"
    "            confidence=\"LOW\",\n"
    "            evidence_json=json.dumps(evidence, separators=(\",\", \":\")),\n"
    "        )\n"
    "    if fact.validation_status in {\"FAILED\", \"REJECTED\"}:\n",
)

# Insert sibling-aware EPS projection validation before indexing.
replace_once(
    "src/cse_financial_etl/transformation/ratios.py",
    "\ndef _index_facts(\n",
    '''\ndef _sanitize_eps_selected(facts: list[ExtractedFact]) -> list[ExtractedFact]:
    by_code = {fact.metric_code: fact for fact in facts}
    selected = by_code.get("EPS_SELECTED")
    if selected is None or selected.status not in ACCEPTED:
        return facts

    diluted = by_code.get("EPS_DILUTED")
    basic = by_code.get("EPS_BASIC")
    preferred = None
    if diluted is not None and is_publishable_fact(diluted) and diluted.validation_status == "PASSED":
        preferred = diluted
    elif basic is not None and is_publishable_fact(basic) and basic.validation_status == "PASSED":
        preferred = basic

    if (
        preferred is not None
        and selected.normalized_value is not None
        and selected.normalized_value == preferred.normalized_value
        and selected.entity_scope == preferred.entity_scope
        and selected.comparison_role == preferred.comparison_role
    ):
        return facts

    evidence = _evidence(selected)
    evidence["row_safety"] = "EPS_SELECTED_SOURCE_NOT_PUBLISHABLE"
    evidence["preferred_source"] = preferred.metric_code if preferred is not None else None
    replacement = replace(
        selected,
        status="VALIDATION_FAILED",
        normalized_value=None,
        validation_status="FAILED",
        overall_certainty=0.0,
        certainty_band="NONE",
        confidence="LOW",
        evidence_json=json.dumps(evidence, separators=(",", ":")),
    )
    return [replacement if fact.metric_code == "EPS_SELECTED" else fact for fact in facts]


def _index_facts(
''',
)
replace_once(
    "src/cse_financial_etl/transformation/ratios.py",
    "    return _ratio_fact(\n        numerator,\n        ratio_code,\n        numerator.normalized_value / denominator.normalized_value,\n",
    "    value = numerator.normalized_value / denominator.normalized_value\n"
    "    plausibility_issue = ratio_plausibility_issue(ratio_code, value)\n"
    "    if plausibility_issue is not None:\n"
    "        return _missing_ratio(\n"
    "            template, ratio_code, \"IMPLAUSIBLE_DERIVED_RATIO\", plausibility_issue\n"
    "        )\n"
    "    return _ratio_fact(\n"
    "        numerator,\n"
    "        ratio_code,\n"
    "        value,\n",
)
replace_once(
    "src/cse_financial_etl/transformation/ratios.py",
    "    sanitized_results = [\n        (item, [_sanitize_source_fact(fact) for fact in facts])\n        for item, facts in extracted_results\n    ]\n",
    "    sanitized_results = [\n"
    "        (item, _sanitize_eps_selected([_sanitize_source_fact(fact) for fact in facts]))\n"
    "        for item, facts in extracted_results\n"
    "    ]\n",
)

# 4. Price publication must never accept zero/negative layout tokens; use historical
# fallback or typed missing instead.
replace_once(
    "src/cse_financial_etl/orchestration/pipeline.py",
    '                        if price.status == "EXTRACTED" and price.value is not None:\n',
    '                        if price.status == "EXTRACTED" and price.value is not None and price.value > 0:\n',
)
replace_once(
    "src/cse_financial_etl/extraction/statement_extractor.py",
    "                if abs(value) > 100_000:\n                    continue\n                numeric.append((token, value))\n",
    "                if value <= 0 or abs(value) > 100_000:\n"
    "                    continue\n"
    "                numeric.append((token, value))\n",
)

# 5. Period resolution previously understood only prior-year comparisons. Balance-sheet
# tables often compare June with March/December in the same calendar year. Replace the
# helper so any non-target quarter-end header is comparative.
statement_path = Path("src/cse_financial_etl/extraction/statement_extractor.py")
statement_text = statement_path.read_text(encoding="utf-8")
pattern = re.compile(r"def _period_header_points\(.*?\n(?=def )", re.S)
match = pattern.search(statement_text)
if match is None:
    raise RuntimeError("statement_extractor.py: _period_header_points not found")
new_period_helper = '''def _period_header_points(page: PageIR, line: LineIR, period_end: date) -> tuple[list[float], list[float]]:
    """Return target and comparative date-header x positions.

    Comparatives are not restricted to the prior year.  Financial-position tables
    commonly compare a June quarter with March/December in the same calendar year.
    """

    months = (
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    )

    def phrases(value: date) -> tuple[str, ...]:
        month_name = months[value.month - 1]
        month_abbr = month_name[:3]
        return (
            f"{value.day} {month_name} {value.year}",
            f"{value.day:02d} {month_name} {value.year}",
            f"{value.day} {month_abbr} {value.year}",
            f"{value.day:02d} {month_abbr} {value.year}",
            f"{value.day:02d}.{value.month:02d}.{value.year}",
            f"{value.day}.{value.month}.{value.year}",
            f"{value.day:02d}/{value.month:02d}/{value.year}",
            f"{value.day}/{value.month}/{value.year}",
            f"{value.day:02d}-{value.month:02d}-{value.year}",
        )

    target_points: list[float] = []
    for phrase in phrases(period_end):
        target_points.extend(_line_points(page, line, phrase))
    target_points.extend(_header_points(page, line, rf"{period_end.year}"))

    comparative_points: list[float] = []
    for year in (period_end.year, period_end.year - 1):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            candidate = date(year, month, day)
            if candidate == period_end:
                continue
            for phrase in phrases(candidate):
                comparative_points.extend(_line_points(page, line, phrase))
    comparative_points.extend(_header_points(page, line, rf"{period_end.year - 1}"))

    def dedupe(points: list[float]) -> list[float]:
        result: list[float] = []
        for point in points:
            if not any(abs(point - existing) < 1.0 for existing in result):
                result.append(point)
        return result

    return dedupe(target_points), dedupe(comparative_points)


'''
statement_text = statement_text[: match.start()] + new_period_helper + statement_text[match.end() :]
statement_path.write_text(statement_text, encoding="utf-8")

# Regression tests for each full-universe root failure class.
append_once(
    "tests/unit/test_unit_detector.py",
    "test_narrative_amount_is_not_a_page_unit_declaration",
    '''
def test_narrative_amount_is_not_a_page_unit_declaration() -> None:
    from cse_financial_etl.domain.enums import UnitScope
    from cse_financial_etl.extraction.unit_detector import detect_candidates

    text = "Corporate guarantee issued on behalf of a subsidiary is LKR 25 Mn and USD 2 Mn."
    assert detect_candidates(text, scope=UnitScope.PAGE, page=3) == []
''',
)
append_once(
    "tests/unit/test_ratio_fail_closed.py",
    "test_eps_selected_cannot_publish_failed_source",
    '''
def test_eps_selected_cannot_publish_failed_source() -> None:
    basic = _fact("EPS_BASIC", "2.51", validation="FAILED")
    selected = _fact("EPS_SELECTED", "2.51")
    [(_, materialized)] = derive_ratio_facts([("filing", [basic, selected])])
    by_code = _by_code(materialized)
    assert by_code["EPS_SELECTED"].status == "VALIDATION_FAILED"
    assert by_code["EPS_SELECTED"].normalized_value is None


def test_narrative_unit_evidence_is_withheld() -> None:
    pat = _fact("PAT", "100")
    pat = pat.__class__(**{
        **pat.__dict__,
    }) if hasattr(pat, "__dict__") else pat
    from dataclasses import replace
    pat = replace(pat, unit_source_text="Corporate guarantee is LKR 25 Mn and USD 2 Mn")
    [(_, materialized)] = derive_ratio_facts([("filing", [pat, _fact("TOP_LINE", "1000")])])
    by_code = _by_code(materialized)
    assert by_code["PAT"].status == "UNIT_NOT_RESOLVED"
    assert by_code["PAT"].normalized_value is None
    assert by_code["NPM"].status == "INSUFFICIENT_INPUT"


def test_tiny_ocr_fragment_in_large_monetary_row_is_withheld() -> None:
    from dataclasses import replace
    equity = replace(
        _fact("TOTAL_EQUITY", "1"),
        source_line='Total equity 4.335"A3ii97,9:. 2,499,936,009 3,569,255,889',
    )
    [(_, materialized)] = derive_ratio_facts([("filing", [equity, _fact("PAT", "100")])])
    by_code = _by_code(materialized)
    assert by_code["TOTAL_EQUITY"].status == "VALUE_CONTEXT_UNRESOLVED"
    assert by_code["ROE"].status == "INSUFFICIENT_INPUT"


def test_catastrophic_ratio_is_not_machine_passed() -> None:
    source = [_fact("PAT", "1000000"), _fact("TOTAL_ASSETS", "1"), _fact("TOTAL_EQUITY", "1")]
    [(_, materialized)] = derive_ratio_facts([("filing", source)])
    by_code = _by_code(materialized)
    assert by_code["ROA"].status == "IMPLAUSIBLE_DERIVED_RATIO"
    assert by_code["ROA"].normalized_value is None
    assert by_code["ROE"].status == "IMPLAUSIBLE_DERIVED_RATIO"
''',
)

# Keep the patch mechanism out of the resulting branch commit.
Path("scripts/apply_row_safety_patch.py").unlink(missing_ok=True)
Path(".github/workflows/apply-row-safety-patch.yml").unlink(missing_ok=True)
print("row-safety patch applied")
