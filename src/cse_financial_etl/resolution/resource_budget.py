"""CPU / memory budget controls for compiler stages (§51)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResourceBudget:
    """Bounded active work — stop with explicit budget issue, never invent results."""

    max_hypotheses: int = 5000
    max_graph_nodes: int = 2000
    beam_width: int = 5
    max_iterations: int = 200
    max_elapsed_seconds: float = 120.0
    max_ocr_threads: int = 1
    started_at: float = field(default_factory=time.monotonic)
    stop_reason: str | None = None

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def exhausted(self) -> bool:
        if self.elapsed() >= self.max_elapsed_seconds:
            self.stop_reason = "ELAPSED_BUDGET_EXHAUSTED"
            return True
        return False

    def check_hypotheses(self, count: int) -> bool:
        if count > self.max_hypotheses:
            self.stop_reason = "HYPOTHESIS_BUDGET_EXHAUSTED"
            return False
        return not self.exhausted()

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_hypotheses": self.max_hypotheses,
            "max_graph_nodes": self.max_graph_nodes,
            "beam_width": self.beam_width,
            "max_iterations": self.max_iterations,
            "max_elapsed_seconds": self.max_elapsed_seconds,
            "max_ocr_threads": self.max_ocr_threads,
            "elapsed_seconds": self.elapsed(),
            "stop_reason": self.stop_reason,
        }
