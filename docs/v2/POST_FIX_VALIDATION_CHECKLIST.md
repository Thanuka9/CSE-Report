# CSE V2 Extraction Investigation — Post-Fix Validation Checklist

**Repository:** `Thanuka9/CSE-Report`  
**Target branch:** `v2/extraction-investigation`

## Status on this branch

Items 1–4 and 9 are investigation infrastructure and are implemented. Canonical
outputs are written under `outputs/v2_extraction_baseline` and
`outputs/v2_extraction_experiments` from one freeze identity, including run-level
`candidate_trace.parquet`, `source_facts.parquet/jsonl`,
`derived_facts.parquet/jsonl`, `production_selection.parquet`, and
`issue_ledger.parquet`. CandidateTrace rows include `candidate_id` and
`source_fact_id`. Items 5–8 and 10
stay blocked until T10 source truth exists. Do not start T10 yet. Do not promote
V2. Do not lower `min_draft_publishable = 8924`.

## 1. Run a fresh full-pipeline A/B baseline

For A and B independently:

```text
read_document()
→ native/OCR routing
→ statement detection
→ table reconstruction
→ context resolution
→ candidates
→ SourceFacts
→ validation
→ DerivedFacts
→ production selection
```

Require exact equality of governed outputs.

## 2. Produce canonical outputs

```text
run_manifest.json
source_manifest.json
candidate_trace.parquet
source_facts.parquet/jsonl
derived_facts.parquet/jsonl
production_selection.parquet
issue_ledger.parquet
issue_summary.csv
experiment_summary.json
extraction_report.md
```

Every output must contain:

```text
run_id
actual_code_sha
investigation_base_sha
source_snapshot_id
runtime identity
```

## 3. Verify source/selection separation

For multi-entity filings:

```text
all proven source entities must exist in SourceFacts
```

Then separately verify:

```text
production selector returns only requested entity
```

## 4. Verify CandidateTrace fidelity

For every pipeline candidate:

```text
exactly one trace row
```

Require exact match on:

```text
candidate ID
regime
concept candidates
entity
period
duration
comparison
unit
reason codes
SourceFact linkage
actual production-selection result
```

## 5. Start T10 blind adjudication only after infrastructure passes

Reviewers must not see:

```text
V1 output
V2 output
current gate decision
```

Truth record must capture:

```text
metric
raw label
raw value
normalized value
entity
period
duration
comparison role
currency
scale
unit dimension
page
bbox
evidence level
source presence
```

Allowed source-presence states:

```text
REPORTED
NOT_REPORTED
AMBIGUOUS
```

## 6. Gate tests after truth exists

Test:

```text
G01 entity-evidence variants
G02 cascade variants
G03 exact-quarter upstream-vs-gate
G04 OTHER-page discovery
G05 continuation
G06 source conflict ownership
G07 collapsed-row reconstruction
G08 duplicate metric ranking
G09 EPS entity inference
```

For every gate calculate:

```text
TP
FP
FN
precision
recall
critical wrong facts
correct facts recovered
incorrect facts admitted
```

Decision must be:

```text
KEEP
NARROW
REPLACE
REMOVE
```

## 7. Structural bake-offs

### Header

```text
H0 current V2
H1 V1 header engine
H2 new V2 HeaderGraph
```

Score:

```text
entity
period
duration
comparison
unit ownership
column-path correctness
```

### Unit

```text
U0 current V2
U1 V1 scoped resolver
U2 new V2 UnitEvidenceResolver
```

Score:

```text
currency
scale
dimension
normalization
conflict handling
```

### Page routing

```text
P0 document-level
P1 page-level OCR routing
P2 hybrid page merge
```

Score:

```text
target recovery
false recovery
lineage quality
```

## 8. Root-cause repair loop

For each source-confirmed defect:

```text
root cause
→ real-PDF failing regression
→ generalized fix
→ DEV truth scoring
→ frozen regression
→ deterministic rerun
```

Never accept a change because raw fact count rises.

Accept only when:

```text
precision does not materially degrade
critical wrong facts remain zero
targeted recall improves
lineage remains complete
```

## 9. Protect the final holdout

Use:

```text
existing 33 = DEV/regression
new unseen 10–15 = HOLDOUT
```

Do not inspect holdout during rule development.

## 10. Extraction completion gate

Do not resume V2 cutover until:

```text
critical wrong source facts = 0
numeric accuracy >= 99.5%
entity accuracy >= 99.8%
period accuracy >= 99.8%
duration accuracy >= 99.8%
unit/scale accuracy >= 99.8%
source-reported target-fact recall >= 97%
```

Also require:

```text
all material gates experimentally decided
no material UNKNOWN root-cause cluster
full-pipeline deterministic A/B
whole-PDF discovery tested
mixed native/OCR tested
new holdout passed
```

Only then proceed to frozen-universe certification and production cutover.
