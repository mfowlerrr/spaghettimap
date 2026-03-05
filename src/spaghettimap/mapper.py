"""Mapper class and internal evaluation helpers."""

from __future__ import annotations

from typing import Any, TypeVar, cast

import jmespath
import jmespath.exceptions
import jmespath.functions
from pydantic import BaseModel, ValidationError

from .config import FieldMapping, MappingConfig, _is_basemodel_subclass
from .exceptions import ConfigurationError, FieldMappingError, MappingError

T = TypeVar("T", bound=BaseModel)


class Mapper:
    """
    Holds one or more :class:`MappingConfig` objects and performs pydantic
    model-to-model conversions using JMESPath.

    Usage
    -----
    ::

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceModel,
                to_type=TargetModel,
                schema={
                    "name": "firstName",
                    "email": "contact.email",
                    "tag_count": "length(tags)",
                    "upper_name": {"expression": "firstName", "transform": str.upper},
                    "computed": lambda d: d["x"] + d["y"],
                },
            )
        )
        result: TargetModel = mapper.map(source_instance, TargetModel)
    """

    def __init__(self) -> None:
        # Keyed by (from_type, to_type) pairs for O(1) lookup.
        self._configs: dict[tuple[type[BaseModel], type[BaseModel]], MappingConfig] = {}

    # ------------------------------------------------------------------
    # Config management
    # ------------------------------------------------------------------

    def add_config(self, config: MappingConfig) -> None:
        """
        Register a :class:`MappingConfig`.

        If a config already exists for the same ``(from_type, to_type)`` pair
        it is silently replaced.

        Raises
        ------
        ConfigurationError
            If *config* is not a :class:`MappingConfig` instance.
        """
        if not isinstance(config, MappingConfig):
            raise ConfigurationError(
                f"Expected a MappingConfig instance, got {type(config).__name__!r}"
            )
        self._configs[(config.from_type, config.to_type)] = config

    def get_config(
        self, from_type: type[BaseModel], to_type: type[BaseModel]
    ) -> MappingConfig | None:
        """Return the registered config for *from_type* → *to_type*, or ``None``."""
        return self._configs.get((from_type, to_type))

    def _resolve_config(
        self, from_type: type[BaseModel], to_type: type[BaseModel]
    ) -> MappingConfig | None:
        """Return config for *from_type*→*to_type*, allowing BaseModel ancestry fallback."""
        config = self.get_config(from_type, to_type)
        if config is not None:
            return config

        for base in from_type.__mro__[1:]:
            if not _is_basemodel_subclass(base):
                continue
            inherited = self.get_config(cast(type[BaseModel], base), to_type)
            if inherited is not None:
                return inherited
        return None

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def map(self, source: BaseModel, to_type: type[T]) -> T:
        """
        Map *source* to a validated instance of *to_type*.

        Raises
        ------
        ConfigurationError
            If *source* is not a BaseModel instance, *to_type* is not a
            BaseModel subclass, or no config is registered for the pair.
        FieldMappingError
            If evaluating a field expression or transform raises an exception.
        MappingError
            If pydantic validation of the constructed target model fails.
        """
        if not isinstance(source, BaseModel):
            raise ConfigurationError(
                f"'source' must be a pydantic BaseModel instance, got {type(source).__name__!r}"
            )
        if not _is_basemodel_subclass(to_type):
            raise ConfigurationError(
                f"'to_type' must be a pydantic BaseModel subclass, got {to_type!r}"
            )

        config = self._resolve_config(type(source), to_type)
        if config is None:
            raise ConfigurationError(
                f"No mapping config registered for {type(source).__name__!r} → {to_type.__name__!r}. "
                f"Call add_config() with a MappingConfig for this pair first."
            )

        # Serialise to a plain dict; nested BaseModel instances become dicts.
        source_dict: dict[str, Any] = source.model_dump(mode="python")

        compiled_expressions = config._compiled_expressions
        result: dict[str, Any] = {
            field: _evaluate_field_mapping(
                field,
                mapping,
                source_dict,
                compiled_expressions.get(field),
                config._jmespath_options,
            )
            for field, mapping in config.schema.items()
        }

        if config.passthrough:
            for field_name in config._target_field_names:
                if field_name not in result and field_name in source_dict:
                    result[field_name] = source_dict[field_name]

        try:
            return to_type.model_validate(result)
        except ValidationError as exc:
            raise MappingError(
                f"Pydantic validation failed while constructing {to_type.__name__!r} "
                f"from mapped data: {exc}"
            ) from exc

    def map_many(self, sources: list[BaseModel], to_type: type[T]) -> list[T]:
        """
        Map a list of source instances to a list of *to_type* instances.

        Raises
        ------
        ConfigurationError
            If *sources* is not a list.
        """
        if not isinstance(sources, list):
            raise ConfigurationError(
                f"'sources' must be a list, got {type(sources).__name__!r}"
            )
        return [self.map(source, to_type) for source in sources]

    def __repr__(self) -> str:
        pairs = [f"{f.__name__!r}→{t.__name__!r}" for f, t in self._configs]
        return f"Mapper(configs=[{', '.join(pairs)}])"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _evaluate_field_mapping(
    field_name: str,
    mapping: FieldMapping,
    source_dict: dict[str, Any],
    compiled_expression: Any | None,
    jmespath_options: jmespath.Options | None,
) -> Any:
    """Evaluate a single field mapping against *source_dict*."""
    try:
        if isinstance(mapping, str):
            return _eval_jmespath(
                field_name,
                mapping,
                source_dict,
                jmespath_options,
                compiled_expression,
            )

        if callable(mapping):
            return mapping(source_dict)

        if isinstance(mapping, dict):
            expr = mapping["expression"]
            value = (
                _eval_jmespath(
                    field_name,
                    expr,
                    source_dict,
                    jmespath_options,
                    compiled_expression,
                )
                if isinstance(expr, str)
                else expr(source_dict)
            )
            transform = mapping.get("transform")
            return transform(value) if transform is not None else value

        raise FieldMappingError(
            field_name, f"Unsupported mapping type {type(mapping).__name__!r}"
        )

    except FieldMappingError:
        raise
    except Exception as exc:
        raise FieldMappingError(field_name, str(exc), source_exception=exc) from exc


def _eval_jmespath(
    field_name: str,
    expression: str,
    source_dict: dict[str, Any],
    options: jmespath.Options | None,
    compiled_expression: Any | None = None,
) -> Any:
    """Compile and search a JMESPath expression with clear error messaging."""
    try:
        compiled = (
            compiled_expression
            if compiled_expression is not None
            else jmespath.compile(expression)
        )
    except jmespath.exceptions.JMESPathError as exc:
        raise FieldMappingError(
            field_name,
            f"Invalid JMESPath expression {expression!r}: {exc}",
            source_exception=exc,
        ) from exc

    try:
        if options is None:
            return compiled.search(source_dict)
        return compiled.search(source_dict, options=options)
    except jmespath.exceptions.JMESPathError as exc:
        raise FieldMappingError(
            field_name,
            f"JMESPath evaluation error for expression {expression!r}: {exc}",
            source_exception=exc,
        ) from exc
