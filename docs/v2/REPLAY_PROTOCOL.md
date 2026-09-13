# V2 Replay Protocol

The fixed-input replay runs in parallel with V2. It does not block V2 start.

## Runs

| Run | Code | Input | Purpose |
|---|---|---|---|
| Reference | historical accepted code | frozen Sept-10 source snapshot | historical reference |
| Replay A | current main | same Sept-10 snapshot | code-only comparison |
| Replay B | current main | same Sept-10 snapshot | determinism |
| Current A | current main | newly frozen current snapshot | current production behavior |
| Current B | current main | same current snapshot | determinism |

## Runtime pin

Capture code SHA, source snapshot ID, every PDF SHA, market-data snapshot, configuration hash, policy hash, concept registry hash, `uv.lock` hash, Python version, OS/container identity, PyMuPDF/pdfplumber/OCR/Tesseract versions, and extraction-affecting environment variables.

Skeleton: `scripts/v2_fixed_input_replay.py` and `cse_financial_etl.v2.diagnostics.replay`.

## Fact identity

Do not compare only counts. Diff key:

```text
filing_version_id
entity_scope
period_end
duration_months
comparison_role
metric_code
```

Classes: `UNCHANGED`, `LOST`, `NEW`, `VALUE_CHANGED`, `CONTEXT_CHANGED`, `STATUS_CHANGED`.

If Replay A and Replay B differ materially: **STOP DIAGNOSTIC ATTRIBUTION** and find nondeterminism first.

## Decision thresholds

Pre-registered in `AGENT_IMPLEMENTATION_PLAN.md` §30. `2,394 / 8,924` is automatic class B.
