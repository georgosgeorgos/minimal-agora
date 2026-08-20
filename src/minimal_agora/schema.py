from __future__ import annotations

from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)

_PYTHON_TYPE_NAMES = {
    int: "int",
    float: "float",
    str: "str",
    bool: "bool",
    list: "list",
    dict: "dict",
}


def infer_schema(initial_state: dict[str, Any], _prefix: str = "") -> dict[str, dict[str, Any]]:
    schema: dict[str, dict[str, Any]] = {}
    for key, value in initial_state.items():
        path = f"{_prefix}{key}" if not _prefix else f"{_prefix}.{key}"
        if isinstance(value, dict):
            schema.update(infer_schema(value, path))
        else:
            entry: dict[str, Any] = {}
            for py_type, name in _PYTHON_TYPE_NAMES.items():
                if isinstance(value, py_type) and not (py_type is int and isinstance(value, bool)):
                    entry["type"] = name
                    break
            else:
                if isinstance(value, bool):
                    entry["type"] = "bool"
                elif value is not None:
                    entry["type"] = type(value).__name__
            entry["nullable"] = value is None
            schema[path] = entry
    return schema


def _flatten_delta(delta: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    pairs: list[tuple[str, Any]] = []
    for key, value in delta.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            pairs.extend(_flatten_delta(value, path))
        else:
            pairs.append((path, value))
    return pairs


def validate_state_delta(delta: dict[str, Any], schema: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    flat = _flatten_delta(delta)

    for path, value in flat:
        if path not in schema:
            errors.append(f"New field {path}: not in original state (value={value!r})")
            continue

        entry = schema[path]
        expected_type = entry.get("type")
        nullable = entry.get("nullable", False)

        if value is None and not nullable:
            errors.append(f"Field {path}: got None but field was non-None in initial state")
            continue

        if value is not None and expected_type:
            actual = type(value).__name__
            if not _type_compatible(value, expected_type):
                errors.append(f"Field {path}: expected {expected_type}, got {actual}")

    return errors


def _type_compatible(value: Any, expected: str) -> bool:
    if expected == "float" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if expected == "int" and isinstance(value, int) and not isinstance(value, bool):
        return True
    if expected == "str" and isinstance(value, str):
        return True
    if expected == "bool" and isinstance(value, bool):
        return True
    if expected == "list" and isinstance(value, list):
        return True
    return expected == "dict" and isinstance(value, dict)
