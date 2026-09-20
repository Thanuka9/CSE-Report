# BLOCKED — WITH EVIDENCE (coordinator status)

**Plan:** `docs/v2/CSE_V2_FINAL_AGENT_EXECUTION_PLAN.md`  
**Branch:** `v2/extraction-investigation` · **git HEAD:** `c5bbe51` (working tree dirty — local recovery not pushed)  
**Production:** **V1** (unchanged). Floor **8,924** unchanged. **Not READY FOR OFFICIAL DECISION.**

## Verdict

**BLOCKED — WITH EVIDENCE.** Two consecutive meaningful full-829 experiments recovered only **+3** then **+4** TARGET draft-selected vs V2-only. Per plan §6 hard stop: **suspend further local context/alias stacking** and reopen **physical reader integration / selection architecture** for MISSING_CELL + CONCEPT losses.

## Frozen baseline (experiment 0 / post unit+nonreg)

`reports/v1_v2_same_input/baseline_freeze_2026-09-20_plus3/`

| Run | Assisted TARGET | V2 TARGET | Net |
|---|---:|---:|---:|
| Freeze (note/share + table unit) | 2,819 | 2,816 | **+3** |
| Exp 2 ( + unanimous table entity/period) | **2,820** | 2,816 | **+4** |
| 80-file sample (not universe proof) | 323 | 305 | +18 |

Do **not** add +4 to E13 3,854. Floor 8,924 untouched.

## Phase A (done)

`reports/v1_v2_same_input/phase_a_2026-09-20/SOURCE_VALID_GAP_AND_SELECTION_WATERFALL.md`

- ELIGIBLE→selected collapse is largely **selection policy**.
- V1-only soft slots ≈ 6,096 — engine differential, not PDF-proven correct.
- Probe first-loss: ENTITY / MISSING_CELL / CONCEPT dominate.
- Review queue PDF adjudication still pending.

## Phase B (hard-stopped after flat exp 2)

Shipped locally (dirty tree): non-regressive union; note/share guards; table units; unanimous entity/period. Safety cases JAT/HAYLEYS/SIGIRIYA remain correct. **Universe lift is not material.**

## Architecture finding (post hard-stop)

AMANA_BANK probe “MISSING_CELL” is often a **misnomer**: V2 already has the numeric cell (`OPERATING_PROFIT` raw `1,366,289`) but **`entity_scope=None`** because the income-statement headers print no Bank/Company/Group. V1 ledger marks `BANK` — likely issuer/regime fill, **not portable** under source-truth guardrails.

Additionally, V1 `_assign_roles` cleared CURRENT/COMPARATIVE for an entire duration block when any sibling lacked a full date (year-only / Change%). Bridge now re-derives roles **among dated peers only** (`dated_peer_order_bridge`).

**Implication:** a large share of V1-only BANK/COMPANY keys on unlabeled single-entity statements are **not recoverable** without inventing entity. Recoverable volume is in printed multi-entity headers, missing physical cells, and concept/statement ownership — not another unanimous-context patch.

## Gates not met (checklist)

Identical cohort KPIs exist, but **like-for-like V1 parity**, **8,924 gate**, **unseen holdout**, **clean SHA + remote CI**, **lineage/replay pack**, and **OFFICIAL readiness** all fail. V1 remains production.
