#!/usr/bin/env python3
"""Run the approved video through a standalone RT-VLM service twice.

This is a target-only hardware/API gate. It deliberately stops before application
ingest, indexing, retrieval, or question answering.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))

from scripts.preflight_smoke_video import (  # noqa: E402
    EXPECTED_SHA256,
    FIXTURE_PATH,
    SELECTED_FRAME_COUNT,
    PreflightError,
    preflight,
)
from retail_intelligence.inference_budget import evaluate_inference_budget  # noqa: E402


DEFAULT_BASE_URL = "http://localhost:8018"
EXPECTED_FRAME_COUNT = SELECTED_FRAME_COUNT
INPUT_HEIGHT = 448
INPUT_WIDTH = 448
VISUAL_TOKENS = evaluate_inference_budget(
    INPUT_WIDTH, INPUT_HEIGHT, EXPECTED_FRAME_COUNT
).visual_tokens
CHUNK_DURATION_SECONDS = 12
PROMPT = (
    "Describe only the visible actions and setting in this video. "
    "Do not infer identity or intent."
)


class SmokeTestError(RuntimeError):
    """The live service did not satisfy the bounded smoke-test contract."""


RequestJSON = Callable[
    [str, str, dict[str, str], bytes | None, str | None, float],
    dict[str, Any],
]


@dataclass(frozen=True, slots=True)
class CaptionRun:
    latency_seconds: float
    frame_count: int
    start_time: float
    end_time: float
    caption: str


class RTVLMSmokeClient:
    """Exercise one standalone RT-VLM origin without retaining its upload."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        request_timeout: float = 300,
        requester: RequestJSON | None = None,
    ) -> None:
        self._base_url = validate_base_url(base_url)
        if not api_key:
            raise ValueError("api_key is required")
        if (
            isinstance(request_timeout, bool)
            or not isinstance(request_timeout, (int, float))
            or request_timeout <= 0
        ):
            raise ValueError("request_timeout must be positive")
        self._api_key = api_key
        self._request_timeout = request_timeout
        self._requester = requester or self._request_json

    def ready(self) -> None:
        self._call("GET", "/v1/health/ready", authenticated=False, timeout=30)

    def metadata(self) -> dict[str, str]:
        models = self._call("GET", "/v1/models")
        model_id = model_identifier(models)
        version = self._call("GET", "/v1/version")
        release = required_string(version, "release", "version")
        api_version = required_string(version, "api", "version")
        return {"model": model_id, "release": release, "api": api_version}

    def caption_twice(self, path: Path, model_id: str) -> tuple[CaptionRun, CaptionRun]:
        upload_id = required_string(self._upload(path), "id", "upload")
        try:
            runs = (self._caption(upload_id, model_id), self._caption(upload_id, model_id))
        except Exception as inference_error:
            self._cleanup_after_failure(upload_id, inference_error)
            raise

        self._delete_upload(upload_id)
        return runs

    def _cleanup_after_failure(self, upload_id: str, inference_error: Exception) -> None:
        try:
            self._delete_upload(upload_id)
        except SmokeTestError:
            raise SmokeTestError(
                "RT-VLM inference failed and uploaded-file cleanup also failed"
            ) from inference_error

    def _upload(self, path: Path) -> dict[str, Any]:
        boundary = f"retail-intelligence-{uuid4().hex}"
        prefix = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="purpose"\r\n\r\n'
            "vision\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="media_type"\r\n\r\n'
            "video\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: video/mp4\r\n\r\n"
        ).encode()
        suffix = f"\r\n--{boundary}--\r\n".encode()
        return self._call(
            "POST",
            "/v1/files",
            body=prefix + path.read_bytes() + suffix,
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def _caption(self, upload_id: str, model_id: str) -> CaptionRun:
        body = json.dumps(
            {
                "id": upload_id,
                "model": model_id,
                "prompt": PROMPT,
                "chunk_duration": CHUNK_DURATION_SECONDS,
                "stream": False,
                "num_frames_per_second_or_fixed_frames_chunk": EXPECTED_FRAME_COUNT,
                "use_fps_for_chunking": False,
                "vlm_input_width": INPUT_WIDTH,
                "vlm_input_height": INPUT_HEIGHT,
            },
            separators=(",", ":"),
        ).encode()
        started = monotonic()
        response = self._call(
            "POST",
            "/v1/generate_captions",
            body=body,
            content_type="application/json",
        )
        return parse_caption(response, monotonic() - started)

    def _delete_upload(self, upload_id: str) -> None:
        response = self._call("DELETE", f"/v1/files/{upload_id}")
        if response.get("deleted") is not True:
            raise SmokeTestError("RT-VLM did not confirm uploaded-file deletion")

    def _call(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        body: bytes | None = None,
        content_type: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return self._requester(
            method,
            path,
            headers,
            body,
            content_type,
            self._request_timeout if timeout is None else timeout,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes | None,
        content_type: str | None,
        timeout: float,
    ) -> dict[str, Any]:
        request_headers = dict(headers)
        if content_type:
            request_headers["Content-Type"] = content_type
        request = Request(
            self._base_url + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
        except HTTPError as error:
            raise SmokeTestError(
                f"{method} {path} failed with HTTP {error.code}"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise SmokeTestError(f"{method} {path} could not reach RT-VLM") from None

        try:
            decoded = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise SmokeTestError(f"{method} {path} returned invalid JSON") from None
        if not isinstance(decoded, dict):
            raise SmokeTestError(f"{method} {path} returned a non-object response")
        return decoded


def validate_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "base URL must be an HTTP(S) origin without credentials, path, query, or fragment"
        )
    return base_url.rstrip("/")


def required_string(response: dict[str, Any], field: str, stage: str) -> str:
    value = response.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SmokeTestError(f"RT-VLM {stage} response has no {field}")
    return value


def model_identifier(response: dict[str, Any]) -> str:
    data = response.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        value = data[0].get("id")
    else:
        value = response.get("id")
    if not isinstance(value, str) or not value:
        raise SmokeTestError("RT-VLM models response has no model identifier")
    return value


def parse_caption(response: dict[str, Any], latency_seconds: float) -> CaptionRun:
    chunks = response.get("chunk_responses")
    if not isinstance(chunks, list) or len(chunks) != 1 or not isinstance(chunks[0], dict):
        raise SmokeTestError("RT-VLM caption response must contain exactly one chunk")
    chunk = chunks[0]
    caption = required_string(chunk, "content", "caption")
    frame_count = chunk.get("frame_count")
    if frame_count != EXPECTED_FRAME_COUNT:
        raise SmokeTestError(
            f"RT-VLM reported {frame_count!r} frames; expected {EXPECTED_FRAME_COUNT}"
        )
    start_time = chunk.get("start_time")
    end_time = chunk.get("end_time")
    if not isinstance(start_time, (int, float)) or not isinstance(end_time, (int, float)):
        raise SmokeTestError("RT-VLM caption response has invalid timestamps")
    return CaptionRun(
        round(latency_seconds, 6),
        frame_count,
        float(start_time),
        float(end_time),
        caption.strip(),
    )


def api_key_from_environment() -> str:
    key = os.environ.get("RTVI_VLM_API_KEY") or os.environ.get("NGC_CLI_API_KEY")
    if not key:
        raise SmokeTestError("set RTVI_VLM_API_KEY or NGC_CLI_API_KEY")
    return key


def run() -> dict[str, object]:
    preflight(FIXTURE_PATH)
    client = RTVLMSmokeClient(
        os.environ.get("RTVI_VLM_BASE_URL", DEFAULT_BASE_URL),
        api_key_from_environment(),
    )
    client.ready()
    service = client.metadata()
    runs = client.caption_twice(FIXTURE_PATH, service["model"])
    return {
        "result": "PASS",
        "fixture": {
            "path": str(FIXTURE_PATH.relative_to(REPOSITORY_ROOT)),
            "sha256": EXPECTED_SHA256,
            "input_width": INPUT_WIDTH,
            "input_height": INPUT_HEIGHT,
            "reported_frames": EXPECTED_FRAME_COUNT,
            "visual_tokens": VISUAL_TOKENS,
        },
        "service": service,
        "runs": [asdict(result) for result in runs],
        "repeat_without_restart": True,
        "upload_deleted": True,
    }


def main() -> int:
    key = os.environ.get("RTVI_VLM_API_KEY") or os.environ.get("NGC_CLI_API_KEY") or ""
    try:
        result = run()
    except (OSError, ValueError, PreflightError, SmokeTestError) as error:
        message = str(error).replace(key, "[REDACTED]") if key else str(error)
        print(f"FAIL: {message}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
