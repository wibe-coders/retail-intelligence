# One-file Vertical Slice Specification

## Boundary

This component proves the first delivery gate through the public application boundary. It registers
one local MP4, creates one deterministic evidence window and caption observation, indexes that
observation, answers a source-scoped question, and returns the cited media only after a store access
check. It is a process-local acceptance fixture, not the production web server or durable database.

`VerticalSlice.process` rejects missing files and checksum mismatches. The source checksum, UTC
range, pipeline version, and configuration determine the run, window, and observation identifiers.
A replay of a succeeded run returns its existing status without invoking a model or adding an
evidence or index record. Status exposes the terminal job state, window count, index count, and the
window's index state.

`VerticalSlice.ask` searches only observations for the requested source. A supported answer stores
a citation containing the camera and half-open UTC range. If retrieval or the answer adapter has no
support, it returns an `unsupported` abstention. The fixture models are deterministic: the caption
adapter returns configured text and the answer adapter can only repeat retrieved evidence.

`PublicApi.get_citation_clip` is the public evidence boundary. It resolves the durable citation and
window, checks that the caller has access to the cited store, and then reads the local MP4. The API
does not accept a media path from the caller. Citation identifiers are locators, not authorization.

## Cloud verification

```bash
PYTHONPATH=src python3 -m unittest tests.test_vertical_slice -v
```

The fixture uses `samples/hong-kong-passageway.mp4` and fake model adapters. It asserts a supported
camera/UTC citation, playable MP4 bytes through the authorized API, denial for another store,
unsupported-question abstention, visible succeeded/indexed state, and stable counts after replay.

## Repeat with pinned local models on DGX Spark

Target verification uses the same `VerticalSlice` and `PublicApi` orchestration and replaces only
`CaptionModel`, `AnswerModel`, and `EvidenceIndex` adapters. Before the run:

1. Record immutable container digests, model revisions, prompt checksum, embedding/index schema
   version, and inference parameters in the pipeline configuration. Do not use mutable image tags or
   model aliases.
2. Keep the MP4, prompts, model weights, index, and responses on Spark-local storage. Disable runtime
   egress and expose only the authenticated API service.
3. Run `python3 scripts/preflight_smoke_video.py` and require every line to report `PASS`.
4. Run the target harness with the pinned adapters twice against a clean durable store. Ask the
   supported and unsupported fixture questions, fetch the citation through
   `PublicApi.get_citation_clip`, and save both returned `SliceStatus` values.
5. Require one succeeded job, one indexed window, and one index record after both runs. Also require
   a camera and UTC citation, a playable authorized clip, denial for a different store, and an
   explicit unsupported abstention.

Report the focused cloud command separately from the target preflight and target harness results.
A fake-adapter pass proves orchestration only; it is not evidence that a local model ran or that the
DGX Spark target passed.

## Acceptance cases

- A checksum mismatch or non-file source fails before registration.
- Reprocessing cannot duplicate the evidence window, observation, index record, or pipeline run.
- Supported answers cite a camera and UTC range tied to the indexed evidence window.
- Unsupported questions abstain rather than composing text.
- Clip bytes are reachable through the store-authorized public API and not from a caller-supplied
  internal path.
- Job and index state are visible at the end of the flow.
