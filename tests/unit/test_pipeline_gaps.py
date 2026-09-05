import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.config import (
    infer_entity_scope,
    infer_issuer_type,
    load_app_config,
    load_issuers,
)
from cse_financial_etl.documents.pdf_text import PdfPage
from cse_financial_etl.domain.enums import MissingReason
from cse_financial_etl.domain.periods import shift_quarter, supporting_periods
from cse_financial_etl.extraction.statement_extractor import (
    METRIC_RULES,
    ExtractedFact,
    _find_metric,
    _is_exact_quarter_page,
    _is_excluded_pat_line,
    entity_scope_for_issuer,
)
from cse_financial_etl.reporting.excel import _previous_ranks
from cse_financial_etl.storage.run_archive import MANIFESTS_DIRNAME, archive_pipeline_artifacts
from cse_financial_etl.transformation.ratios import derive_ratio_facts


def _fact(
    issuer: str,
    period: date,
    metric: str,
    value: str,
    *,
    duration: int | None = 3,
) -> ExtractedFact:
    return ExtractedFact(
        issuer_name=issuer,
        symbol="TEST.N0000",
        period_end=period,
        metric_code=metric,
        metric_type="MONETARY_ABSOLUTE",
        raw_text=value,
        raw_value=Decimal(value),
        normalized_value=Decimal(value),
        currency="LKR",
        scale_factor=1,
        entity_scope="COMPANY",
        source_page=1,
        source_line=metric,
        unit_source_text="Rs.",
        confidence="HIGH",
        status="EXTRACTED",
        duration_months=duration,
        validation_status="PASSED",
        review_status="APPROVED",
        overall_certainty=0.96,
    )


def test_company_pat_attributable_line_is_kept() -> None:
    page = PdfPage(
        1,
        "Statement of profit or loss - Company\nFor the quarter ended 30 June 2026\n"
        "Profit for the period attributable to equity holders of the company 12,500 10,000",
    )
    pat_rule = next(rule for rule in METRIC_RULES if rule.code == "PAT")
    found = _find_metric(page, pat_rule)
    assert found is not None
    assert found[1] == Decimal("12500")


def test_nci_pat_line_is_excluded() -> None:
    assert _is_excluded_pat_line("Profit attributable to non-controlling interests 1,200")
    assert not _is_excluded_pat_line(
        "Profit for the period attributable to equity holders of the company 12,500"
    )


def test_fourth_quarter_page_is_exact_quarter() -> None:
    page = PdfPage(1, "Statement of profit or loss\nFor the fourth quarter ended 31 December 2025")
    assert _is_exact_quarter_page(page)


def test_bank_and_config_entity_scope() -> None:
    assert entity_scope_for_issuer("COMMERCIAL BANK OF CEYLON PLC") == "BANK"
    assert infer_issuer_type("PEOPLE'S LEASING & FINANCE PLC") == "FINANCE_COMPANY"
    assert infer_issuer_type("UNION ASSURANCE PLC") == "INSURANCE"
    project_root = Path(__file__).resolve().parents[2]
    issuers = load_issuers(project_root)
    assert infer_entity_scope("John Keells Holdings PLC", issuers) == "COMPANY"
    assert infer_entity_scope("Commercial Bank of Ceylon PLC", issuers) == "BANK"


def test_app_config_enables_ocr() -> None:
    config = load_app_config(Path(__file__).resolve().parents[2])
    assert config.ocr_enabled is True
    assert config.manual_review_threshold == 0.80
    assert config.use_transformer is True
    assert config.balance_sheet_relative == 0.005


def test_supporting_periods_include_prior_quarters_for_q4_delta() -> None:
    assert shift_quarter(date(2026, 6, 30), 1) == date(2026, 3, 31)
    periods = supporting_periods([date(2026, 6, 30)])
    assert date(2025, 9, 30) in periods
    assert date(2025, 6, 30) not in periods
    assert date(2026, 6, 30) in periods


def test_same_quarter_ratios_need_no_history() -> None:
    period = date(2026, 6, 30)
    facts = [
        _fact("Acme PLC", period, "TOTAL_LIABILITIES", "200"),
        _fact("Acme PLC", period, "TOTAL_EQUITY", "100"),
        _fact("Acme PLC", period, "TOTAL_ASSETS", "300"),
        _fact("Acme PLC", period, "PAT", "10"),
        _fact("Acme PLC", period, "TOP_LINE", "50"),
    ]
    derived = derive_ratio_facts([(object(), facts)], display_periods=[period])
    codes = {fact.metric_code: fact for fact in derived[0][1]}
    assert codes["DEBT_TO_EQUITY"].normalized_value == Decimal("2")
    assert codes["ROE"].normalized_value == Decimal("0.1")
    assert codes["ROA"].normalized_value == Decimal("10") / Decimal("300")
    assert codes["NPM"].normalized_value == Decimal("0.2")


def test_missing_reason_contract_includes_ratio_statuses() -> None:
    assert MissingReason.NON_POSITIVE_DENOMINATOR.value == "NON_POSITIVE_DENOMINATOR"
    assert MissingReason.INCOMPATIBLE_CURRENCY.value == "INCOMPATIBLE_CURRENCY"
    assert MissingReason.INSUFFICIENT_INPUT.value == "INSUFFICIENT_INPUT"
    assert MissingReason.CROSS_FILING_MISMATCH.value == "CROSS_FILING_MISMATCH"


def test_same_quarter_ratio_missing_input_is_insufficient_input() -> None:
    period = date(2026, 6, 30)
    facts = [_fact("Acme PLC", period, "TOTAL_EQUITY", "100")]
    derived = derive_ratio_facts([(object(), facts)], display_periods=[period])
    codes = {fact.metric_code: fact for fact in derived[0][1]}
    assert codes["ROE"].status == "INSUFFICIENT_INPUT"
    assert codes["ROE"].normalized_value is None


def test_historical_price_ignores_live_snapshot_after_quarter_end(tmp_path: Path) -> None:
    from cse_financial_etl.sources.historical_prices import resolve_quarter_end_price

    api = tmp_path / "data" / "raw" / "api"
    api.mkdir(parents=True)
    (api / "market_cap_2026-06-30.json").write_text(
        json.dumps([{"symbol": "AAA.N0000", "price": 10}]),
        encoding="utf-8",
    )
    (api / "market_cap_2026-09-04.json").write_text(
        json.dumps([{"symbol": "AAA.N0000", "price": 99}]),
        encoding="utf-8",
    )
    resolved = resolve_quarter_end_price(tmp_path, "AAA.N0000", date(2026, 6, 30))
    assert resolved is not None
    value, price_date, method = resolved
    assert value == Decimal("10")
    assert price_date == date(2026, 6, 30)
    assert method == "LAST_TRADE_ON_OR_BEFORE_QUARTER_END"
    assert resolve_quarter_end_price(tmp_path, "AAA.N0000", date(2026, 3, 31)) is None


def test_archive_keeps_previous_market_and_output_files(tmp_path: Path) -> None:
    market = tmp_path / "data" / "raw" / "api" / "market_cap_2026-06-30.json"
    market.parent.mkdir(parents=True)
    market.write_text('[{"symbol": "AAA.N0000", "market_capitalization": 100}]', encoding="utf-8")
    workbook = tmp_path / "outputs" / "CSE_Financial_Snapshot_2026-06-30.xlsx"
    workbook.parent.mkdir(parents=True)
    workbook.write_bytes(b"old-xlsx")
    archived = archive_pipeline_artifacts(tmp_path, "2026-06-30", "20260904T120000Z")
    names = {path.name for path in archived}
    assert "market_cap_2026-06-30_20260904T120000Z.json" in names
    assert "CSE_Financial_Snapshot_2026-06-30_20260904T120000Z.xlsx" in names
    assert market.exists()


def test_previous_ranks_use_archived_same_date_snapshot(tmp_path: Path) -> None:
    api = tmp_path / "data" / "raw" / "api"
    history = api / "history"
    history.mkdir(parents=True)
    previous = [
        {"symbol": "AAA.N0000", "market_capitalization": 200},
        {"symbol": "BBB.N0000", "market_capitalization": 100},
    ]
    current = [
        {"symbol": "AAA.N0000", "market_capitalization": 100},
        {"symbol": "BBB.N0000", "market_capitalization": 200},
    ]
    (api / "market_cap_2026-06-30.json").write_text(json.dumps(current), encoding="utf-8")
    (history / "market_cap_2026-06-30_20260904T100000Z.json").write_text(
        json.dumps(previous), encoding="utf-8"
    )
    ranks = _previous_ranks(tmp_path, date(2026, 6, 30))
    assert ranks["AAA.N0000"] == 1
    assert ranks["BBB.N0000"] == 2


def test_run_manifest_is_archived_from_plural_manifests(tmp_path: Path) -> None:
    manifests = tmp_path / "outputs" / MANIFESTS_DIRNAME
    manifests.mkdir(parents=True)
    (manifests / "run_manifest_2026-06-30.json").write_text("{}", encoding="utf-8")
    archived = archive_pipeline_artifacts(tmp_path, "2026-06-30", "20260905T000000Z")
    names = {path.name for path in archived}
    assert "run_manifest_2026-06-30_20260905T000000Z.json" in names
    assert MANIFESTS_DIRNAME == "manifests"


def test_yaml_configs_and_intelligence_stack_are_wired() -> None:
    from cse_financial_etl.config import load_metric_catalog, load_unit_pattern_config
    from cse_financial_etl.documents.document_ir import (
        BBox,
        LineIR,
        PageIR,
        TokenIR,
        cluster_numeric_columns,
    )
    from cse_financial_etl.extraction.evidence_graph import build_value_graph
    from cse_financial_etl.extraction.semantic_matcher import (
        CANONICAL_LABELS,
        apply_metric_catalog,
        get_semantic_matcher,
    )
    from cse_financial_etl.extraction.unit_detector import PATTERNS, configure_unit_patterns

    root = Path(__file__).resolve().parents[2]
    apply_metric_catalog(load_metric_catalog(root))
    configure_unit_patterns(load_unit_pattern_config(root))
    assert "gross income" in CANONICAL_LABELS["TOP_LINE"]
    assert any(pattern.pattern_id == "lkr_thousand" for pattern in PATTERNS)
    matcher = get_semantic_matcher()
    assert matcher.model_name.startswith("rapidfuzz")
    match = matcher.match("Profit for the period", "PAT")
    assert match.score >= 0.9

    token = TokenIR("100", BBox(200, 80, 240, 90), 0, 0, 0)
    line = LineIR(1, "p1-1", "Profit for the period 100", BBox(40, 80, 240, 90), (token,))
    graph = build_value_graph(
        label="Profit for the period",
        value_token=token,
        entity="COMPANY",
        period_end="2026-06-30",
        line=line,
        column_scores=[],
        cluster_centers=(200.0,),
        components={"entity": 1.0},
        selected_score=0.9,
        runner_up_score=0.2,
    )
    assert graph["graph_metrics"]["node_count"] >= 5
    assert any(edge["relation"] == "SAME_ROW" for edge in graph["edges"])

    page = PageIR(
        1,
        800,
        1000,
        (
            LineIR(
                1,
                "r0",
                "10 20 30",
                BBox(0, 100, 300, 110),
                (
                    TokenIR("10", BBox(100, 100, 120, 110), 0, 0, 0),
                    TokenIR("20", BBox(200, 100, 220, 110), 0, 0, 1),
                    TokenIR("30", BBox(300, 100, 320, 110), 0, 0, 2),
                ),
            ),
        ),
        "10 20 30",
    )
    centers = cluster_numeric_columns(page)
    assert len(centers) >= 2
