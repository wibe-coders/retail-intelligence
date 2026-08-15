# NVIDIA Adapter Specification

## Authority and boundary

This document refines the NVIDIA adapter boundary in the
[main specification](../agent.md). It owns conversion from sanitized RT-CV and RT-VLM responses into
canonical observations. Caption sampling and token admission are owned by the
[data pipeline specification](../data-pipeline/agent.md).

## Observation normalization

`retail_intelligence/adapters/nvidia/observations.py` converts RT-CV detections and tracks and RT-VLM
captions into canonical `Observation` values. Input envelopes must identify the source, UTC time and
frame bounds, model and version, configuration, pipeline run, creation time, retention class,
evidence media, and separately retained vendor output.

RT-CV detector class names are retained exactly as supplied; the adapter does not infer a retail
concept from a vendor label. A detection produces a box observation and, when it has a track
identifier, a track observation. RT-VLM text produces a caption observation. Optional confidence
remains absent when the vendor does not supply it.

## Safety boundary

Canonical observations contain query-free `vendor-output://` references to sanitized responses and
query-free `media://` evidence locators. Other schemes, URL credentials, query strings, and fragments
are rejected. Raw responses, frames, credentials, signed URLs, and full prompts do not enter the
canonical domain model.

Configuration retains safe scalar metadata such as prompt revisions but removes secret-bearing
entries and full prompts, instructions, and messages. Invalid vendor responses raise
`NormalizationError` naming the `rt-cv` or `rt-vlm` stage without converting malformed data into an
observation.

## Acceptance cases

- RT-CV boxes and tracks retain source, evidence, model, configuration, run, and vendor references.
- Unknown detector labels remain unchanged and missing confidence remains absent.
- RT-VLM captions remain observations rather than facts.
- Unsafe media or vendor-output references fail at normalization.
- Full prompts are removed while safe prompt revision metadata remains.
- Malformed output reports the failing vendor stage.

The executable checks and representative sanitized responses are in
`tests/test_observation_adapters.py` and `tests/fixtures/`.
