# CSE V2 Extraction Recovery Strategy
## Rebuild the Core Without Repeating the V1 Patch Cycle

**Repository:** `Thanuka9/CSE-Report`  
**Branch:** `v2/extraction-investigation`  
**Current production engine:** `v1`  
**Current V2 role:** challenger only  
**Current V2 universe signal:** ~3,748 draft-publishable facts vs historical alarm ~8,924  
**Purpose:** define the correct engineering direction for V2 so it becomes a durable replacement for V1 rather than another patch-driven extractor.

---

# 1. Why V2 Exists

V1 proved the CSE quarterly-report extraction problem is solvable.

Its limitation became:

```text
new layout
→ patch
→ new issuer variation
→ another patch
→ hidden interaction
→ more special handling
→ maintenance ceiling
```

The objective of V2 is **not** to discard V1.

The target is:

```text
V1 extraction capability
+
V2 architecture
+
generalized rules
-
V1 patch debt
```

That is the engineering direction from this point forward.

---

# 2. What Must Stop

Do not continue V2 as a clean-sheet extractor.

Do not solve the project through:

```text
issuer fails
→ inspect issuer
→ add exception
→ rerun issuer
→ repeat
```

Do not add:

- issuer-name conditions
- file-specific page numbers
- hard-coded column positions
- hard-coded expected values
- template-specific one-off branches
- V1-output-derived source truth
- query-target metadata copied into source context
- silent fallbacks that cannot be traced
- architecture layers with no universe-scale evidence

A real-PDF failure can reveal a generalized defect, but the fix must be structural.

---

# 3. What Must Be Preserved From V2

Keep:

```text
CanonicalDocument
CanonicalStatement
FactCandidate
SourceFact
DerivedFact
CandidateTrace
SourceRef / provenance
source-vs-derived separation
validation contracts
production selection
publication separation
deterministic replay
source-truth schema
holdout methodology
coverage governance
OCR packaging
workbook routing
```

These are not the primary reason current coverage is weak.

Do not start V3.

---

# 4. What Must Be Recovered From V1

V1 must be treated as an engineering asset, not only a comparator.

V1 is not source truth.

But proven V1 algorithms should be reused.

## 4.1 Header / column context

Reuse and adapt V1 logic for:

- spatial header paths
- Group / Company ownership
- duration blocks
- dates tied to specific columns
- current/comparative derivation
- parent/leaf header geometry
- evidence-backed column context
- conflict detection

This should become the basis for V2:

```text
HeaderGraph
ColumnHeaderPath
```

Do not build a new H2 from zero before evaluating the V1 header compiler.

## 4.2 Unit resolution

Reuse V1's scoped unit hierarchy:

```text
ROW
→ COLUMN
→ TABLE
→ PAGE
```

Preserve:

- currency ownership
- scale ownership
- explicit vs inferred scale
- per-share treatment
- cents handling
- count dimensions
- conflict resolution
- evidence IDs

## 4.3 Table / statement structure

Compare V1 and V2 directly for:

- statement page discovery
- statement boundaries
- table detection
- row reconstruction
- numeric cell geometry
- merged headers
- continuation pages
- caption/title ownership
- multi-row headers
- note columns
- percentage/change columns

Where V1 wins, port the technique.
Where V2 wins, keep V2.

---

# 5. Target Architecture

```text
PDF
↓
V2 CanonicalDocument
↓
Page / statement discovery
↓
Table and row reconstruction
↓
V1-derived generalized structural intelligence
    ├─ header geometry
    ├─ column ownership
    ├─ date resolution
    ├─ duration resolution
    ├─ entity resolution
    ├─ scoped unit resolution
    └─ continuation/layout handling
↓
V2 HeaderGraph / ColumnHeaderPath
↓
V2 FactCandidate
↓
V2 SourceFact
↓
Validation
↓
DerivedFact
↓
Production Selection
↓
Publication
↓
Workbook
```

Principle:

> **Port algorithms, not patches.**

---

# 6. Component Migration Matrix

Maintain a formal matrix:

| Capability | V1 | Current V2 | Action |
|---|---|---|---|
| Header hierarchy | Mature | weaker/simplified | PORT + ADAPT |
| Entity ownership | Geometry-aware | partial/banner-driven | PORT + MERGE |
| Period ownership | Mature | partial | PORT + MERGE |
| Duration ownership | Mature | improving | PORT + VALIDATE |
| Comparison role | Source-structure driven | partial | PORT + VALIDATE |
| Unit resolution | Scoped/evidence owned | simplified | PORT |
| Per-share units | Mature | partial | PORT |
| Statement discovery | Compare | Compare | BEST-OF |
| Table reconstruction | Compare | Compare | BEST-OF |
| Row reconstruction | Compare | Compare | BEST-OF |
| Concept matching | Mixed | Mixed | MEASURE + IMPROVE |
| Continuation handling | Compare | incomplete | BEST-OF |
| SourceFact model | limited | strong | KEEP V2 |
| Lineage | limited | strong | KEEP V2 |
| CandidateTrace | absent/limited | strong | KEEP V2 |
| Deterministic replay | limited | strong | KEEP V2 |
| Holdout/source truth | limited | strong | KEEP V2 |
| Production selection | weaker separation | strong | KEEP V2 |
| Governance | limited | strong | KEEP V2 |

Each component ends as one of:

```text
KEEP_V2
PORT_V1
MERGE
REWRITE
DEPRECATE
```

No rewrite before classification.

---

# 7. Universe-Wide Failure Census

Before more isolated fixes, build a universe-level first-failure census.

For every target candidate:

```text
PDF available?
↓
page discovered?
↓
statement detected?
↓
table reconstructed?
↓
row reconstructed?
↓
numeric cell parsed?
↓
concept matched?
↓
entity resolved?
↓
period resolved?
↓
duration resolved?
↓
comparison resolved?
↓
unit resolved?
↓
SourceFact created?
↓
validation passed?
↓
production selected?
↓
published?
```

Required dimensions:

```text
failure_stage
count
metric
issuer_type
statement_type
layout_family
native_vs_ocr
period
```

The top 2–4 failure families should drive engineering.

This replaces patch-by-patch prioritization.

---

# 8. V1 vs V2 Structural Differential

Compare structural extraction on the same filing:

```text
V1 pages/statements/tables/rows/cells/context
vs
V2 pages/statements/tables/rows/cells/context
```

Measure:

```text
statement pages found
tables found
rows found
target row labels found
numeric cells found
entity-resolved columns
period-resolved columns
duration-resolved columns
unit-resolved columns
SourceFacts created
```

Use V1 only to find capability gaps.

If V1 recovers structure that V2 misses:

```text
inspect algorithm
→ generalize
→ port into V2 contracts
→ validate against source truth
```

---

# 9. Recovery Phases

## R0 — Freeze current direction

- Keep production on V1.
- Freeze current V2 evidence.
- Do not lower coverage gates.
- Stop issuer-specific patches.

## R1 — V1 capability audit

Audit first:

```text
compiler/header_tree.py
compiler/units.py
compiler/structure_normalizer.py
document/document_ir.py
statement/table discovery
row reconstruction
continuation handling
concept resolution
```

For each module document:

```text
what it does
why it works
known patch debt
generalizable logic
unsafe assumptions
V2 equivalent
migration decision
```

Deliverable:

```text
V1_V2_EXTRACTION_COMPONENT_MATRIX.md
```

## R2 — Universe first-failure census

Deliver:

```text
universe_first_failure_summary.csv
universe_first_failure_by_metric.csv
universe_first_failure_by_sector.csv
universe_first_failure_by_layout.csv
universe_failure_waterfall.json
```

## R3 — Header-context recovery

Build H1 as:

```text
V1 header compiler
→ adapted to CanonicalStatement
→ emits V2 SourceRef evidence
→ produces V2 ColumnHeaderPath
```

Compare:

```text
H0 = current V2
H1 = V1-derived
```

Score on DEV, real-PDF regressions, source truth, and universe resolution rates.

If H1 materially beats H0 without critical wrong facts, promote H1.

## R4 — Scoped UnitEvidenceResolver

Port V1 unit resolution into V2.

Requirements:

- row/column/table/page evidence hierarchy
- currency and scale independently resolved
- per-share never inherits statement thousands
- cents/share normalized correctly
- conflicts unresolved rather than guessed
- evidence retained in SourceRef

Then rerun the universe.

## R5 — Statement/table parity

Compare V1/V2 for:

```text
page discovery
statement segmentation
table detection
header extraction
row reconstruction
continuations
numeric-cell extraction
```

Port only generalized winning techniques.

## R6 — Concept normalization

Only after structure is stable.

Improve source-truth-backed:

- aliases
- bank/finance/insurance top-line concepts
- operating-profit variants
- liabilities
- per-share labels

Do not fix structural misses by expanding aliases.

## R7 — Universe rerun after every major transplant

After each change:

```text
full challenger
→ compare previous/current
→ inspect new facts
→ inspect lost facts
→ source-check samples
```

Track:

```text
draft_publishable
SourceFacts
entity resolved
period resolved
duration resolved
unit resolved
critical wrong facts
new facts
lost facts
```

---

# 10. Hard Milestones

## M1 — Header recovery

Current:

```text
3,748 draft-publishable
```

The header transplant must produce a material improvement.

If it does not, stop and investigate.

## M2 — Unit recovery

Expected:

```text
fewer UNIT_NOT_RESOLVED
better monetary fact admission
better EPS/NAVPS correctness
fewer unsafe scaling failures
```

## M3 — V1 parity

Before certification, V2 should return to approximately V1-level coverage.

Engineering target:

```text
~8,500–9,200 usable/publishable facts
```

This is a target range, not a guarantee.

V2 is not successful at 4k–6k simply because it is cleaner.

## M4 — V2 improvement over V1

After parity:

```text
coverage modestly above V1
unseen recall >=97%
critical wrong facts = 0 on institutional gold
full lineage
generalized rules
far fewer issuer-specific exceptions
```

A mature outcome could plausibly be around:

```text
~9,000–9,700+ usable/publishable facts
```

subject to actual source availability.

---

# 11. Success Definition

V2 succeeds when it has:

```text
V1-level or better coverage
+
lower wrong-context risk
+
zero critical wrong facts on gold
+
high unseen recall
+
full lineage
+
generalized extraction rules
+
deterministic behavior
+
low issuer-specific patch count
```

Primary KPI:

> **How many valid source facts can V2 recover correctly on unseen CSE filings without issuer-specific intervention?**

---

# 12. Parallel Validation Track

Continue in parallel:

```text
N17 blind adjudication
→ N18 unseen holdout scoring
```

But validation must not pause extraction recovery.

If N18 passes while universe coverage remains weak, V2 is still not production-ready.

If universe coverage improves but N18 finds critical wrong facts, V2 is still not production-ready.

Both correctness and recall must pass.

---

# 13. Certification Sequence After Recovery

Only after parity and healthy universe behavior:

```text
clean committed baseline
↓
CI green
↓
new unseen holdout pass
↓
full-universe challenger healthy
↓
material gates resolved
↓
exact Sept-10 replay if artifacts available
↓
SOURCE_VALIDATED_BASELINE
↓
Extraction Certification Report
↓
OFFICIAL review
↓
controlled V2 cutover
```

---

# 14. Production Cutover

Use:

```text
V1 = current production
V2 = shadow challenger
```

Run identical inputs through both.

Use disagreement only to locate review cases; source PDFs remain truth.

After certification:

```text
V2 becomes default
V1 remains rollback
```

Keep rollback for an agreed observation window before retiring V1.

---

# 15. Rules for Reusing V1

Port a V1 technique only if:

```text
generalizable
not issuer-specific
does not inject query context
retains evidence
deterministic
passes source-truth validation
```

Convert:

```text
V1 heuristic
```

into:

```text
generalized V2 rule
+
SourceRef
+
CandidateTrace visibility
+
regression test
+
universe measurement
```

---

# 16. Do Not Port V1 Patch Debt

Reject V1 logic that depends on:

- issuer-specific names
- exact page numbers
- one-issuer row order
- hidden default dates
- expected entity copied into source
- FY−9M Q4 inference
- silent unit assumptions
- final-value overwrite logic
- untraceable fallback chains

If it cannot be generalized, replace it.

---

# 17. Engineering Scoreboard

After every major run:

| KPI | Previous | Current | Delta |
|---|---:|---:|---:|
| PDFs attempted | | | |
| PDFs successfully parsed | | | |
| SourceFacts | | | |
| Draft-publishable | | | |
| Entity resolved | | | |
| Period resolved | | | |
| Duration resolved | | | |
| Unit resolved | | | |
| Critical wrong | | | |
| Holdout recall | | | |
| Issuer-specific rules | | | |

Do not use ticket count, documentation count, or test count as proof of extraction improvement.

---

# 18. Immediate Execution Order

```text
R0  Freeze current V2 direction/results.
R1  Build V1↔V2 component capability matrix.
R2  Build universe-wide first-failure census.
R3  Rank top 2–4 failure families.
R4  Port V1 header compiler into V2-compatible H1.
R5  Run H0 vs H1 source-truth + universe comparison.
R6  Promote the better header engine.
R7  Port V1 scoped unit resolver into V2.
R8  Rerun universe and measure delta.
R9  Compare V1/V2 statement + table reconstruction.
R10 Port generalized winning structural techniques.
R11 Rerun universe.
R12 Fix concept/alias issues only after structure is stable.
R13 Continue until V1 coverage parity is reached.
R14 Run new unseen holdout.
R15 Resolve remaining material defects.
R16 Establish source-validated baseline.
R17 Complete frozen replay / governed disposition.
R18 Certification.
R19 OFFICIAL review.
R20 Controlled V2 cutover with V1 rollback.
```

---

# 19. Stop Conditions

Pause and reassess if:

```text
major transplant adds little/no correct universe coverage
critical wrong facts increase
source-truth accuracy decreases
fix requires issuer-specific conditions
same failure family keeps returning under different patches
```

A change that only improves one known PDF is not enough.

---

# 20. Expected Outcome

The aim is not an exaggerated raw-count increase.

Expected mature V2:

```text
coverage roughly V1 or modestly higher
~9k+ valid usable facts depending on source availability
unseen recall >=97%
critical wrong facts = 0 on institutional gold
full provenance
deterministic reruns
far fewer issuer-specific patches
faster debugging
lower maintenance cost
better adaptation to new CSE layouts
```

The primary improvement over V1 is:

> **generalization, auditability, correctness, and maintainability without sacrificing V1-level recall.**

---

# 21. Final Direction

Do not build another extractor from scratch.

Do not return to V1 patching.

Build the intended V2:

```text
V1's proven extraction intelligence
+
V2's contracts, provenance, validation, testing, and governance
+
universe-wide measurement
-
issuer-specific patch debt
```

That is the shortest and safest path to production.
