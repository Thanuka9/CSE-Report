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

## PARTIAL / NOT DONE (in-repo remaining)
| Item | Status | Why |
|---|---|---|
| Six-PDF zero-fallback compiler acceptance | PARTIAL | `test_compiler_real_pdfs.py` may exist; CI still skips when `data/**` is absent |
| Resource budget driving beam search | PARTIAL | `ResourceBudget.exhausted()` checked; beam width/iterations not fully enforced |
| StageCache / Accuracy_Quality sheet | PARTIAL | helpers exist; not all called every run |
| MiniLM extra still in pyproject | NOT DONE | `semantic` extra still listed; default-off is not removal |
| CI immutable-main / no patch-push | NOT DONE | workflow still needs rewrite |
| Gold fixture context fields | PARTIAL | MANUAL_* flows checked; seeded rows remain numeric-only |
| Atomic gold promote | NOT DONE | per-file `os.replace` |
| Human 100-issuer adjudication | EXTERNAL | bank reviewers |
| Official release identities | EXTERNAL | gate exists (`contracts/release.py`); identities are bank-supplied |

## Freeze (still in force)
No LLM on publish; regex + RapidFuzz; never blank→0; never A−E liabilities; exact 3M flow; never live prices as quarter-end.
