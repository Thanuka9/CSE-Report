# CSE V2 Extraction Investigation — Pre-T10 Fixes

**Repository:** `Thanuka9/CSE-Report`  
**Branch:** `v2/extraction-investigation`  
**Audited head:** `e92689dabc400e3609e64a9d50512e99d9374dec`

Infrastructure on this branch: source extraction is separate from production
selection; CandidateTrace uses in-run candidates; publication and selection are
independent; full read/parse A/B is required; freeze records `actual_code_sha`;
PAT / TOTAL_EQUITY / BANK TOP_LINE / cents-share are locked; unseen 12-file
HOLDOUT is identity-only. Canonical regen uses one freeze object for freeze,
baseline, experiments, and ranking.

## Objective

Fix the investigation framework before T10 blind source adjudication. Do not change production to V2. Do not lower the historical coverage floor.

## P0 fixes

### 1. Separate source extraction from production entity selection

Current issue: `expected_entity_scope` is passed into `resolve_source_facts()` and `source_admission_failure()`, so source-proven Group/Bank/Company facts can be rejected before the SourceFact layer.

Required architecture:

```text
PDF
→ candidates
→ all source-proven SourceFacts
→ production selector
→ requested entity / period / CURRENT / 3M
```

Required tests:

```text
Company + Group in PDF
→ extraction emits both
→ Company selector returns Company only

Group only
→ extraction emits Group
→ Company selector returns none
```

### 2. CandidateTrace must use exact in-run candidates

Do not rebuild diagnostics with a second `build_candidates()` call.

Return/expose the exact candidate tuple used by the filing pipeline and trace those exact objects, including the same accounting regime.

Recommended result object:

```python
FilingPipelineResult(
    statements=...,
    candidates=...,
    source_facts=...,
    derived_facts=...,
    stage_metrics=...,
)
```

### 3. Separate publication from production selection

Track independently:

```text
source_fact_created
validation_status
publication_status
production_selection_status
production_selected
production_selection_reason
```

Do not treat `publication_status != WITHHELD` as `production_selected=True`.

### 4. Strengthen determinism testing

Current A/B reuses one in-memory `CanonicalDocument`.

Required:

```text
Run A:
read PDF fresh
→ parse/OCR
→ full pipeline

Run B:
read PDF fresh again
→ parse/OCR
→ full pipeline
```

Compare:

```text
tokens
page modes
statement regions
tables
rows/cells
candidate IDs/context
SourceFacts
DerivedFacts
reason codes
selection
```

### 5. Record actual executable code SHA

Every run must record both:

```text
investigation_base_sha
actual_code_sha
```

plus:

```text
branch
working_tree_dirty
source_snapshot_id
uv.lock SHA
config hash
concept-registry hash
issuer-master hash
PyMuPDF/Tesseract/pytesseract versions
OS/container digest
```

### 6. Finish the Source Metric Truth Contract

Lock these before T10:

```text
PAT:
profit for period vs attributable-to-owners

TOTAL_EQUITY:
total entity equity vs equity attributable to owners

BANK TOP_LINE:
Interest income vs Gross income vs Total operating income

per-share normalization:
Rs/share vs cents/share
```

Reviewers must not make these decisions case by case.

### 7. Replace the current “holdout”

The current 11-file holdout comes from the same 33 files already inspected/tuned against.

Use:

```text
existing 33 = DEV + regression corpus
new unseen 10–15 filings = final HOLDOUT
```

Do not inspect the new holdout during development.

### 8. Complete CandidateTrace fields

Add:

```text
page_classification_status
statement_detection_status
table_detection_status
table_reconstruction_status
row_reconstruction_status
header_evidence
unit_evidence
duration_evidence
comparison_evidence
production_selection_reason
```

### 9. Preserve all concept alternatives

For ambiguous/unresolved rows persist all candidate concepts:

```text
metric_code
match_kind
matched_alias
source_concept
score
blocker/rejection reason
accounting regime
```

### 10. Regenerate one canonical baseline

After the fixes, regenerate:

```text
baseline_run_summary.json
experiment_summary.json
defect_family_ranking.json
investigation_freeze.json
```

All must reference the same `actual_code_sha`, source manifest and runtime.

### 11. Run CI on the investigation branch

Require green:

```text
Ruff
mypy
V2 unit tests
CandidateTrace tests
source-truth schema tests
gate-ablation tests
page-routing tests
numeric parser tests
universe/freeze tests
full pytest
```

## Do not change yet

Until T10 source truth exists:

```text
do not remove cascade
do not enable document-level entity inheritance
do not enable page/hybrid OCR in production
do not choose H2/U2/P2
do not expand aliases from V1 output
do not loosen exact-quarter rules
do not lower coverage floors
do not promote V2
```

## Pre-T10 Definition of Done

```text
[x] source extraction no longer filters by expected production entity
[x] production selection measured separately
[x] CandidateTrace uses exact pipeline candidates
[x] CandidateTrace records real production-selection outcome
[x] full read/parse A/B is deterministic
[x] actual executable SHA recorded
[x] PAT semantic locked
[x] TOTAL_EQUITY semantic locked
[x] BANK TOP_LINE semantic locked
[x] cents/share normalization locked
[x] new unseen 10–15 filing holdout selected
[x] canonical baseline regenerated
[x] investigation CI green (ruff, mypy, tests/v2)
```

Canonical freeze/baseline/experiments/ranking share
`actual_code_sha = e92689dabc400e3609e64a9d50512e99d9374dec:dirty:0e06ef8bd0b3`.
Locked-33: 33/33 deterministic, 1642 SourceFacts, 36 `CONTEXT_EVIDENCE_INCOMPLETE`.
CandidateTrace now stores `candidate_id` and `source_fact_id`. Run-level
canonical parquet/jsonl files are written at `outputs/v2_extraction_baseline/`.
Production stays V1. Floor stays 8924. T10 is not started.

Full `pytest` still reports 8 V1 `tests/regression/test_universe_failure_pack.py`
failures. Those tests call V1 `extract_filing` directly; that extractor is
unchanged versus `e92689d`. They are not V2 investigation regressions and must
not be “fixed” by promoting V2 or loosening floors.

Only then begin T10 blind source adjudication.
