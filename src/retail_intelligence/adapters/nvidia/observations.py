"""Normalize sanitized RT-CV and RT-VLM responses at the adapter boundary."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlsplit

from ...domain.intelligence import (
    EvidenceLink,
    IntelligenceContext,
    Observation,
    ObservationKind,
    PipelineProvenance,
)
from ...domain.media import FrameRange, RetentionClass, SourceReference, TimeRange


class NormalizationError(ValueError):
    """A vendor response could not be normalized by the named stage."""

    def __init__(self, stage: str, detail: str) -> None:
        self.stage = stage
        super().__init__(f"{stage} normalization failed: {detail}")


@dataclass(frozen=True, slots=True)
class ObservationEnvelopeDTO:
    source: SourceReference
    evidence: EvidenceLink
    provenance: PipelineProvenance
    created_at: datetime
    retention_class: RetentionClass
    payload_reference: str


@dataclass(frozen=True, slots=True)
class RTCVDetectionDTO:
    detection_id: str
    detector_class: str
    confidence: float | None
    box: tuple[float, float, float, float]
    track_id: str | None


@dataclass(frozen=True, slots=True)
class RTCVResponseDTO:
    envelope: ObservationEnvelopeDTO
    detections: tuple[RTCVDetectionDTO, ...]


@dataclass(frozen=True, slots=True)
class RTVLMCaptionDTO:
    caption_id: str
    text: str
    confidence: float | None


@dataclass(frozen=True, slots=True)
class RTVLMResponseDTO:
    envelope: ObservationEnvelopeDTO
    caption: RTVLMCaptionDTO


def normalize_rt_cv(payload: dict[str, Any]) -> tuple[Observation, ...]:
    """Convert one recorded RT-CV response into box and track observations."""
    dto = _at_stage("rt-cv", lambda: _parse_rt_cv(payload))
    observations: list[Observation] = []
    for detection in dto.detections:
        value = _structured_value(detection)
        observations.append(_observation(
            detection.detection_id, ObservationKind.BOX, value, dto.envelope, detection.confidence
        ))
        if detection.track_id is not None:
            observations.append(_observation(
                f"{detection.detection_id}:track",
                ObservationKind.TRACK,
                value,
                dto.envelope,
                detection.confidence,
            ))
    return tuple(observations)


def normalize_rt_vlm(payload: dict[str, Any]) -> tuple[Observation, ...]:
    """Convert one recorded RT-VLM response into a caption observation."""
    dto = _at_stage("rt-vlm", lambda: _parse_rt_vlm(payload))
    caption = dto.caption
    return (_observation(
        caption.caption_id,
        ObservationKind.CAPTION,
        caption.text,
        dto.envelope,
        caption.confidence,
    ),)


def _parse_rt_cv(payload: dict[str, Any]) -> RTCVResponseDTO:
    envelope = _parse_envelope(payload)
    raw_detections = _required(payload, "detections", list)
    detections = tuple(_parse_detection(item) for item in raw_detections)
    return RTCVResponseDTO(envelope, detections)


def _parse_detection(value: Any) -> RTCVDetectionDTO:
    if not isinstance(value, dict):
        raise ValueError("each detection must be an object")
    raw_box = _required(value, "box", list)
    if len(raw_box) != 4 or any(not _finite_number(item) for item in raw_box):
        raise ValueError("detection box must contain four finite numbers")
    box = tuple(float(item) for item in raw_box)
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("detection box must have positive width and height")
    return RTCVDetectionDTO(
        _text(value, "id"),
        _text(value, "class"),
        _confidence(value.get("confidence")),
        box,  # type: ignore[arg-type]
        _optional_text(value.get("track_id"), "track_id"),
    )


def _parse_rt_vlm(payload: dict[str, Any]) -> RTVLMResponseDTO:
    envelope = _parse_envelope(payload)
    caption = _required(payload, "caption", dict)
    return RTVLMResponseDTO(envelope, RTVLMCaptionDTO(
        _text(caption, "id"), _text(caption, "text"), _confidence(caption.get("confidence"))
    ))


def _parse_envelope(payload: dict[str, Any]) -> ObservationEnvelopeDTO:
    if not isinstance(payload, dict):
        raise ValueError("response must be an object")
    source_value = _required(payload, "source", dict)
    source = SourceReference(
        _text(source_value, "store_id"),
        _text(source_value, "camera_id"),
        _text(source_value, "recording_id"),
    )
    window = _required(payload, "window", dict)
    time_range = TimeRange(_timestamp(window, "start"), _timestamp(window, "end"))
    frame_range = FrameRange(_integer(window, "frame_start"), _integer(window, "frame_end"))
    evidence = EvidenceLink(
        source,
        _text(window, "id"),
        time_range,
        frame_range,
        _safe_media_locator(_text(window, "media_locator")),
    )
    model = _required(payload, "model", dict)
    configuration = _required(payload, "configuration", dict)
    configuration_values = _required(configuration, "values", dict)
    provenance = PipelineProvenance(
        _text(model, "name"),
        _text(model, "version"),
        _text(configuration, "id"),
        _safe_configuration(configuration_values),
        _text(payload, "run_id"),
    )
    payload_reference = _safe_payload_reference(_text(payload, "payload_reference"))
    return ObservationEnvelopeDTO(
        source,
        evidence,
        provenance,
        _timestamp(payload, "created_at"),
        RetentionClass(_text(payload, "retention_class")),
        payload_reference,
    )


def _observation(
    observation_id: str,
    kind: ObservationKind,
    value: str,
    envelope: ObservationEnvelopeDTO,
    confidence: float | None,
) -> Observation:
    context = IntelligenceContext(
        envelope.source,
        envelope.provenance,
        (envelope.evidence,),
        confidence,
        envelope.created_at,
        envelope.retention_class,
    )
    return Observation(observation_id, kind, value, context, envelope.payload_reference)


def _structured_value(detection: RTCVDetectionDTO) -> str:
    return json.dumps({
        "box": detection.box,
        "class": detection.detector_class,
        "track_id": detection.track_id,
    }, separators=(",", ":"), sort_keys=True)


def _safe_payload_reference(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "vendor-output" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("payload_reference must be a query-free vendor-output URI")
    if parsed.username or parsed.password:
        raise ValueError("payload_reference cannot contain credentials")
    return value


def _safe_media_locator(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "media" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("media_locator must be a query-free media URI")
    if parsed.username or parsed.password:
        raise ValueError("media_locator cannot contain credentials")
    return value


def _safe_configuration(values: dict[Any, Any]) -> tuple[tuple[str, str], ...]:
    configuration = []
    for raw_key, raw_value in values.items():
        key = _plain_text(raw_key, "configuration key")
        value = _plain_text(raw_value, "configuration value")
        if _configuration_key_is_safe(key):
            configuration.append((key, value))
    return tuple(sorted(configuration))


def _configuration_key_is_safe(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    secret_markers = ("credential", "password", "secret", "signed_url", "auth_token", "api_key")
    if any(marker in normalized for marker in secret_markers):
        return False
    prompt_markers = ("prompt", "instruction", "messages")
    safe_metadata_suffixes = ("_id", "_revision", "_version", "_digest", "_hash")
    return not any(marker in normalized for marker in prompt_markers) or normalized.endswith(
        safe_metadata_suffixes
    )


def _at_stage(stage: str, operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except NormalizationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise NormalizationError(stage, str(error)) from error


def _required(value: dict[str, Any], key: str, expected: type) -> Any:
    result = value.get(key)
    if not isinstance(result, expected):
        raise ValueError(f"{key} must be a {expected.__name__}")
    return result


def _text(value: dict[str, Any], key: str) -> str:
    return _plain_text(value.get(key), key)


def _plain_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _optional_text(value: Any, name: str) -> str | None:
    return None if value is None else _plain_text(value, name)


def _integer(value: dict[str, Any], key: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise ValueError(f"{key} must be an integer")
    return result


def _timestamp(value: dict[str, Any], key: str) -> datetime:
    raw = _text(value, key)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{key} must be an ISO-8601 timestamp") from error


def _confidence(value: Any) -> float | None:
    if value is None:
        return None
    if not _finite_number(value) or not 0 <= value <= 1:
        raise ValueError("confidence must be between 0 and 1")
    return float(value)


def _finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


__all__ = [
    "NormalizationError",
    "ObservationEnvelopeDTO",
    "RTCVDetectionDTO",
    "RTCVResponseDTO",
    "RTVLMCaptionDTO",
    "RTVLMResponseDTO",
    "normalize_rt_cv",
    "normalize_rt_vlm",
]
