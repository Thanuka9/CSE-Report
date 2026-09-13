"""Single authoritative V2 concept registry."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Literal

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


_TRAILING_NOISE = re.compile(
    r"(?:\s*\((?:lkr|rs\.?|rs\.?\s*'?000|rupees?|in\s+lkr|in\s+rs\.?)\)"
    r"|\s+in\s+(?:lkr|rs\.?)"
    r"|\s*\(note\s*-?\s*\d+(?:\.\d+)*\)"
    r"|\s*\((?:basic(?:\s+and\s+diluted)?|diluted)\)"
    r"|\s*:\s*basic(?:\s+diluted)?)\s*$",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    cleaned = text.casefold().replace("/", " ").replace("-", " ")
    cleaned = re.sub(r"[.:]+$", "", cleaned)
    while True:
        nxt = _TRAILING_NOISE.sub("", cleaned)
        nxt = " ".join(nxt.split())
        if nxt == " ".join(cleaned.split()):
            return nxt
        cleaned = nxt


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
            "Profit before taxation",
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
        ),
        forbidden_aliases=("EBITDA", "Operating profit after taxes on financial services"),
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
        ),
        regime_aliases={
            "BANK": ("Gross income", "Interest income", "Total operating income"),
            "FINANCE_COMPANY": ("Total income", "Net operating income", "Income"),
            "SLFRS17": ("Insurance revenue",),
            "SLFRS4": ("Gross written premium", "Net earned premium"),
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
        exact_aliases=("Total equity", "Shareholders funds", "Total shareholders funds"),
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
        collisions: dict[str, set[str]] = defaultdict(set)
        for concept in concepts:
            aliases = list(concept.exact_aliases) + list(concept.synonyms)
            for values in concept.regime_aliases.values():
                aliases.extend(values)
            for alias in aliases:
                key = _norm(alias)
                owner = self._alias_index.get(key)
                if owner is not None and owner != concept.code:
                    collisions[key].update({owner, concept.code})
                else:
                    self._alias_index[key] = concept.code
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

    def lookup_alias(self, label: str) -> ConceptDefinition | None:
        code = self._alias_index.get(_norm(label))
        return self._by_code.get(code) if code else None

    def is_forbidden(self, label: str) -> bool:
        key = _norm(label)
        return any(
            key == _norm(item) for concept in self.concepts for item in concept.forbidden_aliases
        )


def load_registry() -> ConceptRegistry:
    return ConceptRegistry()


def normalize_label(label: str) -> str:
    return _norm(label)
