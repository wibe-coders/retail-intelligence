"""Bounded whole-file RT-VLM client for the DGX Spark target test."""

from __future__ import annotations

import json
import re
from pathlib import Path
from time import monotonic
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from ...domain.media import Source
from ...pipelines.vertical_slice import CaptionModelResult


class RTVLMServiceError(RuntimeError):
    """A sanitized RT-VLM transport or response failure."""


RequestJSON = Callable[
    [str, str, dict[str, str], bytes | None, str | None, float],
    dict[str, Any],
]


class RTVLMFileCaptionModel:
    """Caption one bounded local file through RT-VLM and remove its uploaded copy."""

    DEFAULT_PROMPT = (
        "Describe only the visible actions and setting in this video. "
        "Do not infer identity or intent."
    )

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        prompt: str = DEFAULT_PROMPT,
        chunk_duration: int = 12,
        input_width: int = 448,
        input_height: int = 448,
        fixed_frame_count: int = 80,
        request_timeout: float = 300,
        max_upload_bytes: int = 64 * 1024 * 1024,
        requester: RequestJSON | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.path not in {"", "/"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "base_url must be an HTTP(S) origin without credentials, path, query, or fragment"
            )
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("api_key is required")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt is required")
        for value, name in (
            (chunk_duration, "chunk_duration"),
            (input_width, "input_width"),
            (input_height, "input_height"),
            (fixed_frame_count, "fixed_frame_count"),
            (max_upload_bytes, "max_upload_bytes"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(request_timeout, bool)
            or not isinstance(request_timeout, (int, float))
            or request_timeout <= 0
        ):
            raise ValueError("request_timeout must be positive")

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._prompt = prompt
        self._chunk_duration = chunk_duration
        self._input_width = input_width
        self._input_height = input_height
        self._fixed_frame_count = fixed_frame_count
        self._request_timeout = request_timeout
        self._max_upload_bytes = max_upload_bytes
        self._requester = requester or self._request_json
        self._metadata: tuple[str, str, str] | None = None

        self.call_count = 0
        self.last_latency_seconds: float | None = None
        self.last_frame_counts: tuple[int, ...] = ()
        self.last_upload_deleted = False

    def ready(self) -> None:
        self._call("GET", "/v1/health/ready", authenticated=False, timeout=30)

    def metadata(self) -> tuple[str, str, str]:
        """Return exact model identifier, service release, and API version."""
        if self._metadata is None:
            models = self._call("GET", "/v1/models")
            model_id = self._model_id(models)
            version = self._call("GET", "/v1/version")
            release = version.get("release")
            api_version = version.get("api")
            if not isinstance(release, str) or not release:
                raise RTVLMServiceError("RT-VLM version response has no release")
            if not isinstance(api_version, str) or not api_version:
                raise RTVLMServiceError("RT-VLM version response has no API version")
            self._metadata = (model_id, release, api_version)
        return self._metadata

    def caption(self, source: Source, window_id: str) -> CaptionModelResult:
        path = Path(source.media_locator)
        if not path.is_file():
            raise ValueError("source media_locator must name a local file")
        size = path.stat().st_size
        if size == 0:
            raise ValueError("target-test upload must not be empty")
        if size > self._max_upload_bytes:
            raise ValueError(
                f"target-test upload exceeds {self._max_upload_bytes} byte limit"
            )
        if not re.fullmatch(r"[A-Za-z0-9_. -]+", path.name):
            raise ValueError("source filename contains unsupported characters")

        model_id, release, _ = self.metadata()
        upload_id: str | None = None
        self.call_count += 1
        self.last_upload_deleted = False
        try:
            upload = self._upload(path)
            upload_id = self._uuid_field(upload, "id", "upload")
            request_body = json.dumps(
                {
                    "id": upload_id,
                    "model": model_id,
                    "prompt": self._prompt,
                    "chunk_duration": self._chunk_duration,
                    "stream": False,
                    "num_frames_per_second_or_fixed_frames_chunk": self._fixed_frame_count,
                    "use_fps_for_chunking": False,
                    "vlm_input_width": self._input_width,
                    "vlm_input_height": self._input_height,
                },
                separators=(",", ":"),
            ).encode()

            started = monotonic()
            response = self._call(
                "POST",
                "/v1/generate_captions",
                body=request_body,
                content_type="application/json",
            )
            self.last_latency_seconds = monotonic() - started
            response_id = self._uuid_field(response, "id", "caption")
            caption, frame_counts = self._caption_text(response)
            self.last_frame_counts = frame_counts
            return CaptionModelResult(
                caption,
                model_id,
                release,
                f"vendor-output://rt-vlm/{response_id}",
            )
        finally:
            if upload_id is not None:
                deletion = self._call("DELETE", f"/v1/files/{upload_id}")
                if deletion.get("deleted") is not True:
                    raise RTVLMServiceError("RT-VLM did not confirm uploaded-file deletion")
                self.last_upload_deleted = True

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
        if content_type is not None:
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
            raise RTVLMServiceError(
                f"{method} {path} failed with HTTP {error.code}"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise RTVLMServiceError(f"{method} {path} could not reach RT-VLM") from None

        try:
            decoded = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RTVLMServiceError(f"{method} {path} returned invalid JSON") from None
        if not isinstance(decoded, dict):
            raise RTVLMServiceError(f"{method} {path} returned a non-object response")
        return decoded

    @staticmethod
    def _model_id(response: dict[str, Any]) -> str:
        data = response.get("data")
        value = data[0].get("id") if isinstance(data, list) and data else response.get("id")
        if not isinstance(value, str) or not value:
            raise RTVLMServiceError("RT-VLM models response has no model identifier")
        return value

    @staticmethod
    def _uuid_field(response: dict[str, Any], field: str, stage: str) -> str:
        value = response.get(field)
        if not isinstance(value, str):
            raise RTVLMServiceError(f"RT-VLM {stage} response has no {field}")
        try:
            UUID(value)
        except ValueError:
            raise RTVLMServiceError(
                f"RT-VLM {stage} response has an invalid {field}"
            ) from None
        return value

    @staticmethod
    def _caption_text(response: dict[str, Any]) -> tuple[str, tuple[int, ...]]:
        chunks = response.get("chunk_responses")
        if not isinstance(chunks, list):
            raise RTVLMServiceError("RT-VLM caption response has no chunk responses")

        captions = []
        frame_counts = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            content = chunk.get("content")
            if isinstance(content, str) and content.strip():
                captions.append(content.strip())
                frame_count = chunk.get("frame_count")
                if isinstance(frame_count, int) and not isinstance(frame_count, bool):
                    frame_counts.append(frame_count)
        if not captions:
            raise RTVLMServiceError("RT-VLM caption response contains no text")
        return "\n".join(captions), tuple(frame_counts)


__all__ = ["RTVLMFileCaptionModel", "RTVLMServiceError"]
