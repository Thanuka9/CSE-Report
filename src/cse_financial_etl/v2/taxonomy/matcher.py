"""Row concept matching: exact, controlled, RapidFuzz, then abstain."""

from __future__ import annotations

from rapidfuzz import fuzz, process

from cse_financial_etl.v2.contracts.concepts import ConceptCandidate
from cse_financial_etl.v2.contracts.enums import AccountingRegime, MatchKind, StatementType
from cse_financial_etl.v2.contracts.statement import StatementRow
from cse_financial_etl.v2.taxonomy.registry import ConceptRegistry, load_registry, normalize_label

_FUZZY_FLOOR = 90
_AMBIGUITY_DELTA = 2

_INSURANCE_REGIMES = ("INSURANCE", "SLFRS4", "SLFRS17")
_ISSUER_TYPE_TO_REGIME = {
    "BANK": AccountingRegime.BANK,
    "FINANCE_COMPANY": AccountingRegime.FINANCE_COMPANY,
    "FINANCE": AccountingRegime.FINANCE_COMPANY,
    "INSURANCE": AccountingRegime.INSURANCE,
    "SLFRS4": AccountingRegime.SLFRS4,
    "SLFRS17": AccountingRegime.SLFRS17,
}


def regimes_for(accounting_regime: AccountingRegime | None) -> tuple[str, ...]:
    if accounting_regime is None or accounting_regime is AccountingRegime.GENERAL:
        return ()
    if accounting_regime is AccountingRegime.INSURANCE:
        return _INSURANCE_REGIMES
    return (accounting_regime.value,)


def accounting_regime_for(
    *,
    issuer_id: str = "",
    issuer_name: str = "",
    issuer_type: str = "",
) -> AccountingRegime:
    """Map master-data issuer type / legal name onto an accounting regime."""

    mapped = _ISSUER_TYPE_TO_REGIME.get(str(issuer_type).strip().upper())
    if mapped is not None:
        return mapped
    from cse_financial_etl.config import infer_issuer_type

    for identity in (issuer_name, issuer_id):
        if not identity:
            continue
        kind = infer_issuer_type(identity)
        mapped = _ISSUER_TYPE_TO_REGIME.get(kind)
        if mapped is not None:
            return mapped
    return AccountingRegime.GENERAL


class RegistryMatcher:
    def __init__(self, registry: ConceptRegistry | None = None) -> None:
        self.registry = registry or load_registry()

    def candidates(
        self,
        row: StatementRow,
        *,
        statement_type: StatementType,
        accounting_regime: AccountingRegime | None = None,
    ) -> list[ConceptCandidate]:
        label = normalize_label(row.normalized_label or row.raw_label)
        regimes = regimes_for(accounting_regime)
        if self.registry.is_forbidden(label) or "discontinued" in label:
            return [ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)]
        exact = self.registry.lookup_alias(label, regimes=regimes)
        if exact is not None:
            if statement_type not in exact.statement_types:
                return [ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)]
            kind = (
                MatchKind.EXACT_ALIAS
                if normalize_label(row.raw_label) == label
                else MatchKind.CONTROLLED_ALIAS
            )
            return [ConceptCandidate(metric_code=exact.code, match_kind=kind, score=100.0)]
        if self.registry.is_regime_alias(label):
            return [ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)]
        diluted_only = "diluted" in label and "basic" not in label
        choices: dict[str, str] = dict(self.registry.regime_aliases(regimes=regimes))
        for concept in self.registry.concepts:
            if statement_type not in concept.statement_types or not concept.source_only:
                continue
            if diluted_only and concept.code == "EPS_BASIC":
                continue
            for alias in (*concept.exact_aliases, *concept.synonyms):
                choices[normalize_label(alias)] = concept.code
        if not choices:
            return [ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)]
        ranked = process.extract(label, list(choices), scorer=fuzz.token_set_ratio, limit=3)
        viable = [
            (alias, score, choices[alias]) for alias, score, _ in ranked if score >= _FUZZY_FLOOR
        ]
        if not viable:
            return [ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)]
        if "operat" not in label:
            # "Taxes on financial services" must not fuzzy-match operating profit.
            viable = [item for item in viable if item[2] != "OPERATING_PROFIT"]
        if not viable:
            return [ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)]
        best_score = viable[0][1]
        top = [item for item in viable if best_score - item[1] <= _AMBIGUITY_DELTA]
        codes = {item[2] for item in top}
        if len(codes) != 1:
            return [
                ConceptCandidate(
                    metric_code=code, match_kind=MatchKind.FUZZY, score=float(best_score)
                )
                for code in sorted(codes)
            ] + [
                ConceptCandidate(
                    metric_code=None, match_kind=MatchKind.ABSTAIN, score=float(best_score)
                )
            ]
        return [
            ConceptCandidate(
                metric_code=next(iter(codes)),
                match_kind=MatchKind.FUZZY,
                score=float(best_score),
            )
        ]
