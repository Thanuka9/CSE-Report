# CSE Extraction Redesign R2 — honest status

DONE only when a named test or wired production caller proves it. Labels without callers are PARTIAL/NOT DONE.

## Compiler / publish path
| Item | Status | Evidence |
|---|---|---|
| Geometry-bound table reconstruction | DONE | `tests/unit/redesign/test_table_reconstruction.py` |
| Header dates/entities (no invented 31 Dec) | DONE | `tests/unit/redesign/test_header_tree.py` |
| Bounded unit typing (EPS not ×1000) | DONE | `tests/unit/redesign/test_unit_typing.py` |
| Compiler is default path; honest routing fields | DONE | `tests/regression/redesign/test_compiler_wiring.py`, `tests/unit/redesign/test_eligibility_publisher.py` |
| Shared eligibility + arbiter abstain + FAILED preserved | DONE | `tests/unit/redesign/test_eligibility_publisher.py` |
| REVIEW not official-publishable | DONE | `tests/unit/test_acceptance.py` |
| Vacuous PASSED removed | DONE | `tests/unit/test_pipeline_stamping.py` |
| Retry uses same extract kwargs | DONE | `tests/unit/test_equation_retry.py::test_retry_extract_kwargs_reach_extractor` |
| Excel reads CSV prices (no live re-resolve) | DONE | code path in `reporting/excel.py`; RESOLVED_HISTORICAL accepted |
| Review CSV after gate hits | DONE | `pipeline.py` stage 7 order |
| EPS/NAVPS sign-aware, UNTESTED without shares | DONE | `tests/unit/test_equation_retry.py` |

## Completion update — 9 September 2026

See [completion QA and limits](R2_Completion_QA_2026-09-09.md).

| Item | Status | Evidence |
|---|---|---|
| Six-PDF zero-fallback compiler acceptance | DONE | Vendored source PDFs; required Linux/Windows CI acceptance test |
| Resolver C resource fairness | DONE | Per-concept iteration budget with global wall-clock/hypothesis bounds; regression tests and targeted NDB proof |
| Native StageCache / Accuracy_Quality sheet | DONE | Ingestion and workbook callers; cache invalidation and denominator tests |
| MiniLM extra removal | DONE | pyproject and lockfile; README updated |
| CI immutable-main / no patch-push | DONE | Read-only Linux/Windows workflow; Ruff, mypy, full pytest and six real PDFs |
| Manual gold fixture context | DONE | 34 contextual financial checks and 4 price checks pass; seeded accuracy excluded |
| Atomic gold generation switch | DONE | Immutable generation + CURRENT.json; interrupted activation test |
| OS-level PDF/OCR cancellation | DONE | Spawned per-PDF worker with process-tree termination; 480 s hard timeout proven in full-universe run |
| Resumable production processing | DONE | Raw/bronze/resilient caches and retry integration wired into full-universe workflow |
| Full-universe OCR engineering proof | DONE | Final main run `4e9ef5ff-878f-4348-b0fe-4d48b6572e67` / Actions `34339810852`: 281 issuers, 829 filings attempted, 9023 safe DRAFT-publishable facts, zero engineering gates |
| Quarantined pathological filings | DONE | Three hard PDF/OCR timeouts remain fail-closed, explicitly recorded, bounded by versioned acceptance policy; zero unhandled pipeline errors |
| Coverage acceptance baseline | DONE | Calibrated from the safe fail-closed universe result; DRAFT-publishable coverage is explicitly measured |
| Final main deterministic CI | DONE | Actions `34340973782` on `a8f0ac6a8bbfb7374c8fda3c9dc41493ebecfc81`: Ubuntu + Windows checks successful |
| Human 100-issuer adjudication | EXTERNAL | Independent reviewers; generated 100-issuer/900-row packet remains UNADJUDICATED |
| Authenticated institutional release identities | EXTERNAL | Signed local review contract exists; institution-controlled identity/key governance remains external |
| GitHub `main` branch protection | EXTERNAL ADMIN | Repository-admin setting; connector cannot enable it |

## Full-universe evidence note

The final 2026-09-09 main production proof completed extraction, price recovery, validation, adjudication-packet generation and acceptance classification successfully. Its acceptance artifact reports `ENGINEERING_PASS_EXTERNAL_PROOF_PENDING`, `engineering_gate_count=0`, three bounded process-tree timeout quarantines, and `unhandled_pipeline_error_count=0`. The only remaining gates are `GOLD_SAMPLE_INCOMPLETE` and `GOLD_ISSUER_SAMPLE_INCOMPLETE`, which deliberately represent the independent human proof requirement. Artifact `10102186226` is the retained evidence for Actions run `34339810852`.

The earlier red universe proof is retained as history: it exposed the stale pre-fail-closed coverage floor and the timeout behavior that led to the versioned quarantine policy. No accounting, entity, duration, unit, validation or publication rule was weakened to obtain the final engineering pass.

## Freeze (still in force)
No LLM on publish; regex + RapidFuzz; never blank→0; never A−E liabilities; exact 3M flow; never live prices as quarter-end; machine-derived ratios remain REVIEW until signed human approval for official release.
