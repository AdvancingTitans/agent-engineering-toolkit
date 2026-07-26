"""Dependency-free validation for the shipped Evidence Atlas JSON Schemas."""

from __future__ import annotations

import json
import re
import sysconfig
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any, Mapping


class AtlasSchemaError(ValueError):
    """A document does not conform to a shipped Atlas JSON Schema."""


def validate_schema(instance: Any, schema_name: str) -> None:
    """Validate one document against the supported Draft 2020-12 subset."""
    root = _schema_root()
    schema = _load_schema(root / schema_name)
    _validate(instance, schema, schema, root / schema_name, "$")


def _schema_root() -> Path:
    source = Path(__file__).resolve().parents[3] / "schemas" / "evidence-atlas" / "v1"
    installed = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "aet"
        / "schemas"
        / "evidence-atlas"
        / "v1"
    )
    distribution_root = None
    try:
        package = distribution("agent-engineering-toolkit")
        for entry in package.files or ():
            if str(entry).endswith(
                "share/aet/schemas/evidence-atlas/v1/graph.schema.json"
            ):
                distribution_root = Path(package.locate_file(entry)).parent
                break
    except PackageNotFoundError:
        pass
    for candidate in (source, installed, distribution_root):
        if candidate is None:
            continue
        if (candidate / "graph.schema.json").is_file():
            return candidate
    raise AtlasSchemaError("packaged Evidence Atlas schemas are unavailable")


def _load_schema(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AtlasSchemaError(f"cannot load schema {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise AtlasSchemaError(f"schema {path.name} must be an object")
    return value


def _validate(
    instance: Any,
    schema: Mapping[str, Any],
    root_schema: Mapping[str, Any],
    schema_path: Path,
    path: str,
) -> None:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        target, target_root, target_path = _resolve_ref(
            reference, root_schema, schema_path
        )
        _validate(instance, target, target_root, target_path, path)
        return
    if "const" in schema and instance != schema["const"]:
        _error(path, f"must equal {schema['const']!r}")
    enum = schema.get("enum")
    if isinstance(enum, list) and instance not in enum:
        _error(path, f"must be one of {enum!r}")
    if "not" in schema:
        try:
            _validate(instance, schema["not"], root_schema, schema_path, path)
        except AtlasSchemaError:
            pass
        else:
            _error(path, "matches a forbidden schema")
    if "oneOf" in schema:
        matches = 0
        for candidate in schema["oneOf"]:
            try:
                _validate(instance, candidate, root_schema, schema_path, path)
            except AtlasSchemaError:
                continue
            matches += 1
        if matches != 1:
            _error(path, f"must match exactly one schema, matched {matches}")

    expected = schema.get("type")
    if expected is not None and not _matches_type(instance, expected):
        _error(path, f"must be {expected}")
    if isinstance(instance, dict):
        _validate_object(instance, schema, root_schema, schema_path, path)
    elif isinstance(instance, list):
        _validate_array(instance, schema, root_schema, schema_path, path)
    elif isinstance(instance, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        if isinstance(minimum, int) and len(instance) < minimum:
            _error(path, f"must have at least {minimum} characters")
        if isinstance(maximum, int) and len(instance) > maximum:
            _error(path, f"must have at most {maximum} characters")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, instance) is None:
            _error(path, f"does not match pattern {pattern!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            _error(path, f"must be >= {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            _error(path, f"must be <= {schema['maximum']}")


def _validate_object(
    instance: dict[str, Any],
    schema: Mapping[str, Any],
    root_schema: Mapping[str, Any],
    schema_path: Path,
    path: str,
) -> None:
    required = schema.get("required", [])
    for key in required:
        if key not in instance:
            _error(path, f"is missing required property {key!r}")
    properties = schema.get("properties", {})
    additional = schema.get("additionalProperties", True)
    for key, value in instance.items():
        child_path = f"{path}.{key}"
        if key in properties:
            _validate(
                value,
                properties[key],
                root_schema,
                schema_path,
                child_path,
            )
        elif additional is False:
            _error(path, f"contains unexpected property {key!r}")
        elif isinstance(additional, Mapping):
            _validate(
                value,
                additional,
                root_schema,
                schema_path,
                child_path,
            )


def _validate_array(
    instance: list[Any],
    schema: Mapping[str, Any],
    root_schema: Mapping[str, Any],
    schema_path: Path,
    path: str,
) -> None:
    minimum = schema.get("minItems")
    maximum = schema.get("maxItems")
    if isinstance(minimum, int) and len(instance) < minimum:
        _error(path, f"must contain at least {minimum} items")
    if isinstance(maximum, int) and len(instance) > maximum:
        _error(path, f"must contain at most {maximum} items")
    if schema.get("uniqueItems") is True:
        serialized = [
            json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False)
            for item in instance
        ]
        if len(serialized) != len(set(serialized)):
            _error(path, "must contain unique items")
    item_schema = schema.get("items")
    if isinstance(item_schema, Mapping):
        for index, value in enumerate(instance):
            _validate(
                value,
                item_schema,
                root_schema,
                schema_path,
                f"{path}[{index}]",
            )


def _resolve_ref(
    reference: str,
    root_schema: Mapping[str, Any],
    schema_path: Path,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Path]:
    if reference.startswith("#/"):
        value: Any = root_schema
        for part in reference[2:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(value, Mapping) or key not in value:
                raise AtlasSchemaError(f"unresolved schema reference {reference}")
            value = value[key]
        if not isinstance(value, Mapping):
            raise AtlasSchemaError(f"schema reference is not an object: {reference}")
        return value, root_schema, schema_path
    if "#" in reference:
        filename, fragment = reference.split("#", 1)
    else:
        filename, fragment = reference, ""
    target_path = (schema_path.parent / filename).resolve(strict=True)
    if target_path.parent != schema_path.parent.resolve():
        raise AtlasSchemaError(f"schema reference escapes its directory: {reference}")
    target_root = _load_schema(target_path)
    if not fragment:
        return target_root, target_root, target_path
    return _resolve_ref(f"#{fragment}", target_root, target_path)


def _matches_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool),
        "null": lambda: value is None,
    }.get(expected, lambda: False)()


def _error(path: str, message: str) -> None:
    raise AtlasSchemaError(f"{path} {message}")


__all__ = ["AtlasSchemaError", "validate_schema"]
