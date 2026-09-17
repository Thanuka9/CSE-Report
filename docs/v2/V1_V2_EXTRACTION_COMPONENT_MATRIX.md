# V1 ↔ V2 Extraction Component Matrix

**Status:** R1 DRAFT — classify before rewrite  
**Strategy:** `docs/v2/EXTRACTION_RECOVERY_STRATEGY_NO_PATCHES.md`  
**Rule:** Port algorithms, not patches. No rewrite before classification.  
**Production:** remains `engine: v1` / floor `8924`

## Capability decisions

| Capability | V1 locus | Current V2 locus | Decision | Rationale |
|---|---|---|---|---|
| Header hierarchy | `compiler/header_tree.py` (`compile_header`, spatial parent/leaf geometry) | `v2/resolution/column_context.py` (banner/subtitle cues; F1 keep-rule) | **PORT_V1 → MERGE** | V1 geometry-aware header paths outperform simplified V2 banners; adapt to `CanonicalStatement` + `SourceRef` as H1 |
| Entity ownership | `header_tree` block assignment by geometry | `column_context._is_entity_bearing_subtitle` + entity patterns | **PORT_V1 → MERGE** | F1 fixed one drop class; V1 parent-phrase geometry is the durable path |
| Period ownership | `header_tree` + `structure_normalizer` date compose | `column_context` date regexes | **PORT_V1 → MERGE** | V1 forbids bare-year→31-Dec defaults and uses printed day/month binding |
| Duration ownership | `header_tree` duration blocks | `column_context` + F3 nearest-banner ≤4-col geometry | **MERGE** | Keep F3 regression wins; port V1 block ownership where V2 still under-resolves (locked-33: duration UNRESOLVED 7061/16077) |
| Comparison role | Derived inside (entity, duration) blocks from dates | Keyword CURRENT/COMPARATIVE + date order heuristics | **PORT_V1 → VALIDATE** | Prefer date-within-block derivation over keywords |
| Unit resolution | `compiler/units.py` ROW→COLUMN→TABLE→PAGE | Column/table cues in `column_context`; concept dimension from registry | **PORT_V1** | V1 scoped evidence hierarchy + conflict→unresolved is stronger; locked-33 first-failure rarely UNIT because admission order hits concept/entity first, but N14 still shows scale/admission gaps |
| Per-share units | `units.py` never inherit table thousands | Registry `PER_SHARE` + limited cues | **PORT_V1** | Explicit per-share scale ownership required for EPS/NAVPS |
| Statement discovery | `compiler/statement_detector.py` → `document/region_detector` | `v2/statements/detector.py` heading-band titles | **BEST-OF / MEASURE** | Compare page recall before choosing; keep V2 explicit-heading discipline |
| Table reconstruction | Document IR `TableIR` path via statement compiler | `v2/statements/table_reconstructor.py` | **BEST-OF / MEASURE** | Structural differential (R5) required |
| Row reconstruction | Structure normalizer + compiler | `table_reconstructor` + `numeric.split_label_and_values` | **BEST-OF / MEASURE** | Same |
| Concept matching | V1 aliases / recovery paths (mixed patch debt) | `v2/taxonomy/matcher.py` + registry | **MEASURE → IMPROVE later** | Do **not** expand aliases to hide structural misses (R6 only after structure stable) |
| Continuation handling | Present in V1 document/compiler path | Incomplete / gate G05 untested | **BEST-OF** | Port only generalized continuation with SourceRef |
| SourceFact model | Limited / mixed with production rows | `v2/contracts/facts.py` | **KEEP_V2** | Stronger separation |
| Lineage / SourceRef | Limited | `v2/contracts/provenance.py` | **KEEP_V2** | |
| CandidateTrace | Absent/limited | `v2/diagnostics/candidate_trace.py` | **KEEP_V2** | Drive R2 census from this |
| Deterministic replay | Limited | `v2/diagnostics/replay.py` + baseline harness | **KEEP_V2** | |
| Holdout / source truth | Limited | `tests/v2/source_truth/*`, N16/N17 | **KEEP_V2** | |
| Production selection | Weaker separation | `v2/resolution/production_selection.py` | **KEEP_V2** | |
| Governance / floors | Limited | coverage baseline + cutover docs | **KEEP_V2** | Never lower 8924 to “pass” V2 |

## V1 module audit (brief)

| Module | What it does | Generalizable core | Unsafe / do-not-port |
|---|---|---|---|
| `compiler/header_tree.py` | Bind numeric columns to spatial header paths; entity/duration blocks; comparison from dates | Geometry parent assignment; conflict detection via `KnownContext` without copying expected values into source | Any future issuer-name branches; midpoint splits (already rejected in comments) |
| `compiler/units.py` | Scoped unit resolve; PER_SHARE isolation; conflict→unresolved | ROW→COLUMN→TABLE→PAGE; evidence-owned declarations | Silent currency/scale defaults (already forbidden — preserve that) |
| `compiler/structure_normalizer.py` | Bounded date/duration/entity/unit text parse | Word-boundary parsers; compose_date rules | Defaulting missing calendar parts |
| `compiler/column_compiler.py` | Wrap header compile into statement columns | Thin adapter — port via header_tree | |
| `compiler/statement_compiler.py` | Assemble compiled statements | Orchestration patterns | Patchy recovery side-paths if any |
| `compiler/statement_detector.py` | Wrapper to region detector | Prefer comparing underlying detectors | |
| `compiler/known_context.py` | Expected metadata for **conflict detection only** | Keep as validator input, never as source fill | Copying known entity/period into extracted facts |
| `compiler/canonical_statement.py` | V1 canonical statement shape | Map fields into V2 contracts | Dual parallel models long-term |

## V2 module audit (brief)

| Module | Role vs matrix |
|---|---|
| `v2/resolution/column_context.py` | Current H0 header/context engine — baseline for H0 vs H1 bake-off |
| `v2/resolution/resolver.py` | Admission order + SourceFact build — keep; feed richer column context |
| `v2/statements/*` | Discovery + table/row rebuild — measure vs V1 before port |
| `v2/taxonomy/*` | Concept layer — freeze expansions until structure ports land |
| `v2/diagnostics/candidate_trace.py` | First-failure census substrate |

## Target H1 shape (R3 preview — not built yet)

```text
V1 compile_header / header geometry
  → adapt onto CanonicalStatement columns
  → emit SourceRef evidence
  → produce ColumnHeaderPath / HeaderGraph
  → bind into FactCandidate context
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

Resolution UNRESOLVED rates (all candidates): entity 4241, duration 7061, period 2056, unit 17.

**Engineering implication:** header/entity/duration ownership (H1 port) is the next structural transplant; concept-alias expansion is **not** the first lever.

## Next

1. R2 full-universe first-failure census (N14 + CandidateTrace waterfall).  
2. R3 implement V1-derived H1 behind a bake-off flag.  
3. Score H0 vs H1 on DEV + regressions + universe resolution rates — promote only if material gain without critical wrong facts.
