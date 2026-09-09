"""Empirical calibration of machine certainty against independent MANUAL_QA truth.

The extractor's ``overall_certainty`` is a ranking/triage score. It becomes a
calibrated probability-like quantity only after enough independent manual labels
exist. Until then every consumer receives an explicit insufficient-sample status.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

MIN_CALIBRATION_SAMPLES = 100
MIN_POPULATED_BIN_SAMPLES = 10
CALIBRATION_BINS: tuple[tuple[float, float], ...] = (
    (0.0, 0.60),
    (0.60, 0.80),
    (0.80, 0.90),
    (0.90, 0.95),
    (0.95, 1.0000001),
)


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    score: float
    correct: bool


def _observations(results: Iterable[dict[str, Any]]) -> list[CalibrationObservation]:
    observations: list[CalibrationObservation] = []
    for row in results:
        if str(row.get("verification_status") or "") != "MANUAL_QA":
            continue
        if row.get("status") not in {"PASS", "FAIL"}:
            continue
        raw = row.get("overall_certainty")
        if raw in (None, ""):
            continue
        try:
            score = float(str(raw))
        except ValueError:
            continue
        if not 0.0 <= score <= 1.0:
            continue
        observations.append(CalibrationObservation(score, row.get("status") == "PASS"))
    return observations


def calibration_from_results(
    results: Iterable[dict[str, Any]],
    *,
    min_samples: int = MIN_CALIBRATION_SAMPLES,
    min_populated_bin_samples: int = MIN_POPULATED_BIN_SAMPLES,
) -> dict[str, Any]:
    """Return reliability bins, Brier score and expected calibration error.

    ``CALIBRATED`` is deliberately conservative: the independent sample must meet
    the global minimum and every populated reliability bin must have enough labels.
    A sparse/partial benchmark still reports diagnostics, but cannot certify the
    certainty score as calibrated.
    """

    observations = _observations(results)
    bins: list[dict[str, Any]] = []
    weighted_gap = 0.0
    total = len(observations)
    for lower, upper in CALIBRATION_BINS:
        selected = [item for item in observations if lower <= item.score < upper]
        count = len(selected)
        mean_score = sum(item.score for item in selected) / count if count else None
        accuracy = sum(item.correct for item in selected) / count if count else None
        gap = abs(mean_score - accuracy) if mean_score is not None and accuracy is not None else None
        if gap is not None and total:
            weighted_gap += gap * (count / total)
        bins.append(
            {
                "lower": lower,
                "upper": min(upper, 1.0),
                "sample_size": count,
                "mean_certainty": mean_score,
                "observed_accuracy": accuracy,
                "absolute_gap": gap,
            }
        )

    brier = (
        sum((item.score - (1.0 if item.correct else 0.0)) ** 2 for item in observations) / total
        if total
        else None
    )
    populated = [row for row in bins if int(row["sample_size"]) > 0]
    enough_bins = bool(populated) and all(
        int(row["sample_size"]) >= min_populated_bin_samples for row in populated
    )
    calibrated = total >= min_samples and enough_bins
    return {
        "status": "CALIBRATED" if calibrated else "INSUFFICIENT_MANUAL_SAMPLE",
        "sample_size": total,
        "minimum_sample_size": min_samples,
        "minimum_populated_bin_size": min_populated_bin_samples,
        "brier_score": brier,
        "expected_calibration_error": weighted_gap if total else None,
        "bins": bins,
        "interpretation": (
            "Empirical reliability measured only on independent MANUAL_QA checks."
            if calibrated
            else "Certainty remains a heuristic ranking score until the independent manual sample is large enough."
        ),
    }
