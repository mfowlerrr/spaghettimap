"""Tests for custom JMESPath functions."""

from __future__ import annotations

import jmespath.functions
import pytest
from pydantic import BaseModel

from spaghettimap import FieldMappingError, MappingConfig, Mapper
from tests.conftest import CustomFunctions, SourceUser


class TestCustomJmespathFunctions:
    def test_custom_upper_function(self, sample_user, custom_fn):
        class T(BaseModel):
            upper_name: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=T,
                schema={"upper_name": "upper(first_name)"},
                custom_functions=custom_fn,
            )
        )
        assert mapper.map(sample_user, T).upper_name == "JANE"

    def test_custom_concat_function(self, sample_user, custom_fn):
        class T(BaseModel):
            name: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=T,
                schema={"name": "concat(first_name, last_name)"},
                custom_functions=custom_fn,
            )
        )
        assert mapper.map(sample_user, T).name == "JaneDoe"

    def test_custom_double_function(self, sample_user, custom_fn):
        class T(BaseModel):
            double_score: float

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=T,
                schema={"double_score": "double(score)"},
                custom_functions=custom_fn,
            )
        )
        assert mapper.map(sample_user, T).double_score == pytest.approx(175.0)

    def test_custom_and_builtin_functions_together(self, sample_user, custom_fn):
        class T(BaseModel):
            upper_name: str
            tag_count: int

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=T,
                schema={"upper_name": "upper(first_name)", "tag_count": "length(tags)"},
                custom_functions=custom_fn,
            )
        )
        result = mapper.map(sample_user, T)
        assert result.upper_name == "JANE"
        assert result.tag_count == 2


# ---------------------------------------------------------------------------
# Shared helpers for error tests
# ---------------------------------------------------------------------------


class _SimpleSource(BaseModel):
    name: str
    age: int


class _SimpleTarget(BaseModel):
    result: str


def _mapper_with(expression: str, custom_functions=None) -> Mapper:
    mapper = Mapper()
    mapper.add_config(
        MappingConfig(
            from_type=_SimpleSource,
            to_type=_SimpleTarget,
            schema={"result": expression},
            custom_functions=custom_functions,
        )
    )
    return mapper


_SOURCE = _SimpleSource(name="test", age=42)


class TestCustomFunctionErrors:
    """Custom function failures must surface as FieldMappingError."""

    def test_function_raises_internally_wraps_as_field_mapping_error(self):
        """RuntimeError inside _func_* body → FieldMappingError."""

        class BoomFunctions(jmespath.functions.Functions):
            @jmespath.functions.signature({"types": ["string"]})
            def _func_boom(self, value: str) -> str:
                raise RuntimeError("internal boom")

        with pytest.raises(FieldMappingError, match="internal boom"):
            _mapper_with("boom(name)", BoomFunctions()).map(_SOURCE, _SimpleTarget)

    def test_function_raises_internally_preserves_original_cause(self):
        """The original RuntimeError is available as __cause__."""

        class BoomFunctions(jmespath.functions.Functions):
            @jmespath.functions.signature({"types": ["string"]})
            def _func_boom(self, value: str) -> str:
                raise RuntimeError("cause me")

        with pytest.raises(FieldMappingError) as exc_info:
            _mapper_with("boom(name)", BoomFunctions()).map(_SOURCE, _SimpleTarget)

        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert "cause me" in str(exc_info.value.__cause__)

    def test_function_raises_internally_carries_field_name(self):
        """FieldMappingError.field is set to the target field name."""

        class BoomFunctions(jmespath.functions.Functions):
            @jmespath.functions.signature({"types": ["string"]})
            def _func_boom(self, value: str) -> str:
                raise RuntimeError("boom")

        with pytest.raises(FieldMappingError) as exc_info:
            _mapper_with("boom(name)", BoomFunctions()).map(_SOURCE, _SimpleTarget)

        assert exc_info.value.field == "result"

    def test_wrong_argument_type_raises_field_mapping_error(self):
        """Passing an int to a string-typed custom function → FieldMappingError."""

        class UpperFunctions(jmespath.functions.Functions):
            @jmespath.functions.signature({"types": ["string"]})
            def _func_upper(self, value: str) -> str:
                return value.upper()

        # age is an int; upper() expects a string
        with pytest.raises(FieldMappingError, match="invalid type"):
            _mapper_with("upper(age)", UpperFunctions()).map(_SOURCE, _SimpleTarget)

    def test_wrong_argument_count_raises_field_mapping_error(self):
        """Calling a 2-arg function with 1 arg → FieldMappingError."""

        class ConcatFunctions(jmespath.functions.Functions):
            @jmespath.functions.signature({"types": ["string"]}, {"types": ["string"]})
            def _func_concat(self, a: str, b: str) -> str:
                return a + b

        with pytest.raises(FieldMappingError, match="Expected 2 arguments"):
            _mapper_with("concat(name)", ConcatFunctions()).map(_SOURCE, _SimpleTarget)

    def test_unknown_function_name_raises_field_mapping_error(self):
        """Calling a function not defined on the Functions instance → FieldMappingError."""
        with pytest.raises(FieldMappingError, match="Unknown function: nonexistent"):
            _mapper_with("nonexistent(name)", CustomFunctions()).map(
                _SOURCE, _SimpleTarget
            )

    def test_custom_function_used_without_registering_raises_field_mapping_error(self):
        """
        Using a custom-function expression with no custom_functions registered
        falls back to jmespath's built-in resolver, which raises FieldMappingError
        for any unknown function name.
        """
        # 'upper' is not a built-in jmespath function
        with pytest.raises(FieldMappingError, match="Unknown function: upper"):
            _mapper_with("upper(name)", custom_functions=None).map(
                _SOURCE, _SimpleTarget
            )

    def test_custom_function_error_message_contains_expression(self):
        """The FieldMappingError message includes the failing JMESPath expression."""

        class BoomFunctions(jmespath.functions.Functions):
            @jmespath.functions.signature({"types": ["string"]})
            def _func_boom(self, value: str) -> str:
                raise RuntimeError("boom")

        with pytest.raises(FieldMappingError) as exc_info:
            _mapper_with("boom(name)", BoomFunctions()).map(_SOURCE, _SimpleTarget)

        assert "result" in str(exc_info.value)
