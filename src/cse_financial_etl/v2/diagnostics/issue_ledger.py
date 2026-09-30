"""V1/V2 disagreement ledger. V1 is a comparator, never truth."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from cse_financial_etl.v2.contracts.enums import DisagreementClass
from cse_financial_etl.v2.contracts.facts import SourceFact
from cse_financial_etl.v2.contracts.investigation import SOURCE_TARGET_METRICS


class LedgerRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: str
    pdf_sha: str
    issuer: str
    sector: str
    metric: str
    page: int | None
    v1_present: bool
    v1_value: str | None
    v1_context: str | None
    v2_source_fact_present: bool
    v2_value: str | None
    v2_context: str | None
    v2_first_failure: str | None
    v2_reason_codes: str
    disagreement_class: DisagreementClass
    source_truth_status: str = "NOT_ADJUDICATED"


def _v2_key(fact: SourceFact) -> tuple[str, str, str, int | None]:
    return (
        fact.metric_code,
        fact.entity_scope.value,
        fact.period_end.isoformat(),
        fact.duration_months,
    )


def _v1_key(row: dict[str, object]) -> tuple[str, str, str, int | None]:
    period = row.get("period_end")
    period_text = period.isoformat() if hasattr(period, "isoformat") else str(period or "")
    duration = row.get("duration_months")
    duration_i = int(duration) if isinstance(duration, int) else None
    return (
        str(row.get("metric_code") or ""),
        str(row.get("entity_scope") or ""),
        period_text,
        duration_i,
    )


def _same_number(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is None and right is None
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except Exception:
        return str(left) == str(right)


def _decimal_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def build_issue_ledger(
    *,
    pdf_sha: str,
    issuer: str,
    sector: str,
    v1_rows: Sequence[dict[str, object]],
    v2_facts: Sequence[SourceFact],
    v2_failures: dict[str, str] | None = None,
) -> tuple[LedgerRow, ...]:
    failures = v2_failures or {}
    v1_map: dict[tuple[str, str, str, int | None], dict[str, object]] = {}
    for row in v1_rows:
        if str(row.get("metric_code") or "") not in SOURCE_TARGET_METRICS:
            continue
        v1_map[_v1_key(row)] = row
    v2_map = {
        _v2_key(fact): fact
        for fact in v2_facts
        if fact.metric_code in SOURCE_TARGET_METRICS
    }
    keys = sorted(set(v1_map) | set(v2_map), key=lambda item: (item[0], item[1], item[2], item[3] or -1))
    rows: list[LedgerRow] = []
    for index, key in enumerate(keys, start=1):
        v1 = v1_map.get(key)
        v2 = v2_map.get(key)
        metric = key[0]
        if v1 is None and v2 is not None:
            klass = DisagreementClass.V2_ONLY_DISAGREEMENT
        elif v1 is not None and v2 is None:
            klass = DisagreementClass.REFERENCE_ONLY_DISAGREEMENT
        elif not _same_number(
            v1.get("normalized_value") if v1 is not None else None,
            v2.normalized_value if v2 is not None else None,
        ):
            klass = DisagreementClass.VALUE_DISAGREEMENT
        elif str(v1.get("comparison_role") if v1 else "") != (
            v2.comparison_role.value if v2 is not None else ""
        ):
            klass = DisagreementClass.CONTEXT_DISAGREEMENT
        else:
            klass = DisagreementClass.AGREEMENT
        rows.append(
            LedgerRow(
                issue_id=f"{issuer}-{metric}-{index}",
                pdf_sha=pdf_sha,
                issuer=issuer,
                sector=sector,
                metric=metric,
                page=v2.source_ref.page_number if v2 is not None else _optional_int(v1, "source_page"),
                v1_present=v1 is not None,
                v1_value=_decimal_text(v1.get("normalized_value") if v1 else None),
                v1_context=_context_v1(v1) if v1 is not None else None,
                v2_source_fact_present=v2 is not None,
                v2_value=format(v2.normalized_value, "f") if v2 is not None else None,
                v2_context=_context_v2(v2) if v2 is not None else None,
                v2_first_failure=None if v2 is not None else failures.get(metric),
                v2_reason_codes=",".join(v2.reason_codes) if v2 is not None else "",
                disagreement_class=klass,
            )
        )
    return tuple(rows)


def _optional_int(row: dict[str, object] | None, field: str) -> int | None:
    if row is None:
        return None
    value = row.get(field)
    return int(value) if isinstance(value, int) else None


def _context_v1(row: dict[str, object]) -> str:
    return "|".join(
        [
            str(row.get("entity_scope") or ""),
            str(row.get("period_end") or ""),
            str(row.get("duration_months") or ""),
            str(row.get("comparison_role") or ""),
        ]
    )


def _context_v2(fact: SourceFact) -> str:
    return "|".join(
        [
            fact.entity_scope.value,
            fact.period_end.isoformat(),
            str(fact.duration_months or ""),
            fact.comparison_role.value,
        ]
    )
