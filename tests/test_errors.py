"""Tests for error handling and edge cases."""

from __future__ import annotations

from typing import Optional

import pytest
from pydantic import BaseModel, ConfigDict

from jmespath_mapper import (
    ConfigurationError,
    FieldMappingError,
    MappingConfig,
    MappingError,
    Mapper,
)
from tests.conftest import SourceUser, TargetUser


class TestErrorCases:
    def test_map_without_registered_config_raises(self, sample_user):
        with pytest.raises(ConfigurationError, match="No mapping config"):
            Mapper().map(sample_user, TargetUser)

    def test_map_source_not_basemodel_raises(self):
        with pytest.raises(ConfigurationError, match="BaseModel instance"):
            Mapper().map({"first_name": "x"}, TargetUser)  # type: ignore

    def test_map_to_type_not_basemodel_raises(self, sample_user):
        with pytest.raises(ConfigurationError, match="pydantic BaseModel subclass"):
            Mapper().map(sample_user, dict)  # type: ignore

    def test_invalid_jmespath_expression_raises_field_mapping_error(self, sample_user):
        class BadTarget(BaseModel):
            x: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser, to_type=BadTarget, schema={"x": "***invalid***"}
            )
        )
        with pytest.raises(FieldMappingError, match="Invalid JMESPath expression"):
            mapper.map(sample_user, BadTarget)

    def test_pydantic_strict_type_mismatch_raises_mapping_error(self, sample_user):
        class StrictTarget(BaseModel):
            model_config = ConfigDict(strict=True)
            age: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser, to_type=StrictTarget, schema={"age": "age"}
            )
        )
        with pytest.raises(MappingError, match="Pydantic validation failed"):
            mapper.map(sample_user, StrictTarget)

    def test_missing_required_target_field_raises_mapping_error(self, sample_user):
        class RequiredTarget(BaseModel):
            must_have: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(from_type=SourceUser, to_type=RequiredTarget, schema={})
        )
        with pytest.raises(MappingError, match="Pydantic validation failed"):
            mapper.map(sample_user, RequiredTarget)

    def test_field_mapping_error_carries_field_name(self, sample_user):
        def raiser(d):
            raise RuntimeError("boom")

        class BadTarget(BaseModel):
            problem_field: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=BadTarget,
                schema={"problem_field": raiser},
            )
        )
        with pytest.raises(FieldMappingError) as exc_info:
            mapper.map(sample_user, BadTarget)
        assert exc_info.value.field == "problem_field"

    def test_field_mapping_error_message_contains_field_name(self, sample_user):
        def raiser(d):
            raise ValueError("bad input")

        class BadTarget(BaseModel):
            my_special_field: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=BadTarget,
                schema={"my_special_field": raiser},
            )
        )
        with pytest.raises(FieldMappingError, match="my_special_field"):
            mapper.map(sample_user, BadTarget)


class TestOptionalAndNoneHandling:
    def test_none_from_missing_path_mapped_to_optional_field(self, sample_user):
        class T(BaseModel):
            missing: Optional[str] = None

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser, to_type=T, schema={"missing": "nonexistent.path"}
            )
        )
        assert mapper.map(sample_user, T).missing is None

    def test_none_value_from_optional_source_field(self):
        from tests.conftest import ContactInfo, Address

        user = SourceUser(
            first_name="Bob",
            last_name="Jones",
            age=25,
            contact=ContactInfo(email="bob@example.com", phone=None),
            address=Address(street="1 St", city="Leeds", postcode="LS1 1AA"),
        )

        class T(BaseModel):
            phone: Optional[str] = None

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser, to_type=T, schema={"phone": "contact.phone"}
            )
        )
        assert mapper.map(user, T).phone is None

    def test_empty_list_projection(self):
        from tests.conftest import ContactInfo, Address

        user = SourceUser(
            first_name="Bob",
            last_name="Jones",
            age=25,
            contact=ContactInfo(email="bob@example.com"),
            address=Address(street="1 St", city="Leeds", postcode="LS1 1AA"),
            tags=[],
        )

        class T(BaseModel):
            tag_names: Optional[list[str]] = None

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser, to_type=T, schema={"tag_names": "tags[*].name"}
            )
        )
        result = mapper.map(user, T)
        # JMESPath returns None for a wildcard projection over an empty list
        assert result.tag_names is None or result.tag_names == []

    def test_target_fields_not_in_schema_use_pydantic_defaults(self, sample_user):
        from tests.conftest import TargetUserDetailed

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=TargetUserDetailed,
                schema={
                    "full_name": {
                        "expression": lambda d: f"{d['first_name']} {d['last_name']}"
                    },
                    "email": "contact.email",
                    "age": "age",
                    "city": "address.city",
                    "postcode": "address.postcode",
                    "active": "active",
                    "birth_date": "birth_date",
                    # score intentionally omitted → default 0.0
                },
            )
        )
        assert mapper.map(sample_user, TargetUserDetailed).score == 0.0


class TestMapMany:
    def test_map_many_returns_list_of_correct_type(self, basic_mapper):
        from tests.conftest import ContactInfo, Address

        users = [
            SourceUser(
                first_name="Alice",
                last_name="Smith",
                age=28,
                contact=ContactInfo(email="alice@example.com"),
                address=Address(street="1 A St", city="Bath", postcode="BA1 1AA"),
            ),
            SourceUser(
                first_name="Bob",
                last_name="Jones",
                age=35,
                contact=ContactInfo(email="bob@example.com"),
                address=Address(street="2 B St", city="Bristol", postcode="BS1 1BB"),
            ),
        ]
        results = basic_mapper.map_many(users, TargetUser)
        assert len(results) == 2
        assert all(isinstance(r, TargetUser) for r in results)
        assert results[0].email == "alice@example.com"
        assert results[1].city == "Bristol"

    def test_map_many_empty_list_returns_empty_list(self, basic_mapper):
        assert basic_mapper.map_many([], TargetUser) == []

    def test_map_many_non_list_raises(self, basic_mapper, sample_user):
        with pytest.raises(ConfigurationError, match="list"):
            basic_mapper.map_many(sample_user, TargetUser)  # type: ignore
