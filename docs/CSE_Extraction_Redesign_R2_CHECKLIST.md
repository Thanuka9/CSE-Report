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
| Six-PDF zero-fallback compiler acceptance | DONE | Vendored source PDFs; required CI acceptance test |
| Resource budget driving candidate search | DONE | Shared iterations/time/width; ambiguity and stop-preservation tests |
| Native StageCache / Accuracy_Quality sheet | DONE | Ingestion and workbook callers; cache invalidation and denominator tests |
| MiniLM extra removal | DONE | pyproject and lockfile; README updated |
| CI immutable-main / no patch-push | DONE | Read-only Linux/Windows workflow |
| Manual gold fixture context | DONE | 34 contextual financial checks and 4 price checks pass; seeded accuracy excluded |
| Atomic gold generation switch | DONE | Immutable generation + CURRENT.json; interrupted activation test |
| OS-level PDF/OCR cancellation; all-stage resume | PARTIAL | Resolver limits/native cache do not implement these broader guarantees |
| Human 100-issuer adjudication | EXTERNAL | Bank reviewers; current manual sample is four reports |
| Authenticated official release identities | EXTERNAL | Local decision contract is not an identity provider |
| Full-universe / wider OCR accuracy acceptance | PENDING | Not performed in this completion run |

## Freeze (still in force)
No LLM on publish; regex + RapidFuzz; never blank→0; never A−E liabilities; exact 3M flow; never live prices as quarter-end.
