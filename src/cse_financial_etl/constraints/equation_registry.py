"""Conditional equation registry — evidence first, derivation second (§20)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class EquationSpec:
    equation_id: str
    required_concepts: tuple[str, ...]
    compatible_entities: tuple[str, ...]
    mode: str  # identify | resolve | derive
    description: str
    rounding_tolerance: Decimal = Decimal("1")


@dataclass(frozen=True, slots=True)
class EquationResult:
    equation_id: str
    status: str  # PASS | FAIL | UNTESTED | NOT_APPLICABLE
    mode: str
    detail: str
    identified_concept: str | None = None


class EquationRegistry:
    def __init__(self) -> None:
        self._equations: list[EquationSpec] = []

    def register(self, spec: EquationSpec) -> None:
        self._equations.append(spec)

    @property
    def equations(self) -> tuple[EquationSpec, ...]:
        return tuple(self._equations)

    def evaluate(
        self,
        values: dict[str, Decimal | None],
        *,
        entity: str,
        allow_derive: bool = False,
    ) -> list[EquationResult]:
        results: list[EquationResult] = []
        for spec in self._equations:
            if spec.compatible_entities and entity not in spec.compatible_entities:
                results.append(
                    EquationResult(spec.equation_id, "NOT_APPLICABLE", spec.mode, "entity_mismatch")
                )
                continue
            # For derive-capable equations, missing output concepts are allowed when deriving.
            required = spec.required_concepts
            if (
                allow_derive
                and spec.mode in {"resolve", "derive", "identify"}
                and spec.equation_id == "pat_eq_pbt_less_tax"
            ):
                # Keep inputs mandatory; outputs may be absent for Mode C.
                required = ("PBT", "INCOME_TAX")
            if any(values.get(c) is None for c in required):
                results.append(
                    EquationResult(spec.equation_id, "UNTESTED", spec.mode, "missing_operands")
                )
                continue
            checker = _CHECKERS.get(spec.equation_id)
            if checker is None:
                results.append(
                    EquationResult(spec.equation_id, "UNTESTED", spec.mode, "no_checker")
                )
                continue
            results.append(checker(spec, values, allow_derive=allow_derive))
        return results


def _assets_identity(spec: EquationSpec, values: dict[str, Decimal | None], **_: Any) -> EquationResult:
    assets = values["TOTAL_ASSETS"]
    liabilities = values.get("TOTAL_LIABILITIES")
    equity = values.get("TOTAL_EQUITY")
    if assets is None or liabilities is None or equity is None:
        return EquationResult(spec.equation_id, "UNTESTED", spec.mode, "missing")
    if abs(assets - (liabilities + equity)) <= spec.rounding_tolerance:
        return EquationResult(spec.equation_id, "PASS", spec.mode, "assets=L+E")
    return EquationResult(spec.equation_id, "FAIL", spec.mode, "assets!=L+E")


def _pat_bridge(spec: EquationSpec, values: dict[str, Decimal | None], **kwargs: Any) -> EquationResult:
    pbt = values.get("PBT")
    tax = values.get("INCOME_TAX")
    pat = values.get("PAT")
    if pbt is None or tax is None:
        return EquationResult(spec.equation_id, "UNTESTED", spec.mode, "missing")
    # Tax may already be signed negative.
    expected = pbt + tax if tax < 0 else pbt - tax
    if pat is not None and abs(pat - expected) <= spec.rounding_tolerance:
        return EquationResult(
            spec.equation_id,
            "PASS",
            spec.mode,
            "pat_matches_bridge",
            identified_concept="PAT",
        )
    if pat is None and kwargs.get("allow_derive"):
        return EquationResult(
            spec.equation_id,
            "PASS",
            "derive",
            f"derived_pat={expected}",
            identified_concept="PAT",
        )
    if pat is None:
        return EquationResult(
            spec.equation_id,
            "UNTESTED",
            spec.mode,
            "pat_absent_derive_not_permitted",
            identified_concept=None,
        )
    return EquationResult(spec.equation_id, "FAIL", spec.mode, "pat_bridge_mismatch")


_CHECKERS: dict[str, Callable[..., EquationResult]] = {
    "assets_eq_liabilities_plus_equity": _assets_identity,
    "pat_eq_pbt_less_tax": _pat_bridge,
}


def default_registry() -> EquationRegistry:
    registry = EquationRegistry()
    registry.register(
        EquationSpec(
            "assets_eq_liabilities_plus_equity",
            ("TOTAL_ASSETS", "TOTAL_LIABILITIES", "TOTAL_EQUITY"),
            ("COMPANY", "BANK", "GROUP"),
            "identify",
            "Assets = Liabilities + Equity",
            rounding_tolerance=Decimal("2"),
        )
    )
    registry.register(
        EquationSpec(
            "pat_eq_pbt_less_tax",
            ("PBT", "INCOME_TAX", "PAT"),
            ("COMPANY", "BANK", "GROUP"),
            "resolve",
            "PAT = PBT - Tax (signed-aware)",
        )
    )
    return registry
