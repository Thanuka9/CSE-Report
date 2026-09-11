from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/cse_financial_etl/extraction/statement_extractor.py")
TESTS = Path("tests/unit/test_statement_extractor.py")
INVARIANTS = Path("tests/unit/test_legacy_fail_closed_invariants.py")
WORKFLOW = Path(".github/workflows/temporary-harden-legacy-failclosed.yml")
SELF = Path(".github/scripts/temp_harden_legacy.py")

text = SOURCE.read_text(encoding="utf-8")


def once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match, found {count}: {old[:100]!r}")
    text = text.replace(old, new, 1)


def section(start: str, end: str, replacement: str) -> None:
    global text
    a = text.index(start)
    b = text.index(end, a)
    text = text[:a] + replacement.rstrip() + "\n\n" + text[b:]


once("    resolve_unit,\n)", "    resolve_unit,\n    UnitDetectionError,\n)")
once('    comparison_role: str = "CURRENT"', '    comparison_role: str = "UNKNOWN"')
once(
    '    proven = (\n        has_quarter or has_change or bool(re.search(r"\\b20\\d{2}\\b", header)) or len(values) == 1\n    )',
    '    proven = has_quarter or has_change or bool(re.search(r"\\b20\\d{2}\\b", header))',
)
once(
    '        return "UNKNOWN", period_end.year\n    return "CURRENT", period_end.year\n\n\ndef _is_related_party_page',
    '        return "UNKNOWN", period_end.year\n    return "UNKNOWN", period_end.year\n\n\ndef _is_related_party_page',
)
once('        duration_months=3 if rule.statement == "FLOW" else None,', '        duration_months=None,')
once(
    '                            else (3 if rule.statement == "FLOW" else None)\n',
    '                            else None\n',
)
once(
    '            elif flow_duration is None:\n                flow_duration = 3 if not cumulative_only else 6\n                evidence["duration_months"] = flow_duration',
    '            elif flow_duration is None:\n                status = "VALUE_CONTEXT_UNRESOLVED"\n                review_status = "REVIEW"\n                evidence["duration_months"] = None',
)
once(
    '                    or _duration_months(selected.page.text)\n                    or 6\n',
    '                    or _duration_months(selected.page.text)\n',
)

unit_start = '    if metric_type == "MONETARY_PER_SHARE":\n'
unit_end = '    collected: list[UnitCandidate] = []\n'
a = text.index(unit_start, text.index("def _unit_for_layout"))
b = text.index(unit_end, a)
unit_block = '''    if metric_type == "MONETARY_PER_SHARE":
        row_candidates = detect_candidates(line.text, scope=UnitScope.ROW, page=page.number)
        if force_rescan and not row_candidates:
            # Look only near the metric row for detached currency/unit evidence.
            page_lines = list(page.lines)
            for index, candidate in enumerate(page_lines):
                if candidate is line or abs(candidate.bbox.center_y - line.bbox.center_y) > 24:
                    continue
                row_candidates = detect_candidates(
                    candidate.text, scope=UnitScope.ROW, page=page.number
                )
                if row_candidates:
                    break
                if index + 1 < len(page_lines):
                    composed = compose_unit_text(candidate.text, page_lines[index + 1].text)
                    row_candidates = detect_candidates(
                        composed, scope=UnitScope.ROW, page=page.number
                    )
                    if row_candidates:
                        break
        if row_candidates:
            try:
                winner = resolve_unit(row_candidates)
            except UnitDetectionError:
                return None, None, None, 0.0
            return winner.currency, 1, winner.source_text, 0.98

        # Per-share scale is one, but currency must still be source-owned. Use only
        # declarations on this statement page; never invent LKR or borrow a report unit.
        statement_candidates: list[UnitCandidate] = []
        for candidate_line in page.lines:
            if not _unit_declaration(candidate_line.text):
                continue
            statement_candidates.extend(
                detect_candidates(
                    candidate_line.text,
                    scope=UnitScope.STATEMENT,
                    page=page.number,
                )
            )
        if not statement_candidates:
            return None, None, None, 0.0
        try:
            winner = resolve_unit(statement_candidates)
        except UnitDetectionError:
            return None, None, None, 0.0
        return winner.currency, 1, winner.source_text, 0.9

'''
text = text[:a] + unit_block + text[b:]

once(
    '        except Exception:\n            pass\n    if not ranked:',
    '        except UnitDetectionError:\n            # A source-unit conflict is ambiguity, not permission to pick a ranked fallback.\n            return None, None, None, 0.0\n    if not ranked:',
)

new_map = '''def _legacy_continuation_evidenced(previous: PageIR, current: PageIR) -> bool:
    """Require positive repeated source evidence before context crosses a page."""

    previous_head = " ".join(line.text for line in previous.lines[:12]).upper()
    current_head = " ".join(line.text for line in current.lines[:12]).upper()
    previous_scope = bool(
        re.search(r"\\b(?:GROUP|COMPANY|BANK|RS\\.?|LKR|RUPEES?)\\b", previous_head)
    )
    current_scope = bool(
        re.search(r"\\b(?:GROUP|COMPANY|BANK|RS\\.?|LKR|RUPEES?)\\b", current_head)
    )
    temporal = bool(
        re.search(
            r"\\b(?:THREE|SIX|NINE|TWELVE|3|6|9|12)\\s+MONTHS?\\b|"
            r"\\b(?:PERIOD|QUARTER|YEAR)\\s+ENDED\\b|\\bAS\\s+AT\\b|"
            r"\\b(?:31|30|29|28)\\s+(?:MAR|MARCH|JUN|JUNE|SEP|SEPTEMBER|DEC|DECEMBER)\\s+20\\d{2}\\b",
            current_head,
        )
    )
    return previous_scope and current_scope and temporal


def _page_statement_map(document: DocumentIR) -> dict[int, str | None]:
    """Map statement type without unevidenced continuation carry-forward."""

    current: str | None = None
    previous: PageIR | None = None
    mapping: dict[int, str | None] = {}
    for page in document.pages:
        if _is_notes_heading(page):
            current = None
            mapping[page.number] = None
            previous = page
            continue
        classified = _classify_page_statement(page)
        if classified == "OTHER":
            current = None
        elif classified is not None:
            current = classified
        elif not (
            current is not None
            and previous is not None
            and page.number == previous.number + 1
            and _legacy_continuation_evidenced(previous, page)
        ):
            current = None
        mapping[page.number] = current
        previous = page
    return mapping
'''
section("def _page_statement_map(", "def _page_has_eps(", new_map)

new_facts = '''def facts_by_code(facts: Iterable[ExtractedFact]) -> dict[str, ExtractedFact]:
    """Return only unique metric facts; duplicate evidence is ambiguous."""

    unique: dict[str, ExtractedFact] = {}
    ambiguous: set[str] = set()
    for fact in facts:
        code = fact.metric_code
        if code in unique:
            ambiguous.add(code)
        else:
            unique[code] = fact
    for code in ambiguous:
        unique.pop(code, None)
    return unique
'''
section("def facts_by_code(", "\n", new_facts) if False else None
# facts_by_code is the final function in this module.
start = text.index("def facts_by_code(")
text = text[:start] + new_facts

SOURCE.write_text(text, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
old = '''    continuation = _page(
        2,
        [
            _line(
                2,
                80,
                [
                    _token("Revenue", 40, 80, 70),
                    _token("100", 200, 80, 40),
                    _token("90", 280, 80, 40),
                ],
            )
        ],
    )
'''
new = '''    continuation = _page(
        2,
        [
            _line(2, 20, [_token("Company", 40, 20, 60), _token("Rs.", 120, 20, 25)]),
            _line(
                2,
                40,
                [
                    _token("Three", 40, 40, 40),
                    _token("months", 90, 40, 45),
                    _token("ended", 145, 40, 40),
                    _token("30", 195, 40, 20),
                    _token("June", 225, 40, 35),
                    _token("2026", 270, 40, 35),
                    _token("2025", 320, 40, 35),
                ],
            ),
            _line(
                2,
                80,
                [
                    _token("Revenue", 40, 80, 70),
                    _token("100", 270, 80, 40),
                    _token("90", 320, 80, 40),
                ],
            ),
        ],
    )
'''
if tests.count(old) != 1:
    raise SystemExit(f"continuation fixture count={tests.count(old)}")
TESTS.write_text(tests.replace(old, new, 1), encoding="utf-8")

INVARIANTS.write_text('''from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.documents.document_ir import BBox, DocumentIR, DocumentQuality, LineIR, PageIR, TokenIR
from cse_financial_etl.documents.pdf_text import PdfPage
from cse_financial_etl.extraction.statement_extractor import ExtractedFact, _comparison_from_layout, _page_statement_map, _select_current, _unit_for_layout, facts_by_code


def _token(text: str, x: float, y: float) -> TokenIR:
    return TokenIR(text, BBox(x, y, x + 40, y + 10), 0, 0, 0)


def _line(page: int, y: float, *tokens: TokenIR) -> LineIR:
    return LineIR(page, f"p{page}-{y}", " ".join(t.text for t in tokens), BBox(10, y, 500, y + 10), tuple(tokens))


def _page(number: int, *lines: LineIR) -> PageIR:
    return PageIR(number, 600, 800, tuple(lines), "\\n".join(line.text for line in lines))


def _doc(*pages: PageIR) -> DocumentIR:
    return DocumentIR("memory.pdf", tuple(pages), DocumentQuality(len(pages), 10, 3, 1.0, "TEST", False))


def _fact(code: str, value: str) -> ExtractedFact:
    amount = Decimal(value)
    return ExtractedFact(issuer_name="Example PLC", symbol="EX.N0000", period_end=date(2026, 6, 30), metric_code=code, metric_type="MONETARY_ABSOLUTE", raw_text=value, raw_value=amount, normalized_value=amount, currency="LKR", scale_factor=1, entity_scope="COMPANY", source_page=1, source_line=code, unit_source_text="Rs.", confidence="HIGH", status="EXTRACTED")


def test_extracted_fact_has_no_implicit_current_role() -> None:
    assert _fact("PAT", "10").comparison_role == "UNKNOWN"


def test_layout_role_is_unknown_without_source_date_headers() -> None:
    value = _token("100", 300, 100)
    row = _line(1, 100, _token("Revenue", 20, 100), value)
    role, _ = _comparison_from_layout(_page(1, row), row, value, date(2026, 6, 30), entity="COMPANY")
    assert role == "UNKNOWN"


def test_single_value_is_not_current_without_period_evidence() -> None:
    page = PdfPage(1, "Statement of profit or loss\\nRevenue 100")
    assert _select_current([("100", Decimal("100"))], page, "FLOW") is None


def test_untitled_page_without_repeated_header_does_not_inherit_statement() -> None:
    first = _page(1, _line(1, 20, _token("Statement", 20, 20), _token("of", 70, 20), _token("profit", 100, 20), _token("or", 160, 20), _token("loss", 190, 20)))
    second = _page(2, _line(2, 80, _token("Revenue", 20, 80), _token("100", 300, 80)))
    assert _page_statement_map(_doc(first, second))[2] is None


def test_per_share_currency_is_not_invented_without_source_unit() -> None:
    row = _line(1, 100, _token("Basic", 20, 100), _token("EPS", 70, 100), _token("1.25", 300, 100))
    page = _page(1, row)
    assert _unit_for_layout(_doc(page), page, row, "MONETARY_PER_SHARE") == (None, None, None, 0.0)


def test_duplicate_metric_facts_do_not_use_last_write_wins() -> None:
    mapping = facts_by_code([_fact("PAT", "10"), _fact("PAT", "11"), _fact("PBT", "12")])
    assert "PAT" not in mapping
    assert mapping["PBT"].raw_value == Decimal("12")
''', encoding="utf-8")

WORKFLOW.unlink(missing_ok=True)
SELF.unlink(missing_ok=True)
