# V2 Data Contract

Authoritative Python models live in `src/cse_financial_etl/v2/contracts/`.

All evidence-bearing objects are frozen Pydantic v2 models with `schema_version = v2.0.0` and `extra = forbid`.

## Provenance

`SourceRef` is mandatory on source cells, source facts, and fact candidates.

Minimum fields: `filing_id`, `filing_version_id`, `source_sha256`, `page_number`, `bbox`, `raw_text`, `parser_name`, `parser_version`.

## Canonical document

There is exactly one document IR:

`CanonicalToken` → `CanonicalLine` → `CanonicalPage` → `CanonicalDocument`

Native, OCR, and hybrid parsers must emit this IR. Do not create a parallel `OCRDocumentIR`.

## Canonical statement

`CanonicalStatement` owns `StatementRow`, `StatementColumn`, and `StatementCell`.

Column context (entity, period, duration, comparison role, unit) is bound to `StatementColumn` with explicit `*_evidence: tuple[SourceRef, ...]` before metric matching.

`StatementColumn.confidence` is diagnostic only.

## Facts

- `FactCandidate`: contextualized cell + row concept + column context. Missing context is `UNRESOLVED`, never assumed.
- `SourceFact`: `fact_kind=SOURCE`, complete source identity, no publication mutation.
- `DerivedFact`: `fact_kind=DERIVED`, formula id and input fact ids, never a source `cell_id`.

Independent status dimensions are on `SourceFact` and `DiagnosticStatuses`. One status must not hide another.

## Release

`ReleaseContext` is passed explicitly. V2 code must not call `set_release_mode` or read `_release_mode`.
