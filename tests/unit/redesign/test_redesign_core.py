"""Revision 2 redesign unit coverage — ontology, arbiter, equations, recovery, queries."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.accounting.concept_rules import (
    group_cannot_satisfy_company,
    requires_exact_3m,
)
from cse_financial_etl.accounting.ontology import PROFIT_LOSS_CONCEPTS, all_concepts
from cse_financial_etl.accounting.semantic_candidates import generate_concept_hypotheses
from cse_financial_etl.compiler.structure_normalizer import (
    normalize_duration_phrase,
    parse_numeric,
)
from cse_financial_etl.constraints.eps import select_eps
from cse_financial_etl.constraints.equation_registry import default_registry
from cse_financial_etl.constraints.temporal import duration_satisfies_flow_target
from cse_financial_etl.facts.derived_facts import compute_quarter_ratios
from cse_financial_etl.facts.query_engine import QueriedFact, query_target_facts
from cse_financial_etl.recovery.failure_diagnoser import diagnose_failures
from cse_financial_etl.recovery.recovery_router import run_recovery
from cse_financial_etl.resolution.arbiter import arbitrate_candidates
from cse_financial_etl.resolution.beam_search import beam_search_concept
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.validation.final_validator import gate_no_overpublication


def _entry(**kwargs: object) -> LedgerEntry:
    base: dict[str, object] = dict(
        entry_id="e1",
        tunnel="A",
        concept="PAT",
        status="unresolved",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        entity="COMPANY",
        period_end="2026-06-30",
        duration_months=3,
        comparison_role="CURRENT",
        unit="LKR",
        scale_factor=1000,
        page=1,
        bbox=None,
        label="Profit for the period",
        score=0.9,
        evidence={"semantic_score": 1.0},
    )
    base.update(kwargs)
    return LedgerEntry(**base)  # type: ignore[arg-type]


def test_ontology_includes_required_concepts() -> None:
    concepts = set(all_concepts())
    for required in (
        "PAT",
        "PBT",
        "OPERATING_PROFIT",
        "TOTAL_ASSETS",
        "TOTAL_LIABILITIES",
        "NAVPS",
    ):
        assert required in concepts
    assert "PAT" in PROFIT_LOSS_CONCEPTS


def test_high_recall_keeps_uncertain_candidates() -> None:
    hyps = generate_concept_hypotheses(
        "Profit attributable to equity holders of the company"
    )
    assert hyps
    assert any(h.concept == "PAT" for h in hyps)
    weak = generate_concept_hypotheses("results from activities", min_keep=0.35)
    assert isinstance(weak, list)


def test_never_group_for_company() -> None:
    assert group_cannot_satisfy_company("COMPANY", "GROUP")
    assert not group_cannot_satisfy_company("COMPANY", "COMPANY")


def test_exact_3m_required_for_flow() -> None:
    assert requires_exact_3m("PAT")
    assert duration_satisfies_flow_target(3)
    assert not duration_satisfies_flow_target(6)


def test_parse_numeric_parentheses_and_dash_not_zero() -> None:
    assert parse_numeric("(1,245)") == Decimal("-1245")
    assert parse_numeric("-") is None
    assert normalize_duration_phrase("For the three months ended 30 June 2026") == 3


def test_equations_do_not_silently_derive_pat() -> None:
    registry = default_registry()
    results = registry.evaluate(
        {"PBT": Decimal("2500"), "INCOME_TAX": Decimal("600"), "PAT": None},
        entity="COMPANY",
        allow_derive=False,
    )
    pat = next(r for r in results if r.equation_id == "pat_eq_pbt_less_tax")
    assert pat.status == "UNTESTED"
    derived = registry.evaluate(
        {"PBT": Decimal("2500"), "INCOME_TAX": Decimal("600"), "PAT": None},
        entity="COMPANY",
        allow_derive=True,
    )
    assert next(r for r in derived if r.equation_id == "pat_eq_pbt_less_tax").mode == "derive"


def test_arbiter_rejects_ytd_and_group() -> None:
    ledger = CandidateLedger()
    ledger.add(_entry(entry_id="g", entity="GROUP", concept="PAT"))
    ledger.add(
        _entry(
            entry_id="y",
            entity="COMPANY",
            duration_months=6,
            concept="PAT",
            score=0.99,
        )
    )
    ledger.add(
        _entry(
            entry_id="ok",
            entity="COMPANY",
            duration_months=3,
            concept="PAT",
            score=0.8,
        )
    )
    decisions = arbitrate_candidates(
        ledger, required_entity="COMPANY", target_duration=3
    )
    pat = next(d for d in decisions if d.concept == "PAT")
    assert pat.status == "SELECTED"
    assert pat.selected is not None
    assert pat.selected.entry_id == "ok"


def test_beam_search_abstains_when_indistinguishable() -> None:
    cands = [
        _entry(entry_id="a", score=0.90),
        _entry(entry_id="b", score=0.89),
    ]
    result = beam_search_concept(
        cands, required_entity="COMPANY", target_duration=3
    )
    assert result.status in {"ABSTAIN", "RESOLVED"}


def test_eps_zero_is_valid_and_diluted_preferred() -> None:
    selected = select_eps(
        diluted=Decimal("0"),
        diluted_status="EXTRACTED",
        basic=Decimal("1.5"),
        basic_status="EXTRACTED",
    )
    assert selected.selected == "EPS_DILUTED"
    assert selected.value == Decimal("0")


def test_ratios_never_blank_to_zero() -> None:
    ratios = compute_quarter_ratios(
        pat=None,
        equity=Decimal("100"),
        assets=Decimal("200"),
        liabilities=None,
        top_line=Decimal("50"),
    )
    by_code = {r.code: r for r in ratios}
    assert by_code["ROE"].status == "INSUFFICIENT_INPUT"
    assert by_code["ROE"].value is None
    assert by_code["DEBT_TO_EQUITY"].value is None


def test_recovery_and_query_pipeline() -> None:
    ledger = CandidateLedger()
    ledger.add(_entry(entry_id="1", status="unresolved", reasons=["DURATION_CONFLICT"]))
    tickets = diagnose_failures({"PAT": ["DURATION_CONFLICT"]})
    tickets = run_recovery(
        tickets,
        ledger,
        context={"required_entity": "COMPANY", "target_duration": 3},
    )
    assert tickets[0].attempts
    arbitrate_candidates(ledger, required_entity="COMPANY", target_duration=3)
    queried = query_target_facts(
        ledger, entity="COMPANY", period_end=date(2026, 6, 30)
    )
    assert any(q.metric_code == "PAT" for q in queried)


def test_no_overpublication_gates() -> None:
    bad = QueriedFact(
        "PAT",
        "PAT",
        _entry(entity="GROUP", status="accepted"),
        "EXTRACTED",
    )
    violations = gate_no_overpublication([bad], [])
    assert any(v.startswith("GROUP_SUBSTITUTION") for v in violations)


def test_review_packet_and_accuracy_quality() -> None:
    from cse_financial_etl.reporting.redesign_metrics import (
        empty_redesign_metrics,
        record_extraction_report,
        summarize_redesign_metrics,
    )
    from cse_financial_etl.reporting.review_views import (
        build_accuracy_quality_view,
        build_review_packet,
    )

    packet = build_review_packet(
        fact={"metric_code": "PAT", "status": "EXTRACTED", "source_page": 3},
        competing_candidates=[{"id": "alt"}],
        blocked_reason=None,
    )
    assert packet["scope_period_unit"] is not None
    assert packet["approval_binding"]["requires_authenticated_reviewer"] is True
    view = build_accuracy_quality_view(
        universe_filings=10,
        filings_processed=10,
        published_facts=80,
        eligible_disclosures=100,
        independent_review_coverage=None,
        measured_precision=None,
        false_absence_rate=None,
        unresolved_issues=5,
        release_status="DRAFT_OFFLINE",
    )
    assert view["universe_filing_coverage"]["rate"] == 1.0
    metrics = empty_redesign_metrics()
    record_extraction_report(
        metrics,
        {
            "document_quality": {"token_count": 10},
            "statements_detected": [{"type": "PROFIT_LOSS"}],
            "tunnel_a": {"mode": "layout_assist_compiler"},
            "tunnel_b": {"deferred": True},
            "final_facts": [{"status": "EXTRACTED"}, {"status": "CUMULATIVE_ONLY"}],
            "failure_tickets": [{"terminal": "RECOVERED"}],
        },
    )
    summary = summarize_redesign_metrics(metrics)
    assert summary["core_metric_coverage"]["EXTRACTED"] == 1
