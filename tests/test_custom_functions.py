"""Tests for custom JMESPath functions."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from jmespath_mapper import MappingConfig, Mapper
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
