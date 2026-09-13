# V2 Concept Registry

One authoritative registry: `cse_financial_etl.v2.taxonomy.registry`. Semantic truth must not be copied into regexes, `metric_catalog.yml` forks, or hardening overrides.

## Source concepts (initial)

`PAT`, `PBT`, `EPS_BASIC`, `EPS_DILUTED`, `NAVPS`, `OPERATING_PROFIT`, `TOTAL_EQUITY`, `TOTAL_ASSETS`, `TOTAL_LIABILITIES`, `TOP_LINE`

## Derived concepts

`EPS_SELECTED`, `LIABILITIES_TO_EQUITY`, `ROE`, `ROA`, `NPM`

`TOTAL_LIABILITIES` is source-only. `TOTAL_ASSETS - TOTAL_EQUITY` is a validation signal, not a publishable derivation.

## Market concept

`LAST_TRADED_PRICE` — last valid trade on or before quarter end for the exact security.

## Target registry fields

`code`, `display_name`, `metric_type`, `statement_types`, `period_behavior`, `unit_dimension`, `allowed_entity_profiles`, `accounting_regimes`, `exact_aliases`, `synonyms`, `forbidden_aliases`, `source_only`, `derivation_allowed`

## Matcher (Phase 8)

Exact alias → controlled alias → RapidFuzz candidate generation → structural compatibility → abstain.

RapidFuzz may not decide publication truth. Embeddings are a future `ConceptCandidateProvider`.

## Implemented (Phase 7–8)

Loader: `cse_financial_etl.v2.taxonomy.registry.load_registry`. Duplicate aliases raise `RegistryConflictError`.

Matcher order: exact alias (including regime aliases) → controlled normalized label → RapidFuzz `token_set_ratio` ≥ 90 → abstain when top scores are within delta 2 across different codes.

Forbidden aliases: `EBITDA` is not operating profit; closing market price is not last traded price.

