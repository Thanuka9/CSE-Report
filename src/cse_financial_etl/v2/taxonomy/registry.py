"""Single authoritative V2 concept registry."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import (
    AccountingRegime,
    PeriodBehavior,
    StatementType,
    UnitDimension,
)
from cse_financial_etl.v2.exceptions import V2Error


class RegistryConflictError(V2Error):
    """Duplicate or conflicting aliases in the concept registry."""


class ConceptDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    code: str
    display_name: str
    metric_type: str
    statement_types: tuple[StatementType, ...]
    period_behavior: PeriodBehavior
    unit_dimension: UnitDimension
    allowed_entity_profiles: tuple[AccountingRegime, ...] = (AccountingRegime.GENERAL,)
    accounting_regimes: tuple[str, ...] = ("DEFAULT",)
    exact_aliases: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    forbidden_aliases: tuple[str, ...] = ()
    source_only: bool = True
    derivation_allowed: bool = False
    regime_aliases: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if not value.strip() or value != value.upper():
            raise ValueError("concept code must be uppercase")
        return value


class AliasMatch(NamedTuple):
    concept: ConceptDefinition
    matched_alias: str
    alias_regime: str | None


_TRAILING_NOISE = re.compile(
    r"(?:\s*\((?:lkr|rs\.?|rs\.?\s*'?000|rupees?|in\s+lkr|in\s+rs\.?)\)"
    r"|\s+in\s+(?:lkr|rs\.?)"
    r"|\s*\(note\s*-?\s*\d+(?:\.\d+)*\)"
    r"|\s*\((?:basic(?:\s+and\s+diluted)?|diluted)\)"
    r"|\s*:\s*basic(?:\s+diluted)?)\s*$",
    re.IGNORECASE,
)
# OCR / table bleed after a clean account label (applied only to source labels).
_TRAILING_OCR_JUNK = re.compile(
    r"(?:\s*\|+\s*)+$"
    r"|(?:\s+\d+o(?:\s*/\s*|\s+)o(?:\s+[\d,().a-z]+)*)$"
    r"|(?:\s+[a-z]*\d[a-z\d]*(?:\s+[|\d,().a-z]+)*)$"
    r"|(?:\s+\d[\d,]*(?:\.\d+)?%?(?:\s+\d[\d,]*(?:\.\d+)?%?)*)$",
    re.IGNORECASE,
)
_LABEL_ONLY_TRAILING = re.compile(
    r"(?:\s+(?:for\s+the\s+period|annualized|annualised)"
    r"|\s+to\s+equity\s+holders)\s*$",
    re.IGNORECASE,
)


def _norm(text: str, *, label_cleanup: bool = False) -> str:
    cleaned = text.casefold().replace("/", " ").replace("-", " ")
    cleaned = cleaned.replace("|", " ").replace("'", "").replace("’", "")
    cleaned = re.sub(r"^[\[\(]+", "", cleaned)
    cleaned = " ".join(cleaned.split())
    while True:
        nxt = _TRAILING_NOISE.sub("", cleaned)
        if label_cleanup:
            nxt = _TRAILING_OCR_JUNK.sub("", nxt)
        # Strip dangling punctuation only — never bare ")" which breaks
        # "(basic and diluted)" / "(Rs.)" before the next noise pass.
        nxt = re.sub(r"[,.:;]+$", "", nxt)
        nxt = " ".join(nxt.split())
        if nxt == cleaned:
            return nxt
        cleaned = nxt


def normalize_label(label: str) -> str:
    """Normalize a source row label for matching (includes OCR cleanup)."""
    return _norm(label, label_cleanup=True)


def _alias_lookup_keys(label: str) -> tuple[str, ...]:
    """Exact key plus qualifier-stripped / re-noised variants for source labels."""
    primary = normalize_label(label)
    keys: list[str] = [primary]
    stripped = _LABEL_ONLY_TRAILING.sub("", primary).strip()
    stripped = " ".join(stripped.split())
    if stripped and stripped not in keys:
        keys.append(stripped)
        renoised = _norm(stripped, label_cleanup=True)
        if renoised and renoised not in keys:
            keys.append(renoised)
    return tuple(keys)


CORE_CONCEPTS: tuple[ConceptDefinition, ...] = (
    ConceptDefinition(
        code="PAT",
        display_name="Profit After Tax",
        metric_type="MONETARY_ABSOLUTE",
        statement_types=(StatementType.INCOME_STATEMENT,),
        period_behavior=PeriodBehavior.FLOW,
        unit_dimension=UnitDimension.MONETARY,
        exact_aliases=(
            "Profit for the period",
            "Profit after tax",
            "Profit after taxation",
            "Net profit for the period",
            "Profit / (loss) for the period",
            "Profit/(loss) for the period",
            "Profit / (loss) for the Period",
            "Profit after Tax from continued operations for the period",
            "Profit/(Loss) for the Period from Continuing Operations",
            "Profit/ (Loss) for the period from continuing operations",
            "Profit for the period from continuing operations",
            "Loss for the period",
            "(Loss)/ Profit for the period",
            "(Loss)/Profit for the period",
        ),
        forbidden_aliases=(
            "Profit attributable to owners",
            "Profit attributable to equity holders",
            "Profit attributable to owners of the parent",
        ),
    ),
    ConceptDefinition(
        code="PBT",
        display_name="Profit Before Tax",
        metric_type="MONETARY_ABSOLUTE",
        statement_types=(StatementType.INCOME_STATEMENT,),
        period_behavior=PeriodBehavior.FLOW,
        unit_dimension=UnitDimension.MONETARY,
        exact_aliases=(
            "Profit before tax",
            "Profit before income tax",
            "Profit before income tax expense",
            "Profit before taxation",
            "Profit before taxation from operations",
            "Net profit/(loss) before taxation",
            "Net profit before taxation",
            "Profit before tax for the period",
            "Profit before Tax from continued operations",
            "Profit/(Loss) Before Tax from Continuing Operations",
            "Profit/ (Loss) before tax for the period",
            "Profit/(loss) before tax",
            "Loss before tax",
        ),
    ),
    ConceptDefinition(
        code="OPERATING_PROFIT",
        display_name="Operating Profit",
        metric_type="MONETARY_ABSOLUTE",
        statement_types=(StatementType.INCOME_STATEMENT,),
        period_behavior=PeriodBehavior.FLOW,
        unit_dimension=UnitDimension.MONETARY,
        exact_aliases=(
            "Operating profit",
            "Results from operating activities",
            "Profit from operations",
            "Profit from operating activities",
            "Profit from Operation",
            "Profit / (loss) from operating activities",
            "Profit/(loss) from operations",
            "Profit / (loss) from operations",
            "Operating profit/(loss)",
            "Operating profit before tax on financial services",
            "Operating profit before taxes on financial services",
            "Operating profit/(loss) before VAT on financial services & SSCL",
            "Operating profit/(loss) before VAT on financial services and SSCL",
            "Profit before tax on financial services",
            "Profit before taxes on financial services",
            "Profit before value added tax (VAT) & social security contribution Levy (SSCL) on financial services",
            "Profit before value added tax (VAT) and social security contribution levy (SSCL) on financial services",
            "Profit before VAT & SSCL on financial services",
            "Profit before VAT and SSCL on financial services",
            "Profit before Social Security Contribution Levy / Value Added Tax on financial services",
            "Profit before Social Security Contribution Levy and Value Added Tax on financial services",
        ),
        forbidden_aliases=(
            "EBITDA",
            "Operating profit after taxes on financial services",
            "Operating profit/(loss) after VAT on financial services & SSCL",
            "Operating profit/(loss) after VAT on financial services and SSCL",
            "Operating profit/(loss) after VAT on financial services and SCCL",
            "Operating profit after VAT on financial services & SSCL",
            "Operating profit after VAT on financial services and SSCL",
            "Operating profit after VAT on financial services and SCCL",
        ),
    ),
    ConceptDefinition(
        code="TOP_LINE",
        display_name="Revenue / Gross Income",
        metric_type="MONETARY_ABSOLUTE",
        statement_types=(StatementType.INCOME_STATEMENT,),
        period_behavior=PeriodBehavior.FLOW,
        unit_dimension=UnitDimension.MONETARY,
        allowed_entity_profiles=(
            AccountingRegime.GENERAL,
            AccountingRegime.BANK,
            AccountingRegime.FINANCE_COMPANY,
            AccountingRegime.INSURANCE,
        ),
        exact_aliases=(
            "Revenue",
            "Total revenue",
            "Net sales",
            "Turnover",
            "Revenue from contracts with customers",
            "Gross written contribution (premium)",
            "Gross written contribution",
        ),
        regime_aliases={
            "BANK": ("Gross income", "Interest income", "Total operating income"),
            "FINANCE_COMPANY": (
                "Total income",
                "Net operating income",
                "Income",
                "Gross income",
                "Interest income",
                "Total operating income",
            ),
            "SLFRS17": ("Insurance revenue",),
            "SLFRS4": (
                "Gross written premium",
                "Gross written contribution (premium)",
                "Gross written contribution",
                "Net earned premium",
            ),
        },
    ),
    ConceptDefinition(
        code="EPS_BASIC",
        display_name="Basic EPS",
        metric_type="MONETARY_PER_SHARE",
        statement_types=(StatementType.INCOME_STATEMENT, StatementType.EPS_NOTE),
        period_behavior=PeriodBehavior.FLOW,
        unit_dimension=UnitDimension.PER_SHARE,
        exact_aliases=(
            "Basic earnings per share",
            "Basic earnings per ordinary share",
            "Earnings per share",
            "Basic earnings/(loss) per share",
            "Basic earning per share",
            "Earning per share",
            "Earnings per share : Basic/Diluted",
            "Basic/Diluted earnings per ordinary share",
            "Basic/Diluted earnings per share",
            "Basic/Diluted earnings/(deficit) per share",
            "Basic and diluted earnings per share",
            "Basic / diluted earnings per share",
            "Earnings per share basic",
            "Earning per share basic",
            "Earnings per share basic diluted",
            "Earnings/(Loss) per share basic",
        ),
    ),
    ConceptDefinition(
        code="EPS_DILUTED",
        display_name="Diluted EPS",
        metric_type="MONETARY_PER_SHARE",
        statement_types=(StatementType.INCOME_STATEMENT, StatementType.EPS_NOTE),
        period_behavior=PeriodBehavior.FLOW,
        unit_dimension=UnitDimension.PER_SHARE,
        exact_aliases=(
            "Diluted earnings per share",
            "Diluted earnings per ordinary share",
            "Earnings per share diluted",
            "Earning per share diluted",
            "Earnings/(Loss) per share diluted",
        ),
    ),
    ConceptDefinition(
        code="NAVPS",
        display_name="Net Assets Per Share",
        metric_type="MONETARY_PER_SHARE",
        statement_types=(StatementType.BALANCE_SHEET, StatementType.EPS_NOTE),
        period_behavior=PeriodBehavior.POINT_IN_TIME,
        unit_dimension=UnitDimension.PER_SHARE,
        exact_aliases=(
            "Net assets per share",
            "Net asset value per share",
            "Net assets value per share",
            "Net asset value per ordinary share",
            "Net book value per share",
            "Net asset per share",
        ),
    ),
    ConceptDefinition(
        code="TOTAL_EQUITY",
        display_name="Total Equity",
        metric_type="MONETARY_ABSOLUTE",
        statement_types=(StatementType.BALANCE_SHEET,),
        period_behavior=PeriodBehavior.STOCK,
        unit_dimension=UnitDimension.MONETARY,
        exact_aliases=(
            "Total equity",
            "Shareholders funds",
            "Total shareholders funds",
            "Total shareholders' funds",
            "Shareholders' funds",
        ),
        forbidden_aliases=(
            "Equity attributable to owners",
            "Equity attributable to owners of the parent",
            "Equity attributable to equity holders",
        ),
    ),
    ConceptDefinition(
        code="TOTAL_ASSETS",
        display_name="Total Assets",
        metric_type="MONETARY_ABSOLUTE",
        statement_types=(StatementType.BALANCE_SHEET,),
        period_behavior=PeriodBehavior.STOCK,
        unit_dimension=UnitDimension.MONETARY,
        exact_aliases=("Total assets",),
    ),
    ConceptDefinition(
        code="TOTAL_LIABILITIES",
        display_name="Total Liabilities",
        metric_type="MONETARY_ABSOLUTE",
        statement_types=(StatementType.BALANCE_SHEET,),
        period_behavior=PeriodBehavior.STOCK,
        unit_dimension=UnitDimension.MONETARY,
        exact_aliases=("Total liabilities", "Total liability"),
        source_only=True,
        derivation_allowed=False,
    ),
    ConceptDefinition(
        code="EPS_SELECTED",
        display_name="EPS Selected",
        metric_type="MONETARY_PER_SHARE",
        statement_types=(StatementType.INCOME_STATEMENT, StatementType.EPS_NOTE),
        period_behavior=PeriodBehavior.FLOW,
        unit_dimension=UnitDimension.PER_SHARE,
        source_only=False,
        derivation_allowed=True,
    ),
    ConceptDefinition(
        code="LIABILITIES_TO_EQUITY",
        display_name="Liabilities / Equity",
        metric_type="RATIO",
        statement_types=(StatementType.BALANCE_SHEET,),
        period_behavior=PeriodBehavior.STOCK,
        unit_dimension=UnitDimension.RATIO,
        source_only=False,
        derivation_allowed=True,
    ),
    ConceptDefinition(
        code="ROE",
        display_name="ROE",
        metric_type="RATIO",
        statement_types=(StatementType.INCOME_STATEMENT, StatementType.BALANCE_SHEET),
        period_behavior=PeriodBehavior.FLOW,
        unit_dimension=UnitDimension.RATIO,
        source_only=False,
        derivation_allowed=True,
    ),
    ConceptDefinition(
        code="ROA",
        display_name="ROA",
        metric_type="RATIO",
        statement_types=(StatementType.INCOME_STATEMENT, StatementType.BALANCE_SHEET),
        period_behavior=PeriodBehavior.FLOW,
        unit_dimension=UnitDimension.RATIO,
        source_only=False,
        derivation_allowed=True,
    ),
    ConceptDefinition(
        code="NPM",
        display_name="NPM",
        metric_type="RATIO",
        statement_types=(StatementType.INCOME_STATEMENT,),
        period_behavior=PeriodBehavior.FLOW,
        unit_dimension=UnitDimension.RATIO,
        source_only=False,
        derivation_allowed=True,
    ),
    ConceptDefinition(
        code="LAST_TRADED_PRICE",
        display_name="Last Traded Price",
        metric_type="MONETARY_PER_SHARE",
        statement_types=(StatementType.OTHER_FINANCIAL_STATEMENT,),
        period_behavior=PeriodBehavior.POINT_IN_TIME,
        unit_dimension=UnitDimension.PER_SHARE,
        exact_aliases=("Last traded price", "Last traded"),
        forbidden_aliases=("Closing market price", "Closing price"),
        source_only=True,
    ),
)


class ConceptRegistry:
    def __init__(self, concepts: tuple[ConceptDefinition, ...] = CORE_CONCEPTS) -> None:
        self.concepts = concepts
        self._by_code = {item.code: item for item in concepts}
        if len(self._by_code) != len(concepts):
            raise RegistryConflictError("duplicate concept codes")
        self._alias_index: dict[str, str] = {}
        self._alias_original: dict[str, str] = {}
        self._regime_alias_index: dict[str, dict[str, str]] = defaultdict(dict)
        self._regime_alias_original: dict[str, dict[str, str]] = defaultdict(dict)
        collisions: dict[str, set[str]] = defaultdict(set)
        for concept in concepts:
            for alias in (*concept.exact_aliases, *concept.synonyms):
                key = _norm(alias)
                owner = self._alias_index.get(key)
                if owner is not None and owner != concept.code:
                    collisions[key].update({owner, concept.code})
                else:
                    self._alias_index[key] = concept.code
                    self._alias_original.setdefault(key, alias)
            for regime, values in concept.regime_aliases.items():
                bucket = self._regime_alias_index[regime.upper()]
                originals = self._regime_alias_original[regime.upper()]
                for alias in values:
                    key = _norm(alias)
                    owner = bucket.get(key)
                    if owner is not None and owner != concept.code:
                        collisions[f"{regime}:{key}"].update({owner, concept.code})
                    else:
                        bucket[key] = concept.code
                        originals.setdefault(key, alias)
            for forbidden in concept.forbidden_aliases:
                forbidden_key = _norm(forbidden)
                if (
                    forbidden_key in self._alias_index
                    and self._alias_index[forbidden_key] == concept.code
                ):
                    raise RegistryConflictError(
                        f"forbidden alias overlaps exact alias: {forbidden}"
                    )
        if collisions:
            raise RegistryConflictError(f"duplicate aliases: {dict(collisions)}")

    def get(self, code: str) -> ConceptDefinition:
        return self._by_code[code]

    def lookup_alias(
        self, label: str, *, regimes: tuple[str, ...] = ()
    ) -> ConceptDefinition | None:
        hit = self.match_alias(label, regimes=regimes)
        return None if hit is None else hit.concept

    def match_alias(self, label: str, *, regimes: tuple[str, ...] = ()) -> AliasMatch | None:
        for key in _alias_lookup_keys(label):
            hit = self._match_normalized(key, label=label, regimes=regimes)
            if hit is not None:
                return hit
        return None

    def _match_normalized(
        self, key: str, *, label: str, regimes: tuple[str, ...]
    ) -> AliasMatch | None:
        code = self._alias_index.get(key)
        if code is not None:
            return AliasMatch(
                concept=self._by_code[code],
                matched_alias=self._alias_original.get(key, label),
                alias_regime=None,
            )
        for regime in regimes:
            bucket = self._regime_alias_index.get(regime.upper(), {})
            code = bucket.get(key)
            if code is None:
                continue
            original = self._regime_alias_original.get(regime.upper(), {}).get(key, label)
            return AliasMatch(
                concept=self._by_code[code],
                matched_alias=original,
                alias_regime=regime.upper(),
            )
        return None

    def original_alias(self, normalized: str, *, regimes: tuple[str, ...] = ()) -> str:
        if normalized in self._alias_original:
            return self._alias_original[normalized]
        for regime in regimes:
            found = self._regime_alias_original.get(regime.upper(), {}).get(normalized)
            if found is not None:
                return found
        return normalized

    def alias_regime(self, normalized: str, *, regimes: tuple[str, ...] = ()) -> str | None:
        if normalized in self._alias_index:
            return None
        for regime in regimes:
            if normalized in self._regime_alias_index.get(regime.upper(), {}):
                return regime.upper()
        return None

    def regime_aliases(self, *, regimes: tuple[str, ...]) -> dict[str, str]:
        choices: dict[str, str] = {}
        for regime in regimes:
            choices.update(self._regime_alias_index.get(regime.upper(), {}))
        return choices

    def is_regime_alias(self, label: str) -> bool:
        key = normalize_label(label)
        return any(key in bucket for bucket in self._regime_alias_index.values())

    def is_forbidden(self, label: str) -> bool:
        key = normalize_label(label)
        return any(
            key == _norm(item) for concept in self.concepts for item in concept.forbidden_aliases
        )


def load_registry() -> ConceptRegistry:
    return ConceptRegistry()
