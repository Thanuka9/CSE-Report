# Non-regression investigation (post +24 bridge)

**Local report only** — treat context-bridge results as a completed local run. Connected GitHub branch head was still reported as `c5bbe51` when this was written; do not claim remote verification of newer commits.

**Reporting correction:** `2,840` draft-selected **TARGET** facts is not interchangeable with E13 `3,854` total draft-publishable (source + derived under the same pipeline definition). Do **not** announce `3,878` without a same-definition rerun.

Artifacts:
- `eligible_loss_audit.json`
- `draft_selected_delta_audit.json`
- `pending_first_failure_partition.json` (42-filing sample)
- `gap_summary.json`

---

## 1. Eligible −276 rows vs 370 new / 200 lost keys

### Reconcile identity vs rows

From `eligible_loss_audit.json` `counts`:

| View | V2-only | Assisted | Δ |
|---|---:|---:|---:|
| ELIGIBLE **rows** | 9,838 | 9,562 | **−276** |
| Unique ELIGIBLE **hard keys** | 9,209 | 9,380 | **+171** |
| Lost hard keys | — | — | **211** |
| New hard keys | — | — | **382** |

Gap-summary “370 new / 200 lost” is the same phenomenon under a slightly different soft-key definition; hard-key audit sees **382 / 211**. Row Δ (−276) and hard-key Δ (+171) diverge because assisted collapses duplicate eligible rows on the same soft slot (~hundreds of extras removed). **−276 is not 276 unique correct facts destroyed.**

### Fate of lost ELIGIBLE hard keys (211)

| Class (`lost_hard_classes`) | Count | Interpretation |
|---|---:|---|
| `ABSENT_FROM_ASSISTED_LEDGER` | 129 | No matching assisted eligible at that metric/entity/period/cmp(+value identity) — **highest risk of wrong removal**; preserve V2 unless stronger PDF conflict is shown |
| `DURATION_REKEYED_SAME_VALUE` | 47 | Same value retained after duration re-key (typically quarter→cumulative withhold path) — **mostly intended demotion** when headers mark period-ended |
| `SLOT_PRESENT_DIFFERENT_VALUE_OR_DURATION` | 21 | Soft slot remains but value/duration changed or only withheld — mix of conflict cleanup vs over-withhold |
| `VALUE_CHANGED_STILL_ELIGIBLE` | 14 | Soft slot still eligible with a **different** value — verify which value is PDF-correct |

### New hard keys (382) — for context, not celebration

| Class | Count |
|---|---:|
| `WAS_CONFLICTING_NOW_ELIGIBLE` | 231 |
| `TRULY_NEW_SLOT` | 111 |
| `WAS_WITHHELD_NOW_ELIGIBLE` | 18 |
| `DURATION_REKEYED_OR_NEW_CMP` | 16 |
| `NEW_VALUE_ON_EXISTING_SOFT` | 6 |

### Preserve-V2 rule (engineering implication)

Union may demote V2 `duration=3` when bridged duration is unresolved/cumulative. That explains most `DURATION_REKEYED_SAME_VALUE` cases. The **129 absences** and **14 value changes** are where the bridge may drop or swap V2 evidence without proven stronger PDF conflict — **fix non-regression before expanding families.**

---

## 2. Draft-selected +24 — count is real; correctness is not proven

From `draft_selected_delta_audit.json`:

| | |
|---|---:|
| V2 draft-selected TARGET | 2,816 |
| Assisted | 2,840 |
| Net | **+24** |
| Gained keys | 130 |
| Lost keys | 106 |

### Gained (130)

| Class | n | Meaning |
|---|---:|---|
| `RECOVERED_FROM_CONFLICT` | 79 | ACL-like conflict break → selected (mechanism works) |
| `TRULY_NEW_SELECTED` | 44 | No prior V2 selection for that slot — **must PDF-verify** |
| `RECOVERED_FROM_WITHHELD_OTHER` | 4 | |
| `NOW_SELECTED_WAS_ELIGIBLE_UNSELECTED` | 2 | |
| `VALUE_SWAP_FROM_PRIOR_SELECTION` | 1 | John Keells Hotels PBT path |

### Lost (106)

| Class | n | Meaning |
|---|---:|---|
| `DROPPED_OR_UNSELECTED` | 63 | Prior selection gone — **regression risk** |
| `DEMOTED_CUMULATIVE_UNSELECTED` | 32 | Quarter demoted → not selectable (often intended) |
| `STILL_ELIGIBLE_NOT_SELECTED` | 10 | Still eligible; lost unique-by-metric race |
| `VALUE_SWAP_STILL_SELECTED` | 1 | |

### PDF spot-checks (sample of gains)

| Case | Selected value | PDF finding | Verdict |
|---|---|---|---|
| ACL PLASTICS TOP_LINE | 731,203,000 | Quarter revenue 731,203 × Rs'000 | **CORRECT** (mechanism proof) |
| JOHN KEELLS HOTELS PBT | 96,269,000 | “Profit/(loss) before tax” 96,269 | **Likely correct** (swap from −5,501) |
| INSUREME PAT | 19,045,566 | Printed 19,045,566 | **Likely correct** |
| JAT HOLDINGS TOP_LINE | **4** | Note “4” beside Revenue; real revenue ~3.0e9 | **NEWLY WRONG** |
| HAYLEYS TOP_LINE | **6,000** | Note/ref noise vs Revenue 164,620,903 | **NEWLY WRONG** |
| HOTEL SIGIRIYA EPS_BASIC | **17,577,000** | Stated-capital share count, not EPS | **NEWLY WRONG** |

**Adjudication status of +24:** ACL proves the architecture can recover output. Spot checks already show **newly wrong** selections (note-index / share-count pollution). Full CORRECT / WRONG / PENDING adjudication of all 130 gains and 106 losses is still required before treating +24 as a quality win.

---

## 3. Pending verify — next large *evidence-backed* family

Universe pending (`gap_summary`): **201,546** assisted `discovery_only_pending_verify`. Do **not** chase all of them.

42-filing sample (`pending_first_failure_partition.json`): **34,102** bridged V1 candidates; **2,118** target-matched.

### First failed requirement — all cells

| First fail | Count | Share |
|---|---:|---:|
| CONCEPT_UNRESOLVED | 31,893 | ~93% (mostly non-target numeric cells) |
| UNIT_UNRESOLVED | 672 | |
| ADMITTED | 598 | |
| ENTITY_UNRESOLVED | 560 | |
| PERIOD_UNRESOLVED | 347 | |
| DURATION_UNRESOLVED | 26 | |
| COMPARISON_ROLE_UNRESOLVED | 6 | |

### First fail among **target-matched** only (n=2,118)

| First fail | Count |
|---|---:|
| UNIT_UNRESOLVED | 668 |
| ADMITTED | 588 |
| ENTITY_UNRESOLVED | 486 |
| PERIOD_UNRESOLVED | 346 |
| DURATION_UNRESOLVED | 26 |
| COMPARISON_ROLE_UNRESOLVED | 4 |

Among target-matched cells that are **still** `DISCOVERY_ONLY`, the same order holds: **UNIT → ENTITY → PERIOD**, then duration / comparison. Concept mass is almost entirely non-target and must not drive engineering.

---

## Recommended next work (in order)

1. **Make union/selection non-regressive**
   - Keep V2 eligible/selected when bridged evidence is silent or weaker.
   - Demote duration only with explicit header conflict (already partial).
   - Block note-index / share-count concepts from TOP_LINE / EPS selection (JAT / HAYLEYS / SIGIRIYA class).
   - Re-measure the 63 `DROPPED_OR_UNSELECTED` and 129 `ABSENT_FROM_ASSISTED_LEDGER` after the guard.

2. **Adjudicate the +130 / −106 draft delta** into CORRECT / WRONG / PENDING with PDF evidence (all `TRULY_NEW_SELECTED`, all value swaps, sample of conflict recoveries, sample of drops).

3. **Only then** expand the next evidence-backed family on **target-matched** V1-only observations: unit/scale → entity (header-printed only) → period → duration/cmp. Never invent entity for unlabeled single-entity filings.

Success metric: **source-verified net draft-selected TARGET gains with ~0 correct losses** — not candidate count, and not “2840 ≈ 3854”.
