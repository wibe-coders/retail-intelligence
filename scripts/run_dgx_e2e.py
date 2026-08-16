#!/usr/bin/env python3
"""Run the approved DGX Spark fixture through the repository's live vertical slice."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from preflight_smoke_video import (  # noqa: E402
    EXPECTED_FRAME_COUNT,
    EXPECTED_FRAME_RATE,
    EXPECTED_HEIGHT,
    EXPECTED_WIDTH,
    FIXTURE_PATH,
    SELECTED_FRAME_COUNT,
    PreflightError,
    preflight,
    sha256 as fixture_sha256,
)
from retail_intelligence.adapters.fakes import EvidenceOnlyAnswerModel  # noqa: E402
from retail_intelligence.adapters.nvidia import (  # noqa: E402
    RTVLMFileCaptionModel,
    RTVLMServiceError,
)
from retail_intelligence.adapters.storage import (  # noqa: E402
    InMemoryEvidenceIndex,
    InMemoryEvidenceStorage,
)
from retail_intelligence.apps import AuthorizationContext, PublicApi  # noqa: E402
from retail_intelligence.apps.public_api import AuthorizationError  # noqa: E402
from retail_intelligence.domain.intelligence import (  # noqa: E402
    PersistenceState,
    PipelineRunState,
)
from retail_intelligence.domain.media import (  # noqa: E402
    FrameRange,
    RetentionClass,
    Source,
    SourceClock,
    SourceReference,
)
from retail_intelligence.domain.query import AnswerState  # noqa: E402
from retail_intelligence.pipelines import VerticalSlice  # noqa: E402


PIPELINE_VERSION = "ret56-dgx-e2e-v1"
PROMPT_REVISION = "ret56-visible-actions-v1"
DEFAULT_BASE_URL = "http://localhost:8018"


class EndToEndError(RuntimeError):
    """The live target did not satisfy the repository acceptance contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EndToEndError(message)


def api_key_from_environment() -> str:
    key = os.environ.get("RTVI_VLM_API_KEY") or os.environ.get("NGC_CLI_API_KEY")
    if not key:
        raise EndToEndError(
            "set RTVI_VLM_API_KEY or NGC_CLI_API_KEY without placing it in the repository"
        )
    return key


def build_source(path: Path) -> Source:
    digest = fixture_sha256(path)
    numerator, denominator = (int(part) for part in EXPECTED_FRAME_RATE.split("/"))
    return Source(
        "ret56-dgx-file",
        SourceReference("ret56-store", "ret56-passageway", "ret56-recording"),
        str(path),
        "h264",
        EXPECTED_WIDTH,
        EXPECTED_HEIGHT,
        numerator / denominator,
        RetentionClass.STANDARD,
        "sha256:" + digest,
        FrameRange(0, EXPECTED_FRAME_COUNT),
        SourceClock(
            datetime(2026, 8, 16, tzinfo=timezone.utc),
            0,
            EXPECTED_FRAME_COUNT,
            denominator,
            numerator,
        ),
    )


def run() -> dict[str, object]:
    preflight(FIXTURE_PATH)

    key = api_key_from_environment()
    base_url = os.environ.get("RTVI_VLM_BASE_URL", DEFAULT_BASE_URL)
    model = RTVLMFileCaptionModel(base_url, key)
    model.ready()
    model_id, release, api_version = model.metadata()

    source = build_source(FIXTURE_PATH)
    storage = InMemoryEvidenceStorage()
    index = InMemoryEvidenceIndex()
    configuration = {
        "window_seconds": 12,
        "caption_prompt_revision": PROMPT_REVISION,
        "model": model_id,
        "input_width": 448,
        "input_height": 448,
        "selected_frames": SELECTED_FRAME_COUNT,
    }
    pipeline = VerticalSlice(
        storage,
        index,
        model,
        EvidenceOnlyAnswerModel(),
        pipeline_version=PIPELINE_VERSION,
        configuration=configuration,
    )
    public_api = PublicApi(storage, pipeline)
    allowed = AuthorizationContext("ret56-operator", frozenset({"ret56-store"}))

    timestamps = tuple(range(EXPECTED_FRAME_COUNT))
    first = pipeline.process(source, timestamps)
    replay = pipeline.process(source, timestamps)

    require(first.pipeline_run.state is PipelineRunState.SUCCEEDED, "pipeline did not succeed")
    require(first.index_state is PersistenceState.INDEXED, "observation was not indexed")
    require((first.evidence_count, first.index_count) == (1, 1), "unexpected evidence counts")
    require(replay == first, "identical replay changed the pipeline result")
    require(model.call_count == 1, "identical replay reran RT-VLM inference")
    require(model.last_frame_counts == (SELECTED_FRAME_COUNT,), "RT-VLM did not report 80 frames")
    require(model.last_upload_deleted, "RT-VLM did not confirm upload deletion")

    observations = storage.find_observations(
        source.reference,
        first.pipeline_run.time_range,
    )
    require(len(observations) == 1, "expected one durable caption observation")
    observation = observations[0]
    require(observation.context.provenance.model == model_id, "stored model ID differs")
    require(observation.context.provenance.model_version == release, "stored release differs")
    require(
        observation.vendor_output_reference.startswith("vendor-output://rt-vlm/"),
        "stored vendor output reference is invalid",
    )

    supported = public_api.ask(
        allowed,
        source.source_id,
        "What does the person do?",
    )
    require(supported.state is AnswerState.SUPPORTED, "evidence-backed question was unsupported")
    require(len(supported.citations) == 1, "supported answer did not contain one citation")
    unsupported = public_api.ask(
        allowed,
        source.source_id,
        "Which submarines surfaced?",
    )
    require(unsupported.state is AnswerState.UNSUPPORTED, "unsupported question did not abstain")

    citation = supported.citations[0]
    clip = public_api.get_citation_clip(allowed, citation.citation_id)
    require(clip.content == FIXTURE_PATH.read_bytes(), "authorized clip differs from fixture")
    require(
        sha256(clip.content).hexdigest() == fixture_sha256(FIXTURE_PATH),
        "authorized clip checksum differs from fixture",
    )

    denied = AuthorizationContext("ret56-outsider", frozenset({"another-store"}))
    try:
        public_api.get_citation_clip(denied, citation.citation_id)
    except AuthorizationError:
        unauthorized_clip_denied = True
    else:
        unauthorized_clip_denied = False
    require(unauthorized_clip_denied, "cross-store clip access was not denied")

    return {
        "result": "PASS",
        "service": {
            "base_url": base_url,
            "model": model_id,
            "release": release,
            "api": api_version,
        },
        "inference": {
            "caption": observation.value,
            "latency_seconds": round(model.last_latency_seconds or 0.0, 6),
            "frame_counts": list(model.last_frame_counts),
            "upload_deleted": model.last_upload_deleted,
        },
        "pipeline": {
            "state": first.pipeline_run.state.value,
            "index_state": first.index_state.value,
            "evidence_count": first.evidence_count,
            "index_count": first.index_count,
            "replay_no_inference": model.call_count == 1,
            "stored_model_provenance": True,
        },
        "evidence": {
            "supported_answer": supported.state.value,
            "unsupported_answer": unsupported.state.value,
            "citation_camera": clip.camera_id,
            "citation_start": clip.utc_start,
            "citation_end": clip.utc_end,
            "clip_bytes": len(clip.content),
            "clip_sha256": fixture_sha256(FIXTURE_PATH),
            "unauthorized_clip_denied": unauthorized_clip_denied,
        },
    }


def main() -> int:
    key = os.environ.get("RTVI_VLM_API_KEY") or os.environ.get("NGC_CLI_API_KEY") or ""
    try:
        result = run()
    except (EndToEndError, PreflightError, RTVLMServiceError, OSError, ValueError) as error:
        message = str(error).replace(key, "[REDACTED]") if key else str(error)
        print(f"FAIL: {message}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
