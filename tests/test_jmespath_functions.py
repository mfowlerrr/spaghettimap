"""Tests for JMESPath built-in functions, filters, multi-select, and pipe expressions."""

from __future__ import annotations

from typing import Optional

import pytest
from pydantic import BaseModel

from jmespath_mapper import MappingConfig, Mapper
from tests.conftest import SourceUser


def _make_mapper(from_type, to_type, schema) -> Mapper:
    mapper = Mapper()
    mapper.add_config(
        MappingConfig(from_type=from_type, to_type=to_type, schema=schema)
    )
    return mapper


class TestJmespathBuiltinFunctions:
    def test_length_of_array(self, sample_user):
        class T(BaseModel):
            tag_count: int

        result = _make_mapper(SourceUser, T, {"tag_count": "length(tags)"}).map(
            sample_user, T
        )
        assert result.tag_count == 2

    def test_length_returns_zero_for_empty_array(self):
        from tests.conftest import ContactInfo, Address

        user = SourceUser(
            first_name="A",
            last_name="B",
            age=20,
            contact=ContactInfo(email="a@b.com"),
            address=Address(street="s", city="c", postcode="p"),
        )

        class T(BaseModel):
            tag_count: int

        result = _make_mapper(SourceUser, T, {"tag_count": "length(tags)"}).map(user, T)
        assert result.tag_count == 0

    def test_sort_array_projection(self, sample_user):
        class T(BaseModel):
            sorted_tags: list[str]

        result = _make_mapper(SourceUser, T, {"sorted_tags": "sort(tags[*].name)"}).map(
            sample_user, T
        )
        assert result.sorted_tags == ["jmespath", "python"]

    def test_max_by(self, sample_user):
        class T(BaseModel):
            heaviest_tag: str

        result = _make_mapper(
            SourceUser, T, {"heaviest_tag": "max_by(tags, &weight).name"}
        ).map(sample_user, T)
        assert result.heaviest_tag == "python"

    def test_min_by(self, sample_user):
        class T(BaseModel):
            lightest_tag: str

        result = _make_mapper(
            SourceUser, T, {"lightest_tag": "min_by(tags, &weight).name"}
        ).map(sample_user, T)
        assert result.lightest_tag == "jmespath"

    def test_contains(self, sample_user):
        class T(BaseModel):
            has_python_tag: bool

        result = _make_mapper(
            SourceUser, T, {"has_python_tag": "contains(tags[*].name, 'python')"}
        ).map(sample_user, T)
        assert result.has_python_tag is True

    def test_join(self, sample_user):
        class T(BaseModel):
            tag_csv: str

        result = _make_mapper(
            SourceUser, T, {"tag_csv": "join(', ', tags[*].name)"}
        ).map(sample_user, T)
        assert result.tag_csv == "python, jmespath"

    def test_keys_on_nested_dict(self, sample_user):
        class T(BaseModel):
            meta_keys: list[str]

        result = _make_mapper(SourceUser, T, {"meta_keys": "keys(metadata)"}).map(
            sample_user, T
        )
        assert result.meta_keys == ["role"]

    def test_values_on_nested_dict(self, sample_user):
        class T(BaseModel):
            meta_values: list[str]

        result = _make_mapper(SourceUser, T, {"meta_values": "values(metadata)"}).map(
            sample_user, T
        )
        assert result.meta_values == ["admin"]

    def test_to_string(self, sample_user):
        class T(BaseModel):
            age_str: str

        result = _make_mapper(SourceUser, T, {"age_str": "to_string(age)"}).map(
            sample_user, T
        )
        assert result.age_str == "30"

    def test_to_number(self):
        class NumSource(BaseModel):
            val: str

        class NumTarget(BaseModel):
            val: float

        result = _make_mapper(NumSource, NumTarget, {"val": "to_number(val)"}).map(
            NumSource(val="3.14"), NumTarget
        )
        assert result.val == pytest.approx(3.14)

    def test_type_function(self, sample_user):
        class T(BaseModel):
            age_type: str

        result = _make_mapper(SourceUser, T, {"age_type": "type(age)"}).map(
            sample_user, T
        )
        assert result.age_type == "number"

    def test_not_null_filter(self):
        class PhoneSource(BaseModel):
            contacts: list[Optional[str]]

        class PhoneTarget(BaseModel):
            valid_contacts: list[str]

        result = _make_mapper(
            PhoneSource, PhoneTarget, {"valid_contacts": "contacts[?@ != null]"}
        ).map(PhoneSource(contacts=["a@b.com", None, "c@d.com"]), PhoneTarget)
        assert result.valid_contacts == ["a@b.com", "c@d.com"]

    def test_floor_and_ceil(self):
        class NumSource(BaseModel):
            val: float

        class NumTarget(BaseModel):
            floored: int
            ceiled: int

        result = _make_mapper(
            NumSource, NumTarget, {"floored": "floor(val)", "ceiled": "ceil(val)"}
        ).map(NumSource(val=3.7), NumTarget)
        assert result.floored == 3
        assert result.ceiled == 4

    def test_abs_function(self):
        class AbsSource(BaseModel):
            val: float

        class AbsTarget(BaseModel):
            absolute: float

        result = _make_mapper(AbsSource, AbsTarget, {"absolute": "abs(val)"}).map(
            AbsSource(val=-42.5), AbsTarget
        )
        assert result.absolute == pytest.approx(42.5)


class TestJmespathFilterAndMultiselect:
    def test_filter_expression(self, sample_user):
        class T(BaseModel):
            heavy_tags: list[str]

        result = _make_mapper(
            SourceUser, T, {"heavy_tags": "tags[?weight > `1.5`].name"}
        ).map(sample_user, T)
        assert result.heavy_tags == ["python"]

    def test_multi_select_hash(self, sample_user):
        class T(BaseModel):
            user_info: dict

        result = _make_mapper(
            SourceUser, T, {"user_info": "{name: first_name, city: address.city}"}
        ).map(sample_user, T)
        assert result.user_info == {"name": "Jane", "city": "London"}

    def test_multi_select_list(self, sample_user):
        class T(BaseModel):
            pair: list

        result = _make_mapper(SourceUser, T, {"pair": "[first_name, last_name]"}).map(
            sample_user, T
        )
        assert result.pair == ["Jane", "Doe"]

    def test_pipe_expression(self, sample_user):
        class T(BaseModel):
            tag_count: int

        result = _make_mapper(
            SourceUser, T, {"tag_count": "tags[*].name | length(@)"}
        ).map(sample_user, T)
        assert result.tag_count == 2

    def test_wildcard_object_values(self, sample_user):
        class T(BaseModel):
            meta_vals: list[str]

        result = _make_mapper(SourceUser, T, {"meta_vals": "metadata.*"}).map(
            sample_user, T
        )
        assert result.meta_vals == ["admin"]

    def test_or_expression_fallback(self):
        class FallbackSource(BaseModel):
            primary: Optional[str] = None
            fallback: str = "default"

        class FallbackTarget(BaseModel):
            value: str

        result = _make_mapper(
            FallbackSource, FallbackTarget, {"value": "primary || fallback"}
        ).map(FallbackSource(), FallbackTarget)
        assert result.value == "default"
