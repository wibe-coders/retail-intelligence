# Retail Intelligence: Main Specification

## Authority

This is the codebase's product and architecture backbone. More detailed specs may refine it but must
not contradict it. When code and this document disagree, either restore the documented behavior or
change this document in the same review.

## Product

Turn retail CCTV into useful, evidence-backed observations and let an authorized user question them
in plain language. The complete runtime—including video processing, storage, retrieval, and language
models—runs on one DGX Spark. Runtime video and queries must not leave the device.

An answer is useful only when a user can inspect its supporting camera and time range. When evidence
is missing or conflicting, the system says so instead of filling the gap.

### First release

- Import recorded video and connect a small set of RTSP cameras.
- Find people and objects, correlate tracks across cameras, and derive occupancy, flow, dwell, and
  zone entry/exit events.
- Search, summarize, and ask questions over a selected store and time range.
- Return an answer with playable evidence clips and the source camera and timestamps.
- Show ingestion, analysis, and indexing status in the web app.

### Not in the first release

- Face recognition or persistent identity outside one analyzed visit.
- Demographic, emotion, intent, or theft claims.
- Automated enforcement or decisions about a person.
- POS, inventory, or staff scheduling integration.
- Guaranteed real-time processing for an unmeasured number of cameras.

## System hierarchy

Dependencies point toward the domain: apps and services call pipelines; pipelines use domain
contracts; adapters implement external ports. Domain code imports no web framework, model SDK,
database client, or NVIDIA service client.

```text
apps/
  web/                 Browser UI: query, evidence playback, camera and job status
services/
  api/                 Only public boundary; auth, authorization, validation, rate limits
  worker/              Runs bounded, retryable analysis and indexing jobs
domain/
  media/               Camera, recording, clip, time range, zone
  intelligence/        Observation, track, event, metric, insight, evidence
  query/               Question, filters, answer, citation, abstention
pipelines/
  ingest/              RTSP/file input, recording, clock and camera metadata
  analyze/             Detection, tracking, embedding, captioning, event derivation
  index/               Persist searchable text, vectors, attributes, and provenance
  answer/              Retrieve, rank, compose, verify, and cite
adapters/
  nvidia/              VSS, VIOS, RT-CV, RT-VLM, RT-Embedding, and local NIM clients
  storage/             Video, relational metadata, search/vector index, optional message bus
ops/
  dgx-spark/           Pinned images, Compose, resource profiles, volumes, health checks
evals/
  datasets/            Immutable manifests, licenses, checksums, split and exclusion rules
  tasks/               Tracking, event, retrieval, answer, latency, and load evaluations
tests/                 Cross-package contract and end-to-end tests
spec/                  Product, contracts, decisions, and operating requirements
```

Model names, databases, and brokers are adapter choices. Do not expose their response shapes above
the adapter boundary.

## Canonical flow

```text
camera or file -> ingest -> analysis -> observations/events -> store and index
question -> retrieve from store/index -> compose and verify -> cited answer and evidence clip
```

Live work is asynchronous. Every submitted recording or time window gets a job with a durable state:
`queued`, `running`, `succeeded`, `failed`, or `cancelled`. Queues are bounded; overload delays or
rejects work rather than exhausting the DGX Spark.

Use inexpensive detection and behavior rules to select candidate clips before expensive VLM
analysis where possible. Preserve independent paths for visual embeddings, object attributes, and
captions so retrieval can combine them without treating generated text as fact.

## Core contracts

All stored intelligence carries:

- a store, camera, and recording identifier;
- UTC start and end timestamps plus source frame bounds when available;
- the producing model, model version, configuration, and pipeline run;
- confidence and a link to the source media;
- a creation time and retention class.

An **observation** is direct model output, such as a box, track, or caption. An **event** combines
observations under an explicit rule, such as entering a zone. A **metric** aggregates events. An
**insight** is a user-facing interpretation and must retain the evidence chain back to observations.

An answer contains text, citations, and an explicit confidence state. Each factual claim must cite at
least one camera/time range. Aggregates must also name the filters and interval used. Unsupported,
ambiguous, and out-of-retention questions return an abstention; they are not converted into plausible
answers.

Cross-camera identities are scoped to a pipeline run and store visit. They are not identities of
real people. Reprocessing is idempotent by source checksum, time range, pipeline version, and
configuration.

## Data strategy

[PhysicalAI-SmartSpaces](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces) is bootstrap
and component-evaluation data. It provides over 280 hours of synchronized 1080p video from nearly
1,800 cameras, with calibration, cross-camera track IDs, and 2D/3D spatial annotations. This makes it
useful for ingestion, tracking, trajectories, occupancy, dwell, flow, and zone tests.

It is mostly synthetic and is not a retail question-answering dataset. It has no documented retail
event labels, product or shelf interactions, natural-language questions, answer citations, or
faithfulness labels. Recent named scenes are primarily warehouses. Therefore it cannot be the
release benchmark for retail insights.

Dataset rules:

- Start with RGB-only subsets; depth is optional and several terabytes.
- Preserve scene-level splits. Synchronized camera views must never cross splits.
- Keep each 2026 Cosmos Transfer re-render with its source scene to prevent leakage.
- Exclude the documented corrupt `MTMC_Tracking_2024/scene_071/camera_0649` video.
- Record the dataset revision, selected scenes, checksums, exclusions, and CC BY 4.0 attribution in
  an immutable manifest.
- Treat annotations as truth only for their documented detection and tracking tasks.

Before release, evaluate on consented, de-identified footage from representative target stores. Hold
out entire stores and time periods. The set must cover occlusion, crowds, lighting changes, camera
faults, and poor synchronization, and include an owner-approved event taxonomy. It must also contain
answerable and unanswerable questions with expected evidence ranges.

## Evaluation gates

A release candidate must pass fixed, versioned tests for:

- tracking and spatial events, including cross-camera handoff;
- event counts and time-bound aggregates;
- retrieval relevance across text, visual, and attribute queries;
- answer correctness, evidence coverage, and unsupported-question abstention;
- end-to-end latency, throughput, queue pressure, and recovery after restart;
- the real-store holdout, not only synthetic or publicly labeled test data.

Report stage metrics separately. A better tracking score does not establish that answers improved.
Never tune on the locked real-store holdout.

## DGX Spark deployment

Production is a reproducible, containerized single-node deployment. Pin ARM64/SBSA-compatible image
digests and keep version-sensitive driver, toolkit, Docker, Compose, model, and VSS requirements in a
machine-checked compatibility manifest. Persist media, metadata, indexes, and audit records on named
host volumes. Every service exposes health and readiness checks and declares CPU, memory, GPU, and
storage budgets.

“Runs entirely on one DGX Spark” is an acceptance test, not an assumption. Benchmark the chosen local
VLM, embedding model, and LLM together under the intended camera load. The release fails if steady
state exceeds its budgets, drops required evidence, or depends on a remote inference API. Runtime
egress is disabled by default; installation may fetch pinned artifacts through an explicit setup
step.

## Security and privacy

The API service is the only network entry point. It terminates HTTPS and enforces authentication,
store-scoped roles, request size and time limits, rate limits, and audit logging. NVIDIA services,
model servers, brokers, and databases stay on a private container network and are never exposed
directly.

Raw video, clips, embeddings, observations, prompts, and answers follow configurable retention and
deletion rules. Logs must not contain frames, credentials, full prompts, or user-identifying
metadata. Evidence access is authorized at request time; possession of a clip URL is not authority.

## Delivery order

1. Prove the single-device vertical slice: one file, one question, one cited clip.
2. Add normalized observations, deterministic events, and component evaluations.
3. Add durable jobs, RTSP ingestion, bounded queues, and restart recovery.
4. Add multi-camera correlation and store/time/zone query filters.
5. Build and lock the real-store evaluation set, then measure capacity and release readiness.

## Decisions still owned by the team

- Target camera count, resolution, frame rate, and acceptable analysis delay.
- First retail event taxonomy and required accuracy per event.
- Video and derived-data retention periods.
- User roles and whether stores are isolated tenants.
- Exact VSS release, local models, stores, and deployment resource profile.

Do not hide these choices behind defaults. Record each decision in `spec/decisions/` with the evidence
that justified it.

## References

- [NVIDIA VSS documentation](https://docs.nvidia.com/vss/latest/)
- [NVIDIA VSS known limitations](https://docs.nvidia.com/vss/latest/Known-Limitations.html)
- [NVIDIA DGX Spark hardware](https://docs.nvidia.com/dgx/dgx-spark/hardware.html)
- [PhysicalAI-SmartSpaces dataset card](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces)
