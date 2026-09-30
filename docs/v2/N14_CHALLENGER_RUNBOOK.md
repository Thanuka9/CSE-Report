# N14 Current-Universe V2 Challenger Runbook

Production default remains `extraction.engine: v1`. Floor remains `8924`.
This run is challenger-only via `--engine v2`.

## Why a runbook

`scripts/run_production_pipeline.py` writes dated artefacts under `outputs/` for the chosen `--as-of`.
A V2 challenger on `2026-09-09` would overwrite the retained V1 acceptance evidence unless those files are snapshotted first.

## Procedure

1. Snapshot V1 proof artefacts:

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dst = "outputs/n14_v1_snapshot_$stamp"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item outputs/universe_acceptance_2026-09-09.json $dst -ErrorAction SilentlyContinue
Copy-Item outputs/normalized_facts_2026-09-09.csv $dst -ErrorAction SilentlyContinue
Copy-Item outputs/pipeline_errors_2026-09-09.json $dst -ErrorAction SilentlyContinue
Copy-Item outputs/r4_hardening_2026-09-09.json $dst -ErrorAction SilentlyContinue
Copy-Item outputs/manifests/run_manifest_2026-09-09.json $dst -ErrorAction SilentlyContinue
```

2. Run offline challenger (default production config stays V1):

```powershell
uv run python scripts/run_production_pipeline.py `
  --as-of 2026-09-09 `
  --offline `
  --engine v2 `
  --skip-excel `
  --tunnel-b-always
```

3. Preserve challenger result separately:

```powershell
$out = "tests/v2/universe/n14_challenger_2026-09-09.json"
Copy-Item outputs/universe_acceptance_2026-09-09.json $out -Force
```

4. Report the fields required by the verified path (PDFs attempted/extracted/quarantined, SourceFacts, DerivedFacts, draft-publishable, unresolved counts, OCR failures).

5. Restore the V1 snapshot files if governance still needs the prior V1 acceptance path on disk.

## Hard stops

- Do not change `configs/app.yml` to `engine: v2`.
- Do not lower `min_draft_publishable`.
- Do not treat fail-closed coverage alone as source truth.
- Do not start N14 mid-N17 truth authoring if that would retune extraction rules.

## Latest completed run (2026-09-16)

Offline `--engine v2` on `2026-09-09`:

| Metric | Value |
|---|---|
| draft-publishable | 3748 / 8924 |
| EXTRACTED+DERIVED | 3894 / 8932 |
| PDFs attempted / extracted | 829 / 786 |
| OCR_REQUIRED_NOT_AVAILABLE | 43 |
| acceptance | ENGINEERING_FAILURES_PRESENT |
| delta vs prior challenger | +64 |

Canonical copies: `tests/v2/universe/n14_challenger_2026-09-09.json`, `n14_universe_acceptance_2026-09-09.json`.
Production default remains V1.
