"""Unit typing with explicit evidence ownership (audit finding 4).

Resolution order is decided per metric *dimension* before any normalization:

* ``MONETARY`` cells use the most specific applicable scope
  (row unit-line → column header → table caption/title → page footer/header).
* ``PER_SHARE`` cells never inherit a table scale: their scale comes from the
  row itself (``(Rs.)`` → 1, ``cents`` → 0.01) or the per-share dimension rule
  (whole currency units); currency still comes from the nearest scope.
* ``COUNT`` cells use row-level evidence only.

Conflicting declarations within the same scope leave the cell unresolved.
Missing currency leaves the cell unresolved. Nothing is defaulted.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from cse_financial_etl.compiler.structure_normalizer import ParsedUnit, parse_unit_text

MONETARY = "MONETARY"
PER_SHARE = "PER_SHARE"
COUNT = "COUNT"
PERCENT = "PERCENT"

SCOPE_ROW = "ROW"
SCOPE_COLUMN = "COLUMN"
SCOPE_TABLE = "TABLE"
SCOPE_PAGE = "PAGE"
_SCOPE_ORDER = (SCOPE_ROW, SCOPE_COLUMN, SCOPE_TABLE, SCOPE_PAGE)

_PER_SHARE_CONCEPTS = {"EPS_BASIC", "EPS_DILUTED", "NAVPS", "DPS", "DIVIDEND_PER_SHARE"}
_COUNT_CONCEPTS = {"WEIGHTED_AVG_SHARES", "ORDINARY_SHARES", "NUMBER_OF_SHARES"}
_LABEL_UNIT_RE = re.compile(r"\(([^()]{1,40})\)")
_TRAILING_UNIT_RE = re.compile(
    r"(?:\s|^)(rs\.?|lkr|usd|cents?|'000|rs\.?\s*'000|rs\.?\s*mn)\.?\s*$", re.I
)


def concept_dimension(concept: str | None) -> str:
    if concept in _PER_SHARE_CONCEPTS:
        return PER_SHARE
    if concept in _COUNT_CONCEPTS:
        return COUNT
    return MONETARY


def label_dimension_hint(label: str) -> str | None:
    lower = label.lower()
    if re.search(r"\bper\s+(?:ordinary\s+)?share\b|\beps\b|\bnavps\b", lower):
        return PER_SHARE
    if re.search(r"\bnumber\s+of\s+(?:ordinary\s+)?shares\b|\bweighted\s+average\s+(?:number\s+of\s+)?shares\b", lower):
        return COUNT
    return None


@dataclass(frozen=True, slots=True)
class UnitDeclaration:
    """A unit statement with the region that declared it."""

    scope: str
    owner: str
    text: str
    currency: str | None
    scale: Decimal | None
    scale_explicit: bool
    per_share: bool = False
    percent: bool = False
    page: int | None = None

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        scope: str,
        owner: str,
        page: int | None = None,
    ) -> UnitDeclaration | None:
        parsed: ParsedUnit = parse_unit_text(text)
        if parsed.is_empty:
            return None
        return cls(
            scope=scope,
            owner=owner,
            text=text.strip(),
            currency=parsed.currency,
            scale=parsed.scale,
            scale_explicit=parsed.scale_explicit,
            per_share=parsed.per_share,
            percent=parsed.percent,
            page=page,
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scale"] = str(self.scale) if self.scale is not None else None
        return data


@dataclass(frozen=True, slots=True)
class UnitResolution:
    dimension: str
    status: str  # RESOLVED | UNRESOLVED
    currency: str | None
    scale: Decimal | None
    currency_owner: str | None
    scale_owner: str | None
    reasons: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def resolved(self) -> bool:
        return self.status == "RESOLVED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "status": self.status,
            "currency": self.currency,
            "scale": str(self.scale) if self.scale is not None else None,
            "currency_owner": self.currency_owner,
            "scale_owner": self.scale_owner,
            "reasons": list(self.reasons),
            "evidence_ids": list(self.evidence_ids),
        }


def row_unit_declarations(label: str, *, owner: str, page: int | None) -> list[UnitDeclaration]:
    """Units declared on the row label itself (``Basic earnings per share (Rs.)``)."""

    found: list[UnitDeclaration] = []
    for match in _LABEL_UNIT_RE.finditer(label):
        inner = match.group(1)
        if re.search(r"\d{3}", inner) and not re.search(r"'000|000s", inner):
            continue  # "(Note 3)" or numeric parentheses are not units
        decl = UnitDeclaration.from_text(inner, scope=SCOPE_ROW, owner=owner, page=page)
        if decl is not None and (decl.currency or decl.scale_explicit or decl.per_share):
            found.append(decl)
    if not found:
        tail = _TRAILING_UNIT_RE.search(label)
        if tail:
            decl = UnitDeclaration.from_text(tail.group(1), scope=SCOPE_ROW, owner=owner, page=page)
            if decl is not None:
                found.append(decl)
    return found


def resolve_unit(
    dimension: str,
    *,
    row: list[UnitDeclaration],
    column: list[UnitDeclaration],
    table: list[UnitDeclaration],
    page: list[UnitDeclaration],
) -> UnitResolution:
    """Resolve currency and scale independently for one cell / dimension."""

    scoped = {
        SCOPE_ROW: [d for d in row if not d.percent or d.currency],
        SCOPE_COLUMN: [d for d in column if not d.percent or d.currency],
        SCOPE_TABLE: [d for d in table if not d.percent or d.currency],
        SCOPE_PAGE: [d for d in page if not d.percent or d.currency],
    }
    reasons: list[str] = []
    evidence: list[str] = []

    currency, currency_owner, cur_conflict = _pick(scoped, attr="currency")
    if cur_conflict:
        reasons.append(f"CURRENCY_CONFLICT:{cur_conflict}")
    if currency is None:
        reasons.append("CURRENCY_MISSING")

    if dimension == PERCENT:
        return UnitResolution(dimension, "RESOLVED", None, Decimal("1"), None, "percent_dimension_rule")

    if dimension == PER_SHARE:
        row_scales = [d for d in scoped[SCOPE_ROW] if d.scale is not None]
        scale, scale_owner, conflict = _pick({SCOPE_ROW: row_scales}, attr="scale")
        if conflict:
            reasons.append(f"SCALE_CONFLICT:{conflict}")
        if scale is None:
            # Per-share amounts are printed in whole currency units unless the row says cents.
            scale = Decimal("1")
            scale_owner = "per_share_dimension_rule"
        if any(d.scale_explicit and d.scale >= Decimal("1000") for d in row_scales):
            # "(Rs. '000)" on a per-share row is not a plausible per-share scale.
            reasons.append("PER_SHARE_ROW_SCALE_IMPLAUSIBLE")
    elif dimension == COUNT:
        row_scales = [d for d in scoped[SCOPE_ROW] if d.scale_explicit]
        scale, scale_owner, conflict = _pick({SCOPE_ROW: row_scales}, attr="scale")
        if conflict:
            reasons.append(f"SCALE_CONFLICT:{conflict}")
        if scale is None:
            reasons.append("COUNT_SCALE_MISSING")
        currency, currency_owner = None, None
        reasons = [r for r in reasons if not r.startswith("CURRENCY")]
    else:
        explicit = {
            scope: [d for d in decls if d.scale_explicit] for scope, decls in scoped.items()
        }
        scale, scale_owner, conflict = _pick(explicit, attr="scale")
        if conflict:
            reasons.append(f"SCALE_CONFLICT:{conflict}")
        if scale is None:
            bare = {
                scope: [d for d in decls if d.scale is not None and d.currency] for scope, decls in scoped.items()
            }
            scale, scale_owner, conflict = _pick(bare, attr="scale")
            if conflict:
                reasons.append(f"SCALE_CONFLICT:{conflict}")
            if scale is not None:
                reasons.append("BARE_CURRENCY_IMPLIES_WHOLE_UNITS")
        if scale is None:
            reasons.append("SCALE_MISSING")
        else:
            # Same-dimension explicit scale at a more specific scope overrides a broader
            # one silently only when identical; otherwise record the override.
            for scope, decls in explicit.items():
                for decl in decls:
                    if decl.scale != scale:
                        reasons.append(f"SCALE_SCOPE_OVERRIDE:{scope}:{decl.scale}")
                        break

    for decls in scoped.values():
        evidence.extend(d.owner for d in decls)
    blocking = [
        r
        for r in reasons
        if r.startswith(("CURRENCY_CONFLICT", "SCALE_CONFLICT", "SCALE_MISSING", "COUNT_SCALE_MISSING", "PER_SHARE_ROW_SCALE_IMPLAUSIBLE"))
        or (r == "CURRENCY_MISSING" and dimension != COUNT)
    ]
    status = "UNRESOLVED" if blocking else "RESOLVED"
    return UnitResolution(
        dimension=dimension,
        status=status,
        currency=currency,
        scale=scale if status == "RESOLVED" else None,
        currency_owner=currency_owner,
        scale_owner=scale_owner,
        reasons=tuple(reasons),
        evidence_ids=tuple(dict.fromkeys(evidence)),
    )


def _pick(
    scoped: dict[str, list[UnitDeclaration]], *, attr: str
) -> tuple[Any, str | None, str | None]:
    """Most specific scope wins; conflicting values inside one scope → conflict."""

    for scope in _SCOPE_ORDER:
        decls = [d for d in scoped.get(scope, []) if getattr(d, attr) is not None]
        if not decls:
            continue
        values = {getattr(d, attr) for d in decls}
        if len(values) > 1:
            return None, None, f"{scope}:" + "|".join(sorted(str(v) for v in values))
        return getattr(decls[0], attr), decls[0].owner, None
    return None, None, None
