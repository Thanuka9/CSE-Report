"""Per-dimension uncertainty graph (§34)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DIMENSIONS = (
    "statement",
    "concept",
    "entity",
    "period",
    "duration",
    "column",
    "unit",
    "numeric",
    "accounting",
)


@dataclass
class UncertaintyGraph:
    concept: str
    dimensions: dict[str, str] = field(default_factory=dict)

    def set(self, dimension: str, status: str) -> None:
        if dimension not in DIMENSIONS:
            raise ValueError(dimension)
        self.dimensions[dimension] = status

    def unresolved_dimensions(self) -> list[str]:
        return [
            dim
            for dim, status in self.dimensions.items()
            if status in {"CONFLICT", "UNRESOLVED", "FAIL", "SEARCH_BUDGET_EXHAUSTED"}
        ]

    def as_dict(self) -> dict[str, Any]:
        return {"concept": self.concept, "dimensions": dict(self.dimensions)}


def uncertainty_from_entry(concept: str, *, entry_status: str, reasons: list[str]) -> UncertaintyGraph:
    graph = UncertaintyGraph(concept=concept)
    for dim in DIMENSIONS:
        graph.set(dim, "RESOLVED")
    joined = " ".join(reasons).upper()
    if "ENTITY" in joined or "GROUP" in joined:
        graph.set("entity", "CONFLICT")
    if "DURATION" in joined or "YTD" in joined or "3M" in joined:
        graph.set("duration", "CONFLICT")
    if "PERIOD" in joined:
        graph.set("period", "CONFLICT")
    if "UNIT" in joined:
        graph.set("unit", "CONFLICT")
    if "COMPARATIVE" in joined or "COLUMN" in joined:
        graph.set("column", "CONFLICT")
    if entry_status == "unresolved":
        graph.set("concept", "UNRESOLVED")
    return graph
