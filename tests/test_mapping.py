"""Tests for basic JMESPath mapping, callable mappings, and dict-style mappings."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from jmespath_mapper import ConfigurationError, FieldMappingError, MappingConfig, Mapper
from tests.conftest import ContactInfo, Address, SourceUser, TargetUser


class TestBasicJmespathMapping:
    def test_direct_field_access(self, basic_mapper, sample_user):
        result = basic_mapper.map(sample_user, TargetUser)
        assert result.age == 30
        assert result.email == "jane@example.com"

    def test_nested_field_access(self, basic_mapper, sample_user):
        result = basic_mapper.map(sample_user, TargetUser)
        assert result.city == "London"

    def test_array_projection(self, basic_mapper, sample_user):
        result = basic_mapper.map(sample_user, TargetUser)
        assert result.tag_names == ["python", "jmespath"]

    def test_result_is_correct_pydantic_type(self, basic_mapper, sample_user):
        result = basic_mapper.map(sample_user, TargetUser)
        assert isinstance(result, TargetUser)

    def test_boolean_field_mapped(self, basic_mapper, sample_user):
        result = basic_mapper.map(sample_user, TargetUser)
        assert result.is_active is True

    def test_inactive_user(self, basic_mapper):
        inactive = SourceUser(
            first_name="Bob",
            last_name="Smith",
            age=40,
            contact=ContactInfo(email="bob@example.com"),
            address=Address(street="1 Low St", city="York", postcode="YO1 7AA"),
            active=False,
        )
        result = basic_mapper.map(inactive, TargetUser)
        assert result.is_active is False


class TestCallableMappings:
    def test_lambda_callable(self, sample_user):
        class CallableTarget(BaseModel):
            full_name: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=CallableTarget,
                schema={"full_name": lambda d: f"{d['first_name']} {d['last_name']}"},
            )
        )
        result = mapper.map(sample_user, CallableTarget)
        assert result.full_name == "Jane Doe"

    def test_named_function_callable(self, sample_user):
        def compute_initials(d: dict) -> str:
            return f"{d['first_name'][0]}.{d['last_name'][0]}."

        class InitialsTarget(BaseModel):
            initials: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=InitialsTarget,
                schema={"initials": compute_initials},
            )
        )
        result = mapper.map(sample_user, InitialsTarget)
        assert result.initials == "J.D."

    def test_callable_receives_full_source_dict(self, sample_user):
        received: list[dict] = []

        def capture(d: dict):
            received.append(d)
            return "captured"

        class CaptureTarget(BaseModel):
            data: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(from_type=SourceUser, to_type=CaptureTarget, schema={"data": capture})
        )
        mapper.map(sample_user, CaptureTarget)
        assert received[0]["first_name"] == "Jane"
        assert "contact" in received[0]

    def test_callable_exception_wrapped_as_field_mapping_error(self, sample_user):
        def bad(d: dict):
            raise ValueError("intentional failure")

        class BadTarget(BaseModel):
            x: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(from_type=SourceUser, to_type=BadTarget, schema={"x": bad})
        )
        with pytest.raises(FieldMappingError, match="intentional failure"):
            mapper.map(sample_user, BadTarget)


class TestDictMappings:
    def test_str_expression_with_transform(self, sample_user):
        class TransformTarget(BaseModel):
            upper_name: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=TransformTarget,
                schema={"upper_name": {"expression": "first_name", "transform": str.upper}},
            )
        )
        result = mapper.map(sample_user, TransformTarget)
        assert result.upper_name == "JANE"

    def test_callable_expression_with_transform(self, sample_user):
        class TransformTarget(BaseModel):
            tag_count_str: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=TransformTarget,
                schema={
                    "tag_count_str": {
                        "expression": lambda d: len(d["tags"]),
                        "transform": str,
                    }
                },
            )
        )
        result = mapper.map(sample_user, TransformTarget)
        assert result.tag_count_str == "2"

    def test_expression_only_no_transform(self, sample_user):
        class SimpleTarget(BaseModel):
            email: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=SimpleTarget,
                schema={"email": {"expression": "contact.email"}},
            )
        )
        result = mapper.map(sample_user, SimpleTarget)
        assert result.email == "jane@example.com"

    def test_chained_transform(self, sample_user):
        def strip_domain(email: str) -> str:
            return email.split("@")[0]

        class UserHandleTarget(BaseModel):
            handle: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=UserHandleTarget,
                schema={"handle": {"expression": "contact.email", "transform": strip_domain}},
            )
        )
        result = mapper.map(sample_user, UserHandleTarget)
        assert result.handle == "jane"

    def test_transform_that_raises_wrapped_as_field_mapping_error(self, sample_user):
        def boom(v):
            raise RuntimeError("transform exploded")

        class BoomTarget(BaseModel):
            x: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=BoomTarget,
                schema={"x": {"expression": "first_name", "transform": boom}},
            )
        )
        with pytest.raises(FieldMappingError, match="transform exploded"):
            mapper.map(sample_user, BoomTarget)
