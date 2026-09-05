# Architecture

The platform uses immutable raw sources, candidate-first extraction, normalized long-form facts, deterministic validation and generated reporting outputs.

The detailed architecture, keys, stage contracts and acceptance criteria are in `production_specification.md`.

## Dependency direction

`domain` has no infrastructure dependencies. Extraction and transformation depend on domain types. Sources, documents, storage and reporting implement infrastructure around those rules. Orchestration composes them; it must not contain parsing or financial methodology.

