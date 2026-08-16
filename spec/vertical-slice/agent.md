# One-file Vertical Slice Specification

## Boundary

This component proves the first delivery gate through the public application boundary. It registers
one local MP4, creates one deterministic evidence window and caption observation, indexes that
observation, answers a source-scoped question, and returns the cited media only after a store access
check. It is a process-local acceptance fixture, not the production web server or durable database.

`VerticalSlice.process` rejects missing files and checksum mismatches. The source checksum, UTC
range, pipeline version, and configuration determine the run, window, and observation identifiers.
A replay of a succeeded run restores a missing index entry from the stored observation without
invoking a model or adding an evidence record. It fails visibly if a succeeded job has lost its
evidence or observation. Status exposes the terminal job state, window count, index count, and the
window's index state.

The public query accepts a registered source identifier rather than caller-supplied source metadata.
`VerticalSlice.ask` searches only observations for that source. A supported answer stores
a citation containing the camera and half-open UTC range. If retrieval or the answer adapter has no
support, it returns an `unsupported` abstention. The fixture models are deterministic: the caption
adapter returns configured text and the answer adapter can only repeat retrieved evidence.

`PublicApi.get_citation_clip` is the public evidence boundary. It resolves the durable citation and
window and registered source, checks that the caller has access to the cited store, and then reads
the local MP4. The API does not accept a media path from the caller and rejects a citation whose
locator differs from the registered source. Citation identifiers are locators, not authorization.

## Cloud verification

```bash
PYTHONPATH=src python3 -m unittest tests.test_vertical_slice -v
```

The fixture uses `samples/hong-kong-passageway.mp4` and fake model adapters. It asserts a supported
camera/UTC citation, playable MP4 bytes through the authorized API, denial for another store,
unsupported-question abstention, visible succeeded/indexed state, and stable counts after replay.

## Live DGX Spark verification

`scripts/run_dgx_e2e.py` is the target gate. It runs the fixture preflight, calls the standalone
RT-VLM service through `RTVLMFileCaptionModel`, and passes the real caption result through the same
`VerticalSlice` and `PublicApi` used by the credential-free acceptance tests. The live adapter
uploads the bounded local MP4, requests one 12-second chunk with 80 fixed frames at 448x448, records
the exact model and service release in observation provenance, and deletes the service-side upload
in a `finally` cleanup path.

The target gate then requires one succeeded run, one indexed window and observation, a supported
answer with a camera/UTC citation, an explicit unsupported abstention, byte-identical authorized
clip retrieval, and denial for another store. It replays the same input and requires that the model
call count remain one.

With a ready service and a key held only in the environment:

```bash
export RTVI_VLM_BASE_URL=http://localhost:8018
read -rsp "RT-VLM API key: " RTVI_VLM_API_KEY
echo
export RTVI_VLM_API_KEY
PYTHONPATH=src python3 scripts/run_dgx_e2e.py
unset RTVI_VLM_API_KEY
```

The live gate intentionally retains process-local storage, indexing, and the evidence-only answer
adapter. It proves the repository's one-file orchestration against real RT-VLM inference; it does
not prove a durable database, production retrieval model, continuous RTSP ingestion, or the
full-stack soak.

## Acceptance cases

- A checksum mismatch or non-file source fails before registration.
- Reprocessing cannot duplicate the evidence window, observation, index record, or pipeline run;
  it restores a missing index record from stored evidence without rerunning caption inference.
- Supported answers cite a camera and UTC range tied to the indexed evidence window.
- Unsupported questions abstain rather than composing text.
- Clip bytes are reachable through the store-authorized public API and not from a caller-supplied
  internal path.
- Job and index state are visible at the end of the flow.
