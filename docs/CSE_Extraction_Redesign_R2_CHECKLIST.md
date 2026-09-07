# CSE Extraction Redesign R2 — Completion Checklist

Status after compiler publish cutover. External-only remainders are marked EXTERNAL.

## Architecture / publish path
- [x] Statement-compiler publish path (`A/B/C → arbiter → query → gates → publisher`)
- [x] Layout extractor assists discovery only (ledger seed); not silent sole publisher
- [x] Explicit bounded layout fallback with issue codes (`LAYOUT_FALLBACK_*`, `COMPILER_DISABLED`)
- [x] Never blank→0; never A−E liabilities; exact 3M flow; no live prices as quarter-end
- [x] No LLM on publish (regex + RapidFuzz)

## §45 modules (in-repo packages)
- [x] ingestion/ document/ compiler/ accounting/ constraints/ tunnels/
- [x] resolution/ recovery/ facts/ validation/ publication gates
- [x] `facts/publisher.py` publish conversion
- [x] Resource budget (`resolution/resource_budget.py`)
- [x] Stage cache + atomic write (`storage/stage_cache.py`)

## §47 tests
- [x] Redesign unit suite (`tests/unit/redesign`)
- [x] Compiler wiring / no silent layout (`tests/regression/redesign`)
- [x] Universe failure pack + structure benchmark + golden integration green
- [x] No-overpublication gates covered

## §48–54 offline DoD
- [x] Separate redesign metrics tracker (`reporting/redesign_metrics.py`)
- [x] Offline eval harness (`validation/eval_harness.py`) — ran on local golden lake
- [x] Production logging contract (`build_extraction_report` §50)
- [x] Review packets + Accuracy_Quality view builders (`reporting/review_views.py`)
- [x] Cache key / atomic promote helpers (§52)
- [x] Resource budget controls (§51)
- [x] No production self-learning (§53) — unchanged policy

## EXTERNAL remainders (cannot complete in-repo without humans/bank process)
- [ ] §49 independent 100-issuer human adjudication of unique published source facts
- [ ] §54 authenticated reviewer identity binding via bank-managed operating workflow
- [ ] Full-universe production release sign-off against frozen inputs at bank scale

## Offline eval snapshot (local)
- cases: 100 (golden fixture lake)
- compiler_publish_cases: 100
- silent_layout_publish_cases: 0
- explicit_fallback_facts: 0
- numeric_pass/fail: 907 / 8 (failures confined to PIPELINE_SEEDED stratum; MANUAL_QA 34/34)
