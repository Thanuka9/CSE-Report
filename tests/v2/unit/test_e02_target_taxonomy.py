"""E02 diagnostics must not turn absent STOCK duration into an error.

NO_TARGET_CANDIDATE is not source-verified ROW_NOT_FOUND; the latter belongs to
the independent N18 truth-scored failure taxonomy.
"""

from scripts.v2_e02_universe_candidate_trace import classify_n18_taxonomy


def test_stock_target_metrics_require_no_flow_duration() -> None:
    for metric in ("NAVPS", "TOTAL_EQUITY", "TOTAL_ASSETS", "TOTAL_LIABILITIES"):
        assert (
            classify_n18_taxonomy(
                stage="NONE", duration_status="UNRESOLVED", metric=metric
            )
            == "NONE"
        )


def test_flow_target_metric_missing_duration_is_failure() -> None:
    assert (
        classify_n18_taxonomy(
            stage="NONE", duration_status="UNRESOLVED", metric="PAT"
        )
        == "DURATION_UNRESOLVED"
    )


def test_first_failure_remains_primary_when_duration_also_unresolved() -> None:
    assert (
        classify_n18_taxonomy(
            stage="ENTITY_UNRESOLVED",
            duration_status="UNRESOLVED",
            metric="OPERATING_PROFIT",
        )
        == "ENTITY_UNRESOLVED"
    )


def test_existing_first_failure_passthrough() -> None:
    assert (
        classify_n18_taxonomy(
            stage="UNIT_UNRESOLVED", duration_status=None, metric="TOP_LINE"
        )
        == "UNIT_UNRESOLVED"
    )
