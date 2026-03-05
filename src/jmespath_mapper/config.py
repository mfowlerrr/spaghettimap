"""MappingConfig definition and schema validation."""

from __future__ import annotations

from typing import Any, Callable

import jmespath
import jmespath.exceptions
import jmespath.functions
from pydantic import BaseModel

from .exceptions import ConfigurationError

# A schema value can be:
#   - str                        → JMESPath expression
#   - Callable[[dict], Any]      → Python function receiving the source model dict
#   - dict                       → {"expression": str | Callable, "transform": Callable (optional)}
FieldMapping = str | Callable[..., Any] | dict[str, Any]


def _is_basemodel_subclass(typ: Any) -> bool:
    try:
        return isinstance(typ, type) and issubclass(typ, BaseModel)
    except TypeError:
        return False


class MappingConfig:
    """
    Configuration describing how to map from one pydantic model type to another.

    Parameters
    ----------
    from_type:
        The source pydantic ``BaseModel`` subclass.
    to_type:
        The target pydantic ``BaseModel`` subclass.
    schema:
        A mapping of *target field name* → field mapping.  Optional – if
        omitted (or ``None``), *passthrough* is automatically enabled so that
        all target fields are auto-mapped from source fields of the same name.

        Each value may be:

        * **str** – a JMESPath expression evaluated against the source model
          serialised to a plain ``dict``.
        * **Callable[[dict], Any]** – a Python callable that receives the full
          source dict and returns the field value.
        * **dict** – must contain an ``"expression"`` key (``str`` or
          ``Callable``) and an optional ``"transform"`` key (``Callable``)
          applied to the extracted value after the expression is evaluated.

    passthrough:
        When ``True``, any target field *not* covered by *schema* is
        automatically filled from the source field with the **same name**
        (if one exists).  Fields already produced by *schema* are never
        overwritten.  Defaults to ``False`` unless *schema* is omitted/``None``,
        in which case it is set to ``True`` automatically.

    custom_functions:
        An optional instance of a :class:`jmespath.functions.Functions`
        subclass that provides additional JMESPath functions available to
        *all* expressions in this config.

    Raises
    ------
    ConfigurationError
        If ``from_type`` or ``to_type`` are not pydantic ``BaseModel``
        subclasses, or if any schema value has an unsupported type.
    """

    def __init__(
        self,
        from_type: type[BaseModel],
        to_type: type[BaseModel],
        schema: dict[str, FieldMapping] | None = None,
        custom_functions: jmespath.functions.Functions | None = None,
        passthrough: bool = False,
    ) -> None:
        if not _is_basemodel_subclass(from_type):
            raise ConfigurationError(
                f"'from_type' must be a pydantic BaseModel subclass, got {from_type!r}"
            )
        if not _is_basemodel_subclass(to_type):
            raise ConfigurationError(
                f"'to_type' must be a pydantic BaseModel subclass, got {to_type!r}"
            )
        if schema is None:
            # No schema provided → enable passthrough automatically.
            schema = {}
            passthrough = True
        elif not isinstance(schema, dict):
            raise ConfigurationError(
                f"'schema' must be a dict, got {type(schema).__name__!r}"
            )

        for key, value in schema.items():
            if not isinstance(key, str):
                raise ConfigurationError(
                    f"All schema keys must be strings; got key {key!r} of type {type(key).__name__!r}"
                )
            _validate_field_mapping(key, value)

        unknown_fields = [
            field for field in schema if field not in to_type.model_fields
        ]
        if unknown_fields:
            raise ConfigurationError(
                f"Schema contains field(s) not present on target model {to_type.__name__!r}: "
                f"{unknown_fields!r}"
            )

        if custom_functions is not None and not isinstance(
            custom_functions, jmespath.functions.Functions
        ):
            raise ConfigurationError(
                "'custom_functions' must be an instance of jmespath.functions.Functions "
                f"(or a subclass), got {type(custom_functions).__name__!r}"
            )

        self.from_type = from_type
        self.to_type = to_type
        self.schema = schema
        self.passthrough = passthrough
        self.custom_functions = custom_functions
        self._target_field_names = tuple(to_type.model_fields.keys())
        self._jmespath_options = (
            jmespath.Options(custom_functions=custom_functions)
            if custom_functions is not None
            else None
        )
        self._compiled_expressions = _compile_schema_expressions(schema)

    def __repr__(self) -> str:
        return (
            f"MappingConfig("
            f"from_type={self.from_type.__name__!r}, "
            f"to_type={self.to_type.__name__!r}, "
            f"fields={list(self.schema.keys())!r}, "
            f"passthrough={self.passthrough!r})"
        )


def _validate_field_mapping(key: str, value: FieldMapping) -> None:
    """Raise ConfigurationError if *value* is not a valid field mapping."""
    if isinstance(value, (str, Callable)):  # type: ignore[arg-type]
        return
    if isinstance(value, dict):
        if "expression" not in value:
            raise ConfigurationError(
                f"Schema value for field '{key}' is a dict but is missing the required "
                f"'expression' key. Got keys: {list(value.keys())!r}"
            )
        expr = value["expression"]
        if not isinstance(expr, str) and not callable(expr):
            raise ConfigurationError(
                f"'expression' for field '{key}' must be a str or callable, "
                f"got {type(expr).__name__!r}"
            )
        transform = value.get("transform")
        if transform is not None and not callable(transform):
            raise ConfigurationError(
                f"'transform' for field '{key}' must be callable, "
                f"got {type(transform).__name__!r}"
            )
        return
    raise ConfigurationError(
        f"Schema value for field '{key}' must be a str, callable, or dict; "
        f"got {type(value).__name__!r}"
    )


def _compile_schema_expressions(schema: dict[str, FieldMapping]) -> dict[str, Any]:
    """Pre-compile all string JMESPath expressions in *schema*."""
    compiled: dict[str, Any] = {}
    for key, value in schema.items():
        if isinstance(value, str):
            compiled[key] = _compile_expression(key, value)
            continue
        if isinstance(value, dict):
            expr = value.get("expression")
            if isinstance(expr, str):
                compiled[key] = _compile_expression(key, expr)
    return compiled


def _compile_expression(field_name: str, expression: str) -> Any:
    try:
        return jmespath.compile(expression)
    except jmespath.exceptions.JMESPathError as exc:
        raise ConfigurationError(
            f"Invalid JMESPath expression for field '{field_name}': {expression!r}: {exc}"
        ) from exc
