# V1 ↔ V2 Extraction Component Matrix

**Status:** R1 LOCKED (draft→audit-merged)  
**Strategy:** `docs/v2/EXTRACTION_RECOVERY_STRATEGY_NO_PATCHES.md`  
**Rule:** Port algorithms, not patches. No rewrite before classification.  
**Production:** remains `engine: v1` / floor `8924`  
**Audit source:** compiler-module capability map (geometry headers, scoped units, continuation bridge vs V2 contracts)

## Capability decisions

| Capability | V1 locus | Current V2 locus | Decision | Rationale |
|---|---|---|---|---|
| Header hierarchy | `compiler/header_tree.py` phrase→column bbox geometry + periodic blocks | `v2/resolution/column_context.py` heading-band/blob + F1 keep-rule | **MERGE** | Keep V2 fail-closed partial-column contract; port V1 phrase geometry / block assignment as H1 |
| Entity ownership | Header block assignment + continuation bridge in `statement_compiler.py` | `EntityScope` + subtitle/banner cues | **MERGE** | V2 enum/fail-closed is right; V1 column-bound entity + evidenced continuation is more accurate |
| Period ownership | YEAR/DAYMONTH/DATE leaf compose per column | `header_calendar_dates` + positional `_period_for_position` | **PORT_V1** | V1 per-column leaf composition avoids non-linear header mis-alignment |
| Duration ownership | `normalize_duration_phrase`, caption guards, `_derive_period_ended_durations` | Duration banners + F3 ≤4-col geometry | **PORT_V1** (+ keep F3 regressions) | V1 duration surface is richer; retain F3 tests when adapting |
| Comparison role | `_assign_roles` from sibling dates (all-or-nothing) | Date-order + lexical CURRENT/COMPARATIVE | **MERGE** | Prefer V1 date-within-block gating; keep V2 lexical only as evidence, not force-fill |
| Unit resolution | `compiler/units.py` ROW→COLUMN→TABLE→PAGE per cell | Statement-level `parse_unit` + resolver scaling | **PORT_V1** | No V2 per-cell scoped `resolve_unit` today — explicit GAP |
| Per-share units | Never inherit table scale; row `(Rs.)` / cents | Registry `PER_SHARE` + limited cues | **PORT_V1** | Need row-scoped declarations, not table thousands |
| Statement discovery | Thin wrapper → `document/region_detector` | `v2/statements/detector.py` heading-band + EPS-note specificity | **KEEP_V2** | Lower false-positive risk; measure recall before any V1 merge |
| Table reconstruction | `document/table_reconstructor.py` → `TableIR` | `v2/statements/table_reconstructor.py` | **MERGE** (R5) | Converge IR; keep V1 header-phrase geometry where V2 is x-gap only |
| Row reconstruction | V1 cell grid / hypotheses | `numeric.split_label_and_values` + ambiguity flags | **KEEP_V2** | Matches audit rules without `TableIR` dependency |
| Concept matching | `generate_concept_hypotheses` + structural boost | `v2/taxonomy/matcher.py` + registry/abstain | **KEEP_V2** | Do not expand aliases to hide structural misses |
| Continuation handling | `document/continuation.py` + `_bridge_evidenced_continuation_context` | Region “continued” markers only | **PORT_V1** | Column-schema inheritance across pages is a GAP in V2 |
| SourceFact model | Limited / mixed | `v2/contracts/facts.py` | **KEEP_V2** | |
| Lineage / SourceRef | bbox/page on cells | `v2/contracts/provenance.py` + `diagnostics/lineage.py` | **KEEP_V2** | |
| CandidateTrace | Absent | `v2/diagnostics/candidate_trace.py` | **KEEP_V2** | R2 substrate |
| Deterministic replay | Limited | `v2/diagnostics/replay.py` | **KEEP_V2** | |
| Holdout / source truth | Limited | holdout + golden diagnostics | **KEEP_V2** | |
| Production selection | `KnownContext`-adjacent forcing risk | `v2/resolution/production_selection.py` | **KEEP_V2** | Never fold query context into source |
| Governance / floors | Conflict strings only | `v2/governance/coverage_floors.py` | **KEEP_V2** | Never lower 8924 |

## Do-not-port V1 patch debt

| Signal | V1 path | Action |
|---|---|---|
| Issuer **NDB** “Period ended” caption special-case | `header_tree.py` | **REJECT** — issuer-specific |
| Caption/table-title silent fill of entity/duration/date when column silent | `header_tree.py` | **REJECT / rewrite** — leave unresolved or require column evidence |
| Geometric tolerance hacks (`+2`, 6px) | `header_tree.py` | Re-derive with tests; do not copy magic constants blindly |
| Fake `table_index` from `round(bbox.y0)` | `statement_compiler.py` | **REJECT** — use stable statement/region ids (V2) |
| Query context `.N` → VOTING / default duration=3 | `known_context.py` | **REJECT** as source fill — conflict detection only |
| Bare currency → scale `1` silent default | `structure_normalizer` / units comments | Prefer UNRESOLVED over silent scale |
| Cover/blob duration fallback risk | V2 `parse_duration_months(cover)` | Treat as same class of debt — tighten during H1 |

## V1 → V2 module map

| V1 | V2 | Status |
|---|---|---|
| Document IR / table geometry | `v2/contracts/document.py`, `v2/document/*` | PARTIAL |
| Table reconstruction | `v2/statements/table_reconstructor.py` | PARALLEL |
| Statement discovery | `v2/statements/detector.py` | MAPPED (KEEP_V2) |
| Header / column context | `v2/resolution/column_context.py` | PARTIAL — not phrase-geometry |
| Units (cell-level scoped) | column `parse_unit` + resolver | **GAP** |
| Continuation column bridge | detector region merge only | **GAP** |
| Known/query context | pipeline args + production_selection | PARTIAL — must stay post-source |
| Facts / lineage / traces / replay / holdout / governance | `v2/contracts`, `v2/diagnostics`, `v2/governance` | V2-only strengths |
| `v2/table/` package | — | MISSING (use `statements/table_reconstructor.py`) |

## V1 module notes (port lens)

| Module | Generalizable core | Unsafe |
|---|---|---|
| `header_tree.py` | Geometric `_assign_blocks`, nearest-parent, year+day/month compose, role derivation, KnownContext **conflict-only** | NDB rule; caption silent fill; magic tolerances |
| `units.py` | Scoped resolve; PER_SHARE isolation; conflict→UNRESOLVED | Silent identical-scope override logging patterns |
| `structure_normalizer.py` | Word-bounded unit/date/duration parsers | Day clamp / SL date-order heuristics without evidence |
| `statement_compiler.py` | Evidenced continuation entity bridge; page unit declarations | bbox-Y table ids; EPS label merge lookbacks if issuer-tied |
| `column_compiler.py` | Thin schema adapter | None beyond header_tree |
| `statement_detector.py` | Entry only | Debt in `document/region_detector` |
| `known_context.py` | Expected vs observed conflict input | Defaults and symbol heuristics as source |
| `canonical_statement.py` | Multi-dimension cell IR ideas | Dual long-lived IR — map into V2 contracts |

## Target H1 shape (R3 — not built)

```text
V1 compile_header geometry (minus patch debt)
  → adapt onto CanonicalStatement columns
  → emit SourceRef evidence
  → ColumnHeaderPath / HeaderGraph
  → bind FactCandidate context
  → bake-off vs H0 (current column_context)
```

Do **not** invent clean-sheet H2 before H1 measurement.

## Seed failure signal (locked-33, not full R2)

From `tests/v2/universe/r2_seed_first_failure_locked33.json` (16,077 candidates):

| first_failure_stage | count |
|---|---:|
| CONCEPT_UNRESOLVED | 13837 (mostly non-target numerics) |
| ENTITY_UNRESOLVED | 707 |
| NONE | 633 |
| PUBLICATION | 495 |
| VALIDATION | 405 |

Resolution UNRESOLVED rates: entity 4241, duration 7061, period 2056, unit 17.

**Implication:** H1 header/entity/duration port first; concept-alias expansion is not the first lever; unit port still required despite low first-failure count (admission order masks it).

## Ranked next transplants

1. **R3** — V1-derived H1 header/entity/period/duration/comparison (MERGE/PORT as above), exclude do-not-port list.  
2. **R4** — Scoped UnitEvidenceResolver (`units.py` → V2 SourceRef).  
3. **R5** — Continuation column bridge + table IR differential.  
4. R2 full-universe CandidateTrace census when traces exist at N14 scale.

## Next

Score H0 vs H1 on DEV + LITE/SFCL regressions + universe resolution rates; promote H1 only if material gain and critical wrong facts do not increase.
