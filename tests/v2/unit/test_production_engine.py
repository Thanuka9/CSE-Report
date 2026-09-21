from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.config import AppConfig
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    PublicationStatus,
    StatementType,
)
from cse_financial_etl.v2.market.quarter_end_price import resolve_last_traded_as_of_quarter_end
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from cse_financial_etl.v2.production.adapter import _from_source, select_pipeline_facts
from cse_financial_etl.v2.production.engine import extract_for_production
from cse_financial_etl.v2.taxonomy.registry import load_registry
from tests.v2.helpers import geometric_document, source_fact, source_ref


def test_app_config_defaults_to_v1_engine() -> None:
    assert AppConfig().extraction_engine == "v1"


def test_investor_navps_does_not_infer_company() -> None:
    document = geometric_document(
        (
            ((40.0, "INVESTOR INFORMATION"),),
            ((40.0, "30 June 2026"), (220.0, "30 June 2025")),
            ((40.0, "Net assets per share"), (220.0, "148.27"), (340.0, "127.14")),
        ),
        title="INVESTOR INFORMATION",
    )
    statements, facts, _derived, _metrics = run_filing_pipeline(
        document, issuer_id="HAYL.N0000"
    )
    assert any(item.statement_type is StatementType.EPS_NOTE for item in statements)
    navps = [fact for fact in facts if fact.metric_code == "NAVPS"]
    assert all(fact.entity_scope is not EntityScope.COMPANY for fact in navps)
    assert not any(
        fact.publication_status is PublicationStatus.ELIGIBLE for fact in navps
    )


def test_last_traded_rejects_observed_after_quarter_end(tmp_path: Path) -> None:
    resolved = resolve_last_traded_as_of_quarter_end(
        tmp_path, "AAA.N0000", date(2026, 6, 30)
    )
    assert resolved is None


def test_last_traded_wrapper_drops_future_observation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "cse_financial_etl.v2.market.quarter_end_price.resolve_quarter_end_price",
        lambda *_args, **_kwargs: (Decimal("10"), date(2026, 7, 1), "LEAK"),
    )
    assert (
        resolve_last_traded_as_of_quarter_end(tmp_path, "AAA.N0000", date(2026, 6, 30))
        is None
    )


def test_pipeline_facts_prefer_requested_company_over_group() -> None:
    company = source_fact(
        fact_id="company-pat",
        metric_code="PAT",
        entity_scope=EntityScope.COMPANY,
        normalized_value=Decimal("1"),
        raw_value=Decimal("1"),
    )
    group = source_fact(
        fact_id="group-pat",
        metric_code="PAT",
        entity_scope=EntityScope.GROUP,
        normalized_value=Decimal("9"),
        raw_value=Decimal("9"),
        cell_id="cell-2",
    )
    selected = select_pipeline_facts(
        (group, company),
        period_end=date(2026, 6, 30),
        expected_entity=EntityScope.COMPANY,
    )
    assert len(selected) == 1
    assert selected[0].entity_scope is EntityScope.COMPANY
    assert selected[0].normalized_value == Decimal("1")


def test_pipeline_facts_fail_closed_when_company_absent() -> None:
    group = source_fact(entity_scope=EntityScope.GROUP)
    selected = select_pipeline_facts(
        (group,),
        period_end=date(2026, 6, 30),
        expected_entity=EntityScope.COMPANY,
    )
    assert selected == ()


def test_pipeline_facts_fail_closed_when_bank_absent() -> None:
    group = source_fact(entity_scope=EntityScope.GROUP)
    selected = select_pipeline_facts(
        (group,),
        period_end=date(2026, 6, 30),
        expected_entity=EntityScope.BANK,
    )
    assert selected == ()


def test_pipeline_facts_allow_company_separate_equivalence() -> None:
    separate = source_fact(entity_scope=EntityScope.SEPARATE)
    selected = select_pipeline_facts(
        (separate,),
        period_end=date(2026, 6, 30),
        expected_entity=EntityScope.COMPANY,
    )
    assert len(selected) == 1
    assert selected[0].entity_scope is EntityScope.SEPARATE


def test_pipeline_facts_allow_group_consolidated_equivalence() -> None:
    consolidated = source_fact(entity_scope=EntityScope.CONSOLIDATED)
    selected = select_pipeline_facts(
        (consolidated,),
        period_end=date(2026, 6, 30),
        expected_entity=EntityScope.GROUP,
    )
    assert len(selected) == 1
    assert selected[0].entity_scope is EntityScope.CONSOLIDATED


def test_pipeline_facts_prefer_natural_scale_over_bn_highlight() -> None:
    highlight = source_fact(
        fact_id="bn-pat",
        normalized_value=Decimal("181200000000"),
        raw_value=Decimal("181.2"),
        source_scale=Decimal("1000000000"),
        source_ref=source_ref(page_number=2, raw_text="181.2"),
        cell_id="cell-bn",
    )
    statement = source_fact(
        fact_id="stmt-pat",
        normalized_value=Decimal("429411257"),
        raw_value=Decimal("429411257"),
        source_scale=Decimal("1"),
        source_ref=source_ref(page_number=5, raw_text="429,411,257"),
        cell_id="cell-stmt",
    )
    selected = select_pipeline_facts(
        (highlight, statement),
        period_end=date(2026, 6, 30),
        expected_entity=EntityScope.COMPANY,
    )
    assert len(selected) == 1
    assert selected[0].normalized_value == Decimal("429411257")

    comparative = source_fact(
        fact_id="prior",
        comparison_role=ComparisonRole.COMPARATIVE,
        period_end=date(2025, 6, 30),
        cell_id="cell-2",
    )
    six_month = source_fact(fact_id="six", duration_months=6, cell_id="cell-3")
    current = source_fact()
    selected = select_pipeline_facts(
        (comparative, six_month, current),
        period_end=date(2026, 6, 30),
        expected_entity=EntityScope.COMPANY,
    )
    assert [fact.fact_id for fact in selected] == ["fact-1"]


def test_pipeline_extract_filing_defaults_to_v1(monkeypatch) -> None:
    called = {"v1": False, "v2": False}

    def fake_v1(*_args, **_kwargs):
        called["v1"] = True
        return []

    def fake_v2(*_args, **_kwargs):
        called["v2"] = True
        return []

    monkeypatch.setattr(
        "cse_financial_etl.orchestration.pipeline.extract_filing_v1", fake_v1
    )
    monkeypatch.setattr(
        "cse_financial_etl.v2.production.engine.extract_filing_v2", fake_v2
    )
    from cse_financial_etl.orchestration.pipeline import extract_filing

    extract_filing(Path("missing.pdf"), "Acme PLC", "ACM.N0000", date(2026, 6, 30))
    assert called["v1"] is True
    assert called["v2"] is False


def test_rollback_to_v1_leaves_hybrid_off_and_v1_importable(monkeypatch) -> None:
    called = {"v1": 0, "v2": 0}

    def fake_v1(*_args, **_kwargs):
        called["v1"] += 1
        return []

    def fake_v2(*_args, **_kwargs):
        called["v2"] += 1
        return []

    monkeypatch.setattr(
        "cse_financial_etl.v2.production.engine.extract_filing", fake_v1
    )
    monkeypatch.setattr(
        "cse_financial_etl.v2.production.engine.extract_filing_v2", fake_v2
    )
    extract_for_production(
        Path("missing.pdf"), "Acme", "ACM.N0000", date(2026, 6, 30), engine="v2"
    )
    extract_for_production(
        Path("missing.pdf"), "Acme", "ACM.N0000", date(2026, 6, 30), engine="v1"
    )
    assert called == {"v1": 1, "v2": 1}
    from cse_financial_etl.extraction.statement_extractor import extract_filing as v1_backend

    assert callable(v1_backend)
    import yaml

    app = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "configs" / "app.yml").read_text(
            encoding="utf-8"
        )
    )
    assert app["extraction"]["engine"] == "v1"


def test_v1_engine_flag_still_calls_challenger(monkeypatch) -> None:
    called = {"v1": False}

    def fake_v1(*_args, **_kwargs):
        called["v1"] = True
        return []

    monkeypatch.setattr(
        "cse_financial_etl.v2.production.engine.extract_filing", fake_v1
    )
    extract_for_production(
        Path("missing.pdf"), "Acme", "ACM.N0000", date(2026, 6, 30), engine="v1"
    )
    assert called["v1"] is True


def test_v2_adapter_does_not_invent_confidence_one() -> None:
    fact = _from_source(
        source_fact(),
        issuer_name="Acme PLC",
        symbol="ACM.N0000",
        registry=load_registry(),
    )
    assert fact.confidence == "DETERMINISTIC"
    assert fact.certainty_band == "DETERMINISTIC"
    assert fact.semantic_confidence == 0.0
    assert fact.entity_confidence == 0.0
    assert fact.period_confidence == 0.0
    assert fact.unit_confidence == 0.0
    assert fact.overall_certainty == 0.0
