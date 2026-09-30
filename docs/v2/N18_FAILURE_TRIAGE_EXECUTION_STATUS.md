# N18 Failure Triage — Execution Status

**Plan:** `docs/v2/N18_FAILURE_TRIAGE_AND_RECOVERY_PLAN.md`  
**Branch:** `v2/extraction-investigation`  
**Frozen N17 gold:** `639454a2`  
**Frozen N18 first score:** `dc146572` (`tests/v2/universe/n18_ai_blind_first_score.json`) — **immutable**  
**Engine / floor:** `v1` / `8924` (unchanged)  
**As of:** 2026-09-19

## Freeze rule

The first N18 score is historical evidence. Do not overwrite it. After triage + engineering, N16/N17/N18 are **regression/DEV evidence only** — not a reusable unseen holdout.

## Completed sequence

1. P0-A/B/C + P1 triage — **DONE** (`tests/v2/universe/n18_failure_summary.json`)
2. E02 full-universe CandidateTrace — **DONE** (`tests/v2/universe/e02_universe_summary.json`)
3. Entity-ownership green light — **YES**
4. Generalized dual-entity column geometry fix — **LANDED** (regression only)
5. Former N18 regression — **DONE** (`n18_regression_after_entity_geometry.json`)

### E02 vs N18 entity comparison

| Signal | N18 confirmed | Universe (E02) |
|---|---:|---:|
| ENTITY_UNRESOLVED | 36 | **24,226** target candidates |
| WRONG_ENTITY | **7** (truth) | not countable without gold |
| GROUP+COMPANY both explicit | — | **2,490** statements |
| GROUP+BANK both explicit | — | **194** statements |
| ROW_NOT_FOUND slots | 26 | **3,792** |

`WRONG_ENTITY` remains N18-confirmed only; universe dual-entity layouts + ENTITY_UNRESOLVED are prevalence evidence.

### Entity fix (generalized)

Root cause: high-arity Group|Company grids collapsed to 2 monetary columns (modal 3), so Company values inherited GROUP labels.

Fix:
- `table_reconstructor._intervals_for_body` — prefer ≥4-value structure over polluted modal
- `column_context._entity_for_position` — ordered left/right half-split for dual banners; nearest-banner only when >2 banners; never invent entity from issuer/expected production entity

Tests: `tests/v2/unit/test_dual_entity_column_geometry.py` + existing LITE/SFCL/column_context.

### Former N18 regression (not unseen)

| Metric | Frozen first | After entity fix |
|---|---:|---:|
| TP | 23 | **29** |
| FN | 68 | 68 |
| critical_wrong | 8 | **1** |
| entity_mismatch | 7 | **0** |
| numeric_correctness | 0.74 | **0.97** |

Remaining critical wrong: **UBC OPERATING_PROFIT** (`WRONG_DURATION` / period) — next P0 family.

## Next

1. UBC duration/Q4 ownership (last known critical wrong)
2. Then ROW_NOT_FOUND (26 N18 / 3,792 universe)
3. E13 full-universe challenger only after promotion decision
4. No new unseen holdout until major P0 families land

Hard stops: no issuer patches; no V2 promotion / floor change; do not claim unseen holdout success on N18 re-runs.
