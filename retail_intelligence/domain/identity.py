"""Deterministic, secret-safe identity for replayable pipeline work."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from ._base import require_non_negative_integer, require_text
from .media import TimeRange


_SENSITIVE_KEY_PARTS = frozenset(
    {
        "accesskey",
        "apikey",
        "authorization",
        "credential",
        "credentials",
        "password",
        "privatekey",
        "secret",
        "signature",
        "signedurl",
        "token",
    }
)
_SIGNED_QUERY_PARTS = frozenset(
    {"credential", "expires", "signature", "signedheaders", "sig", "token"}
)
_SIGNED_URL_MARKER = "<signed-url-excluded>"


def canonical_configuration_json(configuration: Mapping[str, Any] | str) -> str:
    """Return stable JSON after removing credentials and signed URL material.

    A string input is treated as a serialized JSON object, so formatting and object key order do
    not affect the result. Lists and tuples are equivalent configuration sequences.
    """

    if isinstance(configuration, str):
        try:
            configuration = json.loads(configuration)
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("configuration must be a JSON object") from error
    if not isinstance(configuration, Mapping):
        raise ValueError("configuration must be a mapping or serialized JSON object")
    canonical = _canonical_value(configuration)
    return json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class PipelineIdentity:
    """The four identity-bearing inputs shared by a pipeline run and its evidence."""

    source_checksum: str
    time_range: TimeRange
    pipeline_version: str
    configuration: Mapping[str, Any] | str = field(repr=False, compare=False)
    _configuration_json: str = field(init=False, repr=False, compare=False)
    _identity_digest: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        require_text(self.source_checksum, "source_checksum")
        require_text(self.pipeline_version, "pipeline_version")
        if not isinstance(self.time_range, TimeRange):
            raise ValueError("time_range must be a TimeRange")
        configuration_json = canonical_configuration_json(self.configuration)
        material = {
            "configuration": json.loads(configuration_json),
            "pipeline_version": self.pipeline_version,
            "source_checksum": self.source_checksum,
            "time_range": {
                "end": _utc_text(self.time_range.end),
                "start": _utc_text(self.time_range.start),
            },
        }
        object.__setattr__(self, "_configuration_json", configuration_json)
        object.__setattr__(self, "_identity_digest", _digest("pipeline-identity-v1", material))

    @property
    def configuration_id(self) -> str:
        return f"config_{_digest('configuration-v1', json.loads(self._configuration_json))}"

    @property
    def identity_digest(self) -> str:
        return self._identity_digest

    @property
    def evidence_window_id(self) -> str:
        return f"window_{_digest('evidence-window-v1', self._identity_digest)}"

    @property
    def pipeline_run_id(self) -> str:
        return f"run_{_digest('pipeline-run-v1', self._identity_digest)}"

    def observation_id(self, kind: str, sequence: int) -> str:
        """Identify one ordered normalized output within this pipeline input."""

        require_text(kind, "observation kind")
        require_non_negative_integer(sequence, "observation sequence")
        material = {"identity": self._identity_digest, "kind": kind, "sequence": sequence}
        return f"observation_{_digest('observation-v1', material)}"


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("configuration keys must be strings")
            if _is_sensitive_key(key):
                continue
            result[key] = _canonical_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and _is_signed_url(value):
            return _SIGNED_URL_MARKER
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value) if value.is_integer() else value
    raise ValueError("configuration contains an unsupported value")


def _is_sensitive_key(key: str) -> bool:
    parts = set(filter(None, re.split(r"[^a-z0-9]+", key.casefold())))
    compact = "".join(parts)
    return bool(parts & _SENSITIVE_KEY_PARTS or compact in _SENSITIVE_KEY_PARTS)


def _is_signed_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if not parsed.scheme or not parsed.netloc or not parsed.query:
        return False
    query_keys = {
        "".join(filter(str.isalnum, key.casefold())) for key, _ in parse_qsl(parsed.query)
    }
    return any(any(part in key for part in _SIGNED_QUERY_PARTS) for key in query_keys)


def _utc_text(value) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _digest(namespace: str, value: Any) -> str:
    serialized = json.dumps(
        {"namespace": namespace, "value": value},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


__all__ = ["PipelineIdentity", "canonical_configuration_json"]
