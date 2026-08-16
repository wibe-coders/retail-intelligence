"""Framework-independent validation and serialization for domain contracts."""

from __future__ import annotations

import json
import math
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, TypeVar


_MODELS: dict[str, type[DomainModel]] = {}
_ENUMS: dict[str, type[Enum]] = {}
Model = TypeVar("Model", bound="DomainModel")


def register_model(model: type[Model]) -> type[Model]:
    """Register a domain model as an allowed serialization type."""

    name = f"{model.__module__}.{model.__qualname__}"
    _MODELS[name] = model
    model._serialization_name = name
    return model


def register_enum(enum: type[Enum]) -> type[Enum]:
    _ENUMS[f"{enum.__module__}.{enum.__qualname__}"] = enum
    return enum


class DomainModel:
    """Canonical JSON serialization shared by immutable domain models."""

    _serialization_name: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:
        return _encode(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls: type[Model], value: dict[str, Any]) -> Model:
        decoded = _decode(value)
        if not isinstance(decoded, cls):
            raise ValueError(f"serialized value is not a {cls.__name__}")
        return decoded

    @classmethod
    def from_json(cls: type[Model], value: str) -> Model:
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise ValueError("serialized domain model must be a JSON object")
        return cls.from_dict(decoded)


def require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def validate_confidence(value: float | None) -> None:
    if value is not None and (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError("confidence must be between 0 and 1 inclusive")


def require_non_negative_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def require_text_tuple(values: tuple[str, ...], name: str) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError(f"{name} must be a non-empty tuple")
    for value in values:
        require_text(value, name)


def _encode(value: Any) -> Any:
    if isinstance(value, DomainModel) and is_dataclass(value):
        return {
            "__type__": value._serialization_name,
            **{field.name: _encode(getattr(value, field.name)) for field in fields(value)},
        }
    if isinstance(value, Enum):
        return {
            "__enum__": f"{type(value).__module__}.{type(value).__qualname__}",
            "value": value.value,
        }
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat().replace("+00:00", "Z")}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_decode(item) for item in value)
    if not isinstance(value, dict):
        return value
    if set(value) == {"__datetime__"}:
        return datetime.fromisoformat(value["__datetime__"].replace("Z", "+00:00"))
    if set(value) == {"__enum__", "value"}:
        enum = _ENUMS.get(value["__enum__"])
        if enum is None:
            raise ValueError("unknown domain enum type")
        return enum(value["value"])
    type_name = value.get("__type__")
    if not isinstance(type_name, str) or type_name not in _MODELS:
        raise ValueError("unknown or missing domain model type")
    model = _MODELS[type_name]
    expected = {field.name for field in fields(model)}
    supplied = set(value) - {"__type__"}
    if supplied != expected:
        raise ValueError("serialized fields do not match the domain model")
    return model(**{name: _decode(value[name]) for name in expected})
