"""Tests for MappingConfig and Mapper config management."""

from __future__ import annotations

import pytest

from jmespath_mapper import ConfigurationError, MappingConfig, Mapper
from tests.conftest import SourceProduct, SourceUser, TargetProduct, TargetUser


class TestMappingConfigValidation:
    def test_valid_config_creates_successfully(self):
        config = MappingConfig(
            from_type=SourceUser,
            to_type=TargetUser,
            schema={"email": "contact.email"},
        )
        assert config.from_type is SourceUser
        assert config.to_type is TargetUser

    def test_from_type_not_basemodel_raises(self):
        with pytest.raises(ConfigurationError, match="from_type"):
            MappingConfig(from_type=dict, to_type=TargetUser, schema={})  # type: ignore

    def test_to_type_not_basemodel_raises(self):
        with pytest.raises(ConfigurationError, match="to_type"):
            MappingConfig(from_type=SourceUser, to_type=str, schema={})  # type: ignore

    def test_schema_not_dict_raises(self):
        with pytest.raises(ConfigurationError, match="schema"):
            MappingConfig(from_type=SourceUser, to_type=TargetUser, schema="bad")  # type: ignore

    def test_schema_key_not_string_raises(self):
        with pytest.raises(ConfigurationError, match="keys must be strings"):
            MappingConfig(
                from_type=SourceUser,
                to_type=TargetUser,
                schema={1: "age"},  # type: ignore
            )

    def test_schema_value_invalid_type_raises(self):
        with pytest.raises(ConfigurationError, match="str, callable, or dict"):
            MappingConfig(
                from_type=SourceUser,
                to_type=TargetUser,
                schema={"age": 42},  # type: ignore
            )

    def test_schema_dict_missing_expression_raises(self):
        with pytest.raises(ConfigurationError, match="'expression' key"):
            MappingConfig(
                from_type=SourceUser,
                to_type=TargetUser,
                schema={"age": {"transform": str.upper}},
            )

    def test_schema_dict_expression_bad_type_raises(self):
        with pytest.raises(ConfigurationError, match="str or callable"):
            MappingConfig(
                from_type=SourceUser,
                to_type=TargetUser,
                schema={"age": {"expression": 99}},  # type: ignore
            )

    def test_schema_dict_transform_not_callable_raises(self):
        with pytest.raises(ConfigurationError, match="'transform'.*callable"):
            MappingConfig(
                from_type=SourceUser,
                to_type=TargetUser,
                schema={"age": {"expression": "age", "transform": "not_callable"}},  # type: ignore
            )

    def test_invalid_custom_functions_raises(self):
        with pytest.raises(ConfigurationError, match="custom_functions"):
            MappingConfig(
                from_type=SourceUser,
                to_type=TargetUser,
                schema={"age": "age"},
                custom_functions="not_a_functions_instance",  # type: ignore
            )

    def test_empty_schema_is_valid(self):
        config = MappingConfig(from_type=SourceUser, to_type=TargetUser, schema={})
        assert config.schema == {}

    def test_repr_contains_type_names(self):
        config = MappingConfig(
            from_type=SourceUser, to_type=TargetUser, schema={"age": "age"}
        )
        r = repr(config)
        assert "SourceUser" in r
        assert "TargetUser" in r


class TestMapperConfigManagement:
    def test_add_config_then_get_config(self):
        mapper = Mapper()
        config = MappingConfig(from_type=SourceUser, to_type=TargetUser, schema={})
        mapper.add_config(config)
        assert mapper.get_config(SourceUser, TargetUser) is config

    def test_add_config_replaces_existing(self):
        mapper = Mapper()
        config1 = MappingConfig(from_type=SourceUser, to_type=TargetUser, schema={"age": "age"})
        config2 = MappingConfig(from_type=SourceUser, to_type=TargetUser, schema={"email": "contact.email"})
        mapper.add_config(config1)
        mapper.add_config(config2)
        assert mapper.get_config(SourceUser, TargetUser) is config2

    def test_get_config_returns_none_for_missing(self):
        mapper = Mapper()
        assert mapper.get_config(SourceUser, TargetUser) is None

    def test_add_non_config_raises(self):
        mapper = Mapper()
        with pytest.raises(ConfigurationError, match="MappingConfig"):
            mapper.add_config("not a config")  # type: ignore

    def test_multiple_configs_coexist(self):
        mapper = Mapper()
        c1 = MappingConfig(from_type=SourceUser, to_type=TargetUser, schema={})
        c2 = MappingConfig(from_type=SourceProduct, to_type=TargetProduct, schema={})
        mapper.add_config(c1)
        mapper.add_config(c2)
        assert mapper.get_config(SourceUser, TargetUser) is c1
        assert mapper.get_config(SourceProduct, TargetProduct) is c2

    def test_repr_contains_config_pairs(self):
        mapper = Mapper()
        mapper.add_config(MappingConfig(from_type=SourceUser, to_type=TargetUser, schema={}))
        r = repr(mapper)
        assert "SourceUser" in r
        assert "TargetUser" in r
