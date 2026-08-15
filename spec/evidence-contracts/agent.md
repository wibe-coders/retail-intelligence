# Evidence Contracts Specification

## Authority and boundary

This document refines the evidence and answer contracts in the
[main specification](../agent.md). It owns source identity, evidence windows, normalized
intelligence, cited answers, and persistence boundaries. Video ingestion, model execution, indexing
infrastructure, and the web API are outside this boundary.

The current Python package implements the contracts in this document as framework-independent domain
models, persistence ports, and a deterministic in-memory adapter.

## Domain contracts

The public models are immutable dataclasses grouped by their owning domain:

- `retail_intelligence.domain.media` defines source identity and metadata, non-empty UTC half-open
  time ranges, source-frame ranges, retention classes, and complete, partial, or gap evidence
  windows.
- `retail_intelligence.domain.intelligence` defines pipeline runs and provenance, evidence links,
  observations, derived events, metrics, insights, and evidence records. A caption is an observation,
  not a derived event or user-facing fact.
- `retail_intelligence.domain.query` defines citations and answer states. A supported answer requires
  text and at least one citation. Ambiguous, unsupported, and out-of-retention answers require a
  matching abstention reason.

These contracts and their validation rules are defined in
`retail_intelligence/domain/media/__init__.py`,
`retail_intelligence/domain/intelligence/__init__.py`, and
`retail_intelligence/domain/query/__init__.py`. Each subpackage's `__all__` list is its public API;
`retail_intelligence/domain/_base.py` is private shared machinery.

Every domain model exposes `to_dict`, `from_dict`, `to_json`, and `from_json`. Serialization produces
plain JSON containing explicit registered type tags, rejects unknown types or mismatched fields, and
round-trips tuples, enums, and UTC datetimes without a framework, database, or model SDK. The shared
implementation is in `retail_intelligence/domain/_base.py`.

## Pipeline identity and idempotency

`retail_intelligence/domain/identity.py` deterministically identifies a pipeline run, its evidence
window, and each ordered observation. Source content checksum, UTC half-open time range, pipeline
version, and configuration determine the shared identity. Observation kind and zero-based sequence
distinguish normalized outputs from the same pipeline input.

Configuration is canonical JSON before hashing. Mapping order, JSON whitespace, integral float
representation, and list-versus-tuple representation do not change an identifier. Credential-bearing
keys are removed at every nesting level. URL user information and signed query parameters are removed
while the resource location remains identity-bearing. Invalid serialized configuration and duplicate
keys fail without including the rejected configuration in the error or traceback.

## Persistence boundary

`retail_intelligence/ports/storage.py` separates persistence into protocols for sources, evidence
windows, observations and events, pipeline runs, and citations. Temporal queries require an exact
store, camera, and recording reference plus a UTC half-open time range.

`retail_intelligence/adapters/storage/in_memory.py` implements every port for deterministic tests and
the one-camera experiment. It is process-local and is not a production database. Its behavior is:

- Saving equal immutable content under the same identifier is idempotent. Reusing an identifier for
  different content raises `ConflictingRecordError` and preserves the existing record.
- Results are isolated by the complete source reference, include only overlapping time ranges, and
  are returned as immutable tuples sorted by identifier. Intervals that only touch at one endpoint
  do not overlap.
- A pipeline run may move from `queued` to `running`, `failed`, or `cancelled`, and from `running` to
  `succeeded`, `failed`, or `cancelled`. It cannot leave a terminal state or change its source, time
  range, pipeline version, or configuration identifier.

## Acceptance cases

- Domain models round-trip through their JSON representation and reject unknown types or fields.
- Evidence completeness agrees with expected and observed frame counts.
- Intelligence links back to evidence from the same source.
- Supported answers contain cited text; every other answer state contains a matching abstention.
- Re-saving equal records is idempotent, while identifier conflicts fail without replacing data.
- Temporal queries isolate stores and treat adjacent half-open intervals as non-overlapping.
- Pipeline runs advance only through the allowed lifecycle without changing immutable identity.
- Equivalent safe configurations reproduce pipeline, window, and observation identifiers; changing
  an identity-bearing input changes the resulting identifiers.
- Credential changes and refreshed URL signatures do not change identity, while a different signed
  resource path does.

The executable checks are in `tests/test_domain_contracts.py`,
`tests/test_in_memory_evidence_storage.py`, and `tests/test_pipeline_identity.py`.
