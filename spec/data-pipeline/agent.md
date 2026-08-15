# Data Pipeline Specification

## Authority and boundary

This document refines the ingestion, analysis, and indexing parts of the
[main specification](../agent.md). It owns the path from a camera or video file to indexed evidence.
Natural-language retrieval, answer generation, and the web API are outside this boundary.

The first accepted deployment processes one 1080p, 30 FPS, H.264 camera on one DGX Spark. More
cameras are unsupported until the complete co-resident stack passes the capacity gates below.

## Theory

A camera timeline becomes immutable evidence windows. RT-CV supplies continuous structured
observations; one RT-VLM slot supplies bounded semantic observations; indexing preserves both the
evidence and any gaps. The Spark is one shared resource pool, so admission is based on full-stack
measurements rather than isolated service limits.

This deliberately rejects running every camera through RT-VLM. A later camera can reuse the same
window, budget, and admission contracts without creating a parallel pipeline.

## Pipeline

```text
camera or file
  -> register and decode
  -> timestamped evidence windows
     |-> RT-CV detection and tracking --------------------|
     |-> sampled frames -> RT-VLM captioning -------------|
  -> normalize and combine observations
  -> durable evidence store and search index
```

1. Register each source once. Keep credentials in the secret store; persist only a secret reference.
2. Use source presentation timestamps, not arrival time, to form half-open windows `[start, end)`.
3. Run RT-CV continuously and retain its boxes, classes, confidences, and track identifiers.
4. Send non-overlapping windows from one active camera to RT-VLM for continuous captioning.
5. Normalize vendor output without erasing the original payload or model provenance.
6. Store and index complete, partial, and gap records. Indexing a partial record is better than
   silently omitting the interval.

The baseline uses VSS 3.2.x ARM64/SBSA images, RT-DETR ResNet50 with its tracker, and Cosmos3 Nano
Reasoner. Pin exact container digests, model revisions, prompts, and configuration in each pipeline
run. Upgrading any of them creates a new pipeline version.

RT-CV recognizes only the deployed model's documented label set. Unknown objects remain unknown; the
pipeline must not reinterpret a warehouse class as a product, shelf interaction, or retail event.

## Core records

These are domain contracts, not required wire formats.

### `Source`

- store, camera, and recording identifiers;
- RTSP or file reference and separate credential reference;
- codec, source width, height, and nominal frame rate;
- clock and calibration metadata when available;
- retention class.

### `EvidenceWindow`

- stable window identifier and source identifier;
- UTC start and end timestamps plus source frame bounds;
- expected and observed frame counts;
- pipeline version;
- completeness: `complete`, `partial`, or `gap`.

The identifier derives from the source, time range, pipeline version, and configuration. Replaying a
window updates or reproduces the same logical record; it cannot create duplicate evidence.

### `InferenceBudget`

- model and tokenizer version;
- final model-input width and height;
- chunk duration, sampling method, and actual selected frame count;
- patch size, temporal stride, and computed visual-token count;
- admission result and rejection reason.

The budget describes one inference call. It is distinct from the Spark's concurrent workload limit.

### `Observation`

- kind: RT-CV box/track or RT-VLM caption;
- source and evidence-window identifiers;
- UTC and frame bounds;
- class or text, confidence when supplied, and model provenance;
- reference to the unmodified vendor output.

A caption is a model observation, not a fact. A retail event exists only when an explicit,
versioned rule or model derives it and retains links to its input observations.

### `EvidenceRecord`

- evidence window and all normalized observations;
- derived events, each with its rule or model version;
- completeness and explicit missing stages;
- source-media locator for later clip extraction;
- store/index status and last error.

### `PipelineRun`

- source and dataset revision when applicable;
- pinned images, models, prompt, and configuration;
- stage states and timestamps;
- resource and latency measurements;
- failures, retries, skipped windows, and final result.

Records and logs must not contain credentials, signed media URLs, frames, or full prompts.

## Windowing and visual-token budget

The token count for one inference is:

```text
patches_per_frame = ceil(width / 32) * ceil(height / 32)
visual_tokens = ceil(selected_frames / 2) * patches_per_frame
```

Accept only 4,096 through 16,384 visual tokens, inclusive. Calculate from the actual selected frames
and final model tensor—not the source resolution or requested frame rate. Non-divisible dimensions
use ceiling semantics; never crop or round down to make a request fit.

The baseline is NVIDIA's measured profile:

```text
window              10 seconds
model input          448 x 448
selected frames      80, evenly spaced across the window
effective sampling   8 FPS
visual tokens        ceil(80 / 2) * 14 * 14 = 7,840
```

Reuse the VSS 3.2 preprocessing for this profile and record the resulting transform. Do not add a
custom crop, mosaic, or aspect-ratio policy until it has a separate accuracy evaluation. Adjacent
windows do not share tokens.

Reject a window before inference when its configuration or realized sample falls outside the token
range. Do not duplicate frames to reach the minimum. A low-frame-rate or damaged source produces an
explicit gap or partial record.

## DGX Spark admission and backpressure

Exactly one continuous RT-VLM caption stream may be active. A second request is rejected before it
creates another decode or inference pipeline. Switching the active camera takes effect on the next
window boundary so evidence ownership stays unambiguous.

The RT-VLM queue holds at most one ready window in addition to the running window. If the queue is
full, skip the new VLM job and record a semantic-coverage gap; never allow delay to grow without
bound. Retry a failed VLM inference once. If it fails again, publish the RT-CV evidence as `partial`
with the failure reason.

NVIDIA measured the 7,840-token profile on DGX Spark at one caption stream with about 8.6 seconds of
latency per ready 10-second chunk. Two caption streams averaged about 27 seconds and cannot sustain
continuous input. NVIDIA's isolated RT-CV benchmark reached five 1080p30 streams with RT-DETR
ResNet50, but it did not include the co-resident VLM, local query model, storage, or application.
Neither number is a production capacity claim for this system.

The deployment must also account for Spark's single integrated GPU, unified CPU/GPU memory, and
single NVDEC/NVENC engines. Do not infer a decoder limit from the engine count. H.265, AV1,
transcoding, additional cameras, and duplicate consumers remain unsupported until measured with the
whole stack.

## Failure behavior

- Duplicate source or stream identifiers fail visibly; they never attach to an existing pipeline.
- Out-of-order, duplicate, or missing timestamps are recorded. The pipeline does not invent time.
- An RTSP interruption closes the affected interval as partial or gap and reconnects without
  rewriting earlier windows.
- A realized token count is checked again immediately before inference.
- Stage retries are idempotent and cannot duplicate observations or index records.
- Index failure leaves durable evidence pending for retry; it does not rerun model inference.
- Overload rejects or skips named work and records why. It never creates an unbounded queue.
- Stopping a source waits for its running window, rejects new work, and releases its decoder and
  inference resources.

## Evaluation data

Use dataset training data for pipeline bring-up and throughput measurements. Do not report accuracy
from data used to tune prompts, thresholds, mappings, or models.

### PhysicalAI-SmartSpaces

Use [PhysicalAI-SmartSpaces](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces) for file
ingestion, calibration, detection, tracking, trajectories, and load tests. After multi-camera
admission is implemented, also use it for cross-camera handoff. Use scene-held-out validation or test
data for reported tracking results. Keep synchronized cameras and Cosmos Transfer re-renders with
their source scene in the same split, and exclude the documented corrupt
`MTMC_Tracking_2024/scene_071/camera_0649` video.

This dataset is mostly synthetic and has no natural-language or retail-interaction ground truth. It
cannot validate caption faithfulness or retail insight accuracy.

### Retail supplements

- Use [RetailAction](https://huggingface.co/datasets/standard-cognition/RetailAction) validation and
  test splits for real-store `take`, `put`, and `touch` interaction evaluation.
- Use the [MERL Shopping Dataset](https://www.merl.com/research/highlights/merl-shopping-dataset) for
  continuous-video ingestion, action timing, and events that cross window boundaries.

Both supplements are internal evaluation inputs. Record their custom or research-use terms and do
not redistribute them or use them for production claims without legal approval. Do not add UCA or
UCF-Crime until their conflicting usage terms are resolved. Do not count AI City data as an
independent benchmark when it duplicates PhysicalAI-SmartSpaces.

Every dataset manifest records its source URL, revision, license, checksums, selected files, split,
exclusions, and allowed uses. Sample selection is a later task. It must include normal activity,
occlusion, sparse and crowded scenes, an action crossing a window boundary, and an ambiguous clip.

## Acceptance gates

### Contract checks

- `448x448` with 80 frames produces 7,840 tokens and is accepted.
- `448x448` at 3 FPS for 10 seconds produces 2,940 tokens and is rejected.
- `448x448` at 17 FPS for 10 seconds produces 16,660 tokens and is rejected.
- Odd frame counts use `ceil(frames / 2)`.
- Dimensions just above a 32-pixel boundary consume another patch row or column.
- Missing duration, zero dimensions, zero frames, and insufficient source frames fail before
  inference.
- A second caption stream is rejected even when each request is individually within its token
  budget.

### Pipeline checks

- Replaying a window produces no duplicate observations or evidence records.
- VLM failure produces indexed, partial RT-CV evidence after one retry.
- RTSP loss creates a visible gap and recovery does not rewrite completed windows.
- Index recovery resumes from durable evidence without rerunning inference.
- Every ready, skipped, failed, and indexed window can be reconciled by identifier.

### DGX Spark gate

Run a 30-minute warm-up followed by a four-hour full-stack soak with the baseline camera and model
profile. Require:

- no OOM, container restart, device reboot, or monotonically growing queue;
- no missing window identifiers or silent drops;
- RT-CV sustained processing at least 90% of its configured frame rate;
- RT-VLM caption p95 at or below the 10-second window interval;
- storage and indexing to catch up after a transient failure.

Repeat the gate for every supported codec, resolution, model revision, or higher camera count. Report
model-quality metrics separately from pipeline correctness. Establish the first quality baseline
before setting regression thresholds; passing a systems soak does not establish accurate insights.

## Theory note

```text
Theory:      A source timeline becomes immutable evidence windows. RT-CV supplies continuous
             structure; one RT-VLM slot supplies bounded semantics; gaps remain first-class data.
Instead of:  Continuous VLM inference for every camera or capacity inferred from isolated maxima.
Reused:      VSS service boundaries, token equation, and measured 448x448/80-frame profile.
New concept: EvidenceWindow, InferenceBudget, and SparkAdmissionPolicy.
Assumes:     One 1080p30 H.264 camera, VSS 3.2.x, and non-overlapping 10-second windows.
Cost:        One 7,840-token caption inference every 10 seconds uses nearly all measured captioning
             capacity on the Spark.
Watch:       CV, VLM, query models, decode, storage, and the app contend for one resource pool; only
             the full-stack soak establishes safe capacity.
```

## References

- [VSS RT-VLM performance](https://docs.nvidia.com/vss/latest/performance-rt-vlm.html)
- [VSS RT-CV performance](https://docs.nvidia.com/vss/latest/performance-rt-cv.html)
- [VSS Real-Time VLM](https://docs.nvidia.com/vss/latest/real-time-vlm.html)
- [VSS prerequisites](https://docs.nvidia.com/vss/latest/prerequisites.html)
- [DGX Spark hardware](https://docs.nvidia.com/dgx/dgx-spark/hardware.html)
