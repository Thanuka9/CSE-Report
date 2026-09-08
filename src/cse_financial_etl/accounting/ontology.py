"""Richer accounting ontology (Revision 2 §15). Maps concepts, not final 14 outputs."""

from __future__ import annotations

import re

PROFIT_LOSS_CONCEPTS: tuple[str, ...] = (
    "TOP_LINE",
    "REVENUE",
    "GROSS_INCOME",
    "TOTAL_INCOME",
    "INTEREST_INCOME",
    "INTEREST_EXPENSE",
    "NET_INTEREST_INCOME",
    "TOTAL_OPERATING_INCOME",
    "NET_OPERATING_INCOME",
    "FEE_INCOME",
    "TRADING_INCOME",
    "INSURANCE_REVENUE",
    "COST_OF_SALES",
    "GROSS_PROFIT",
    "OTHER_OPERATING_INCOME",
    "DISTRIBUTION_EXPENSE",
    "ADMINISTRATIVE_EXPENSE",
    "OTHER_OPERATING_EXPENSE",
    "IMPAIRMENT",
    "OPERATING_PROFIT",
    "FINANCE_INCOME",
    "FINANCE_COST",
    "ASSOCIATE_JV_RESULT",
    "PBT",
    "INCOME_TAX",
    "CONTINUING_OPERATIONS_RESULT",
    "DISCONTINUED_OPERATIONS_RESULT",
    "PAT",
    "ATTRIBUTION_OWNERS",
    "ATTRIBUTION_NCI",
    "EPS_BASIC",
    "EPS_DILUTED",
    "DPS",
    "WEIGHTED_AVG_SHARES",
)

FINANCIAL_POSITION_CONCEPTS: tuple[str, ...] = (
    "NON_CURRENT_ASSETS",
    "CURRENT_ASSETS",
    "TOTAL_ASSETS",
    "SHARE_CAPITAL",
    "RESERVES",
    "EQUITY_ATTRIBUTABLE_TO_OWNERS",
    "NCI_EQUITY",
    "TOTAL_EQUITY",
    "NON_CURRENT_LIABILITIES",
    "CURRENT_LIABILITIES",
    "TOTAL_LIABILITIES",
    "TOTAL_EQUITY_AND_LIABILITIES",
    "ORDINARY_SHARES",
    "NAVPS",
)

# Concepts that may satisfy the TOP_LINE publish field, in preference order.
TOP_LINE_FAMILY: tuple[str, ...] = (
    "REVENUE",
    "GROSS_INCOME",
    "INSURANCE_REVENUE",
    "TOTAL_INCOME",
    "TOTAL_OPERATING_INCOME",
    "INTEREST_INCOME",
    "NET_INTEREST_INCOME",
    "NET_OPERATING_INCOME",
    "TOP_LINE",
)

# Target projection codes used by the 14-field publish contract.
TARGET_CONCEPT_MAP: dict[str, str] = {
    "PAT": "PAT",
    "PBT": "PBT",
    "EPS_BASIC": "EPS_BASIC",
    "EPS_DILUTED": "EPS_DILUTED",
    "NAVPS": "NAVPS",
    "OPERATING_PROFIT": "OPERATING_PROFIT",
    "TOTAL_EQUITY": "TOTAL_EQUITY",
    "TOTAL_ASSETS": "TOTAL_ASSETS",
    "TOTAL_LIABILITIES": "TOTAL_LIABILITIES",
    **{concept: "TOP_LINE" for concept in TOP_LINE_FAMILY},
}

# Statement families a concept may legitimately come from.
FLOW_CONCEPTS: frozenset[str] = frozenset(PROFIT_LOSS_CONCEPTS)
STOCK_CONCEPTS: frozenset[str] = frozenset(FINANCIAL_POSITION_CONCEPTS)


def all_concepts() -> tuple[str, ...]:
    return PROFIT_LOSS_CONCEPTS + FINANCIAL_POSITION_CONCEPTS


def _rx(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


# Anchored label patterns (applied to the normalized label; see semantic_candidates).
CONCEPT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "REVENUE": _rx(
        r"^revenue(?: from contracts with customers)?$",
        r"^revenue from (?:contracts|operations|sale)",
        r"^(?:total|net|gross) revenue$",
        r"^(?:net )?sales(?: revenue)?$",
        r"^turnover$",
        r"^total turnover$",
    ),
    "GROSS_INCOME": _rx(r"^gross income$"),
    "TOTAL_INCOME": _rx(r"^income$", r"^total income$"),
    "TOTAL_OPERATING_INCOME": _rx(r"^total operating income$"),
    "NET_OPERATING_INCOME": _rx(r"^net operating income$"),
    "INTEREST_INCOME": _rx(r"^interest income$", r"^interest and similar income$"),
    "INTEREST_EXPENSE": _rx(r"^interest expenses?$", r"^interest and similar expenses?$"),
    "NET_INTEREST_INCOME": _rx(r"^net interest income$"),
    "INSURANCE_REVENUE": _rx(
        r"^insurance revenue$",
        r"^gross written premiums?$",
        r"^net earned premiums?$",
    ),
    "FEE_INCOME": _rx(r"^(?:net )?fee and commission income$"),
    "COST_OF_SALES": _rx(r"^cost of (?:sales|goods sold|services)$", r"^direct costs?$"),
    "GROSS_PROFIT": _rx(r"^gross profit$"),
    "OTHER_OPERATING_INCOME": _rx(r"^other (?:operating )?income$", r"^net other operating income$"),
    "DISTRIBUTION_EXPENSE": _rx(r"^(?:selling and )?distribution (?:expenses?|costs?)$", r"^selling and distribution expenses?$"),
    "ADMINISTRATIVE_EXPENSE": _rx(r"^administrative? (?:expenses?|costs?)$", r"^administration expenses?$"),
    "OTHER_OPERATING_EXPENSE": _rx(r"^other (?:operating )?expenses?$"),
    "IMPAIRMENT": _rx(r"^(?:net )?impairment"),
    "OPERATING_PROFIT": _rx(
        r"^results? (?:from|of) operating activities$",
        r"^operating profit(?: before taxes? on financial services)?$",
        r"^profit from operations?$",
        r"^profit from operating activities$",
        r"^results? from operations?$",
        r"^operating results?$",
        r"^ebit$",
        r"^earnings before interest and tax(?:es|ation)?$",
    ),
    "FINANCE_INCOME": _rx(r"^finance income$"),
    "FINANCE_COST": _rx(r"^finance costs?$", r"^finance expenses?$"),
    "ASSOCIATE_JV_RESULT": _rx(r"^share of (?:profit|loss|results?).*(?:associates?|joint ventures?)", r"^share of joint venture"),
    "PBT": _rx(
        r"^profit before (?:income )?tax(?:ation)?$",
        r"^profit before (?:income )?tax(?:ation)? from continuing operations$",
        r"^loss before (?:income )?tax(?:ation)?$",
    ),
    "INCOME_TAX": _rx(
        r"^income tax(?: expenses?| reversal| charge)?$",
        r"^tax(?:ation)?(?: expenses?)?$",
        r"^income tax expenses? reversal$",
    ),
    "PAT": _rx(
        r"^(?:net )?profit for the (?:period|quarter|year)$",
        r"^(?:net )?loss for the (?:period|quarter|year)$",
        r"^(?:net )?profit after (?:income )?tax(?:ation)?$",
        r"^profit for the (?:period|quarter|year) from continuing operations$",
        r"^profit(?: for the (?:period|quarter|year))? attributable to (?:the )?(?:equity holders|owners|shareholders)",
    ),
    "ATTRIBUTION_OWNERS": _rx(
        r"^(?:equity holders|owners|shareholders) of the (?:parent|company|bank)",
        r"^equity holders of the parent company$",
        r"^attributable to (?:the )?(?:equity holders|owners|shareholders)",
    ),
    "ATTRIBUTION_NCI": _rx(r"^non[- ]?controlling interests?$", r"^minority interests?$"),
    "EPS_BASIC": _rx(
        r"^basic(?: ?/ ?diluted)? (?:earnings|loss|earning) per (?:ordinary )?share",
        r"^(?:earnings|loss) per (?:ordinary )?share basic",
        r"^earnings per (?:ordinary )?share$",
        r"^earnings per share for the (?:period|quarter|year)",
        r"^basic eps$",
        r"^eps basic$",
        r"^basic$",
    ),
    "EPS_DILUTED": _rx(
        r"^diluted (?:earnings|loss|earning) per (?:ordinary )?share",
        r"^basic ?/ ?diluted (?:earnings|loss) per (?:ordinary )?share",
        r"^(?:earnings|loss) per (?:ordinary )?share diluted",
        r"^diluted eps$",
        r"^eps diluted$",
        r"^diluted$",
    ),
    "DPS": _rx(r"^dividends? per (?:ordinary )?share"),
    "TOTAL_ASSETS": _rx(r"^total assets$"),
    "TOTAL_EQUITY": _rx(
        r"^total equity$",
        r"^total (?:shareholders|shareholders') equity$",
        r"^equity attributable to (?:equity holders|owners) of the (?:parent|company|bank)$",
        r"^total (?:shareholders|shareholders') funds$",
        r"^shareholders funds$",
    ),
    "TOTAL_LIABILITIES": _rx(r"^total liabilit(?:y|ies)$"),
    "TOTAL_EQUITY_AND_LIABILITIES": _rx(r"^total (?:equity and liabilities|liabilities and equity)$"),
    "NAVPS": _rx(
        r"^net assets? value per (?:ordinary )?share",
        r"^net assets? per (?:ordinary )?share",
        r"^net book value per (?:ordinary )?share",
        r"^nav(?:ps)?(?: per (?:ordinary )?share)?$",
    ),
    "CURRENT_LIABILITIES": _rx(r"^(?:total )?current liabilities$"),
    "NON_CURRENT_LIABILITIES": _rx(r"^(?:total )?non[- ]?current liabilities$"),
    "CURRENT_ASSETS": _rx(r"^(?:total )?current assets$"),
    "NON_CURRENT_ASSETS": _rx(r"^(?:total )?non[- ]?current assets$"),
    "WEIGHTED_AVG_SHARES": _rx(r"^weighted average number of (?:ordinary )?shares"),
    "ORDINARY_SHARES": _rx(r"^number of (?:ordinary )?shares"),
}

# Labels that must never be read as the concept even when fuzzy similarity is high.
CONCEPT_EXCLUSIONS: dict[str, tuple[re.Pattern[str], ...]] = {
    "REVENUE": _rx(r"reserve", r"comprehensive", r"tax", r"other", r"finance", r"cost"),
    "GROSS_INCOME": _rx(r"comprehensive", r"tax", r"other"),
    "TOTAL_INCOME": _rx(r"comprehensive", r"tax", r"other", r"interest", r"operating", r"finance", r"fee"),
    "TOTAL_OPERATING_INCOME": _rx(r"comprehensive", r"other", r"expense"),
    "NET_OPERATING_INCOME": _rx(r"comprehensive", r"other", r"expense"),
    "INTEREST_INCOME": _rx(r"^net", r"expense", r"other"),
    "NET_INTEREST_INCOME": _rx(r"expense", r"after"),
    "OPERATING_PROFIT": _rx(
        r"before working capital",
        r"after impairment",
        r"after tax on financial",
        r"per share",
        r"depreciation",
        r"^profit for the (?:period|quarter|year)",
        r"before tax",
    ),
    "PBT": _rx(
        r"after", r"per share", r"comprehensive", r"discontinued", r"financial services", r"^profit for the (?:period|quarter|year)"
    ),
    "PAT": _rx(
        r"before",
        r"comprehensive",
        r"per share",
        r"non[- ]?controlling",
        r"minority",
        r"discontinued",
        r"from operations",
        r"operating",
        r"attributable to:?$",
    ),
    "INCOME_TAX": _rx(r"before", r"after", r"profit", r"deferred tax (?:assets|liabilities)", r"financial services"),
    "EPS_BASIC": _rx(r"diluted(?! ?/)", r"dividend", r"net asset"),
    "EPS_DILUTED": _rx(r"dividend", r"net asset", r"^basic(?! ?/)"),
    "TOTAL_ASSETS": _rx(r"net", r"per share", r"current", r"financial", r"equity"),
    "TOTAL_EQUITY": _rx(r"liabilities", r"per share", r"and", r"assets"),
    "TOTAL_LIABILITIES": _rx(r"equity", r"current", r"and", r"per share"),
    "NAVPS": _rx(r"earnings"),
}

# Concept → alias phrases kept for fuzzy fallback (regex is the primary channel).
CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "REVENUE": ("revenue", "net revenue", "total revenue", "net sales", "turnover", "revenue from contracts with customers"),
    "GROSS_INCOME": ("gross income",),
    "TOTAL_INCOME": ("income", "total income"),
    "TOTAL_OPERATING_INCOME": ("total operating income",),
    "NET_OPERATING_INCOME": ("net operating income",),
    "INTEREST_INCOME": ("interest income",),
    "NET_INTEREST_INCOME": ("net interest income",),
    "INSURANCE_REVENUE": ("insurance revenue", "gross written premium", "net earned premium"),
    "OPERATING_PROFIT": (
        "operating profit",
        "results from operating activities",
        "profit from operations",
        "operating profit before tax on financial services",
        "results of operating activities",
        "profit from operating activities",
        "results from operations",
    ),
    "PBT": ("profit before tax", "profit before taxation", "profit before income tax", "loss before tax"),
    "PAT": (
        "profit for the period",
        "profit for the quarter",
        "profit after tax",
        "profit after taxation",
        "net profit after tax",
        "loss for the period",
        "net profit for the period",
        "profit attributable to equity holders",
        "profit attributable to owners of the company",
        "profit attributable to shareholders of the company",
    ),
    "INCOME_TAX": ("income tax", "taxation", "tax expense", "income tax expense"),
    "EPS_BASIC": ("basic earnings per share", "earnings per share basic", "earnings per ordinary share", "basic loss per share"),
    "EPS_DILUTED": ("diluted earnings per share", "earnings per share diluted", "diluted loss per share"),
    "TOTAL_ASSETS": ("total assets",),
    "TOTAL_EQUITY": ("total equity", "total shareholders equity", "equity attributable to owners", "shareholders funds"),
    "TOTAL_LIABILITIES": ("total liabilities", "total liability"),
    "TOTAL_EQUITY_AND_LIABILITIES": ("total equity and liabilities",),
    "NAVPS": ("net asset value per share", "net assets per share", "nav per share", "net asset per share"),
    "GROSS_PROFIT": ("gross profit",),
    "COST_OF_SALES": ("cost of sales", "cost of goods sold"),
    "CURRENT_LIABILITIES": ("current liabilities", "total current liabilities"),
    "NON_CURRENT_LIABILITIES": ("non-current liabilities", "non current liabilities", "total non-current liabilities"),
    "CURRENT_ASSETS": ("current assets", "total current assets"),
    "NON_CURRENT_ASSETS": ("non-current assets", "non current assets", "total non-current assets"),
    "DPS": ("dividend per share",),
}
