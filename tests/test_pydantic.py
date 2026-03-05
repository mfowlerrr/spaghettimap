"""Tests for pydantic-specific nuances and real-world model scenarios."""

from __future__ import annotations

from datetime import date
from typing import Optional

import pytest
from pydantic import BaseModel, Field, field_validator, model_validator

from jmespath_mapper import MappingConfig, Mapper
from tests.conftest import (
    Address,
    ContactInfo,
    SourceProduct,
    SourceUser,
    TargetProduct,
    TargetProductSummary,
)


class TestPydanticNuances:
    def test_field_validators_run_on_target(self):
        class ValidatedTarget(BaseModel):
            email: str

            @field_validator("email")
            @classmethod
            def must_contain_at(cls, v: str) -> str:
                if "@" not in v:
                    raise ValueError("not a valid email")
                return v

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=ValidatedTarget,
                schema={"email": "contact.email"},
            )
        )
        user = SourceUser(
            first_name="A", last_name="B", age=1,
            contact=ContactInfo(email="valid@example.com"),
            address=Address(street="s", city="c", postcode="p"),
        )
        assert mapper.map(user, ValidatedTarget).email == "valid@example.com"

    def test_model_validator_runs_on_target(self):
        class CrossFieldTarget(BaseModel):
            a: int
            b: int
            total: int = 0

            @model_validator(mode="after")
            def compute_total(self) -> "CrossFieldTarget":
                self.total = self.a + self.b
                return self

        class Source(BaseModel):
            x: int
            y: int

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(from_type=Source, to_type=CrossFieldTarget, schema={"a": "x", "b": "y"})
        )
        result = mapper.map(Source(x=3, y=7), CrossFieldTarget)
        assert result.total == 10

    def test_pydantic_type_coercion(self):
        """Pydantic v2 coerces compatible types by default in non-strict mode."""

        class CoerceSource(BaseModel):
            val: str

        class CoerceTarget(BaseModel):
            val: int

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(from_type=CoerceSource, to_type=CoerceTarget, schema={"val": "val"})
        )
        assert mapper.map(CoerceSource(val="42"), CoerceTarget).val == 42

    def test_aliased_target_field_mapped_by_python_name(self):
        class AliasedTarget(BaseModel):
            full_name: str = Field(alias="fullName")
            model_config = {"populate_by_name": True}

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=AliasedTarget,
                schema={"full_name": {"expression": lambda d: f"{d['first_name']} {d['last_name']}"}},
            )
        )
        user = SourceUser(
            first_name="Clara", last_name="Bell", age=22,
            contact=ContactInfo(email="c@b.com"),
            address=Address(street="s", city="c", postcode="p"),
        )
        assert mapper.map(user, AliasedTarget).full_name == "Clara Bell"

    def test_source_field_alias_uses_python_name_in_schema(self):
        class AliasSource(BaseModel):
            user_name: str = Field(alias="userName")
            model_config = {"populate_by_name": True}

        class SimpleTarget(BaseModel):
            name: str

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(from_type=AliasSource, to_type=SimpleTarget, schema={"name": "user_name"})
        )
        # model_dump() uses Python field names by default
        assert mapper.map(AliasSource(user_name="charlie"), SimpleTarget).name == "charlie"

    def test_date_field_preserved(self, sample_user):
        class DateTarget(BaseModel):
            birth_date: Optional[date] = None

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(from_type=SourceUser, to_type=DateTarget, schema={"birth_date": "birth_date"})
        )
        assert mapper.map(sample_user, DateTarget).birth_date == date(1994, 6, 15)

    def test_nested_target_model_coerced_from_dict(self, sample_user):
        class NestedTarget(BaseModel):
            class Info(BaseModel):
                email: str
                city: str

            info: Info

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceUser,
                to_type=NestedTarget,
                schema={"info": {"expression": "{email: contact.email, city: address.city}"}},
            )
        )
        result = mapper.map(sample_user, NestedTarget)
        assert isinstance(result.info, NestedTarget.Info)
        assert result.info.email == "jane@example.com"
        assert result.info.city == "London"

    def test_source_nested_model_serialised_for_jmespath(self, sample_user):
        """Projecting over a list of nested models works (models become dicts)."""

        class T(BaseModel):
            weights: list[float]

        mapper = Mapper()
        mapper.add_config(
            MappingConfig(from_type=SourceUser, to_type=T, schema={"weights": "tags[*].weight"})
        )
        assert mapper.map(sample_user, T).weights == [2.0, 1.5]


class TestProductMapping:
    """Real-world product model mapping scenario."""

    def _product_mapper(self) -> Mapper:
        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceProduct,
                to_type=TargetProduct,
                schema={
                    "id": "product_id",
                    "name": "title",
                    "price": "price",
                    "available": {"expression": "stock", "transform": lambda s: s > 0},
                    "primary_category": "categories[0]",
                },
            )
        )
        return mapper

    def test_basic_product_mapping(self, sample_product):
        result = self._product_mapper().map(sample_product, TargetProduct)
        assert isinstance(result, TargetProduct)
        assert result.id == "prod-001"
        assert result.name == "Widget Pro"
        assert result.price == pytest.approx(29.99)
        assert result.available is True
        assert result.primary_category == "tools"

    def test_out_of_stock_product(self):
        product = SourceProduct(product_id="p2", title="Old", price=9.99, stock=0)
        assert self._product_mapper().map(product, TargetProduct).available is False

    def test_price_formatted_with_transform(self, sample_product):
        mapper = Mapper()
        mapper.add_config(
            MappingConfig(
                from_type=SourceProduct,
                to_type=TargetProductSummary,
                schema={
                    "id": "product_id",
                    "name": "title",
                    "price_formatted": {"expression": "price", "transform": lambda p: f"£{p:.2f}"},
                },
            )
        )
        assert mapper.map(sample_product, TargetProductSummary).price_formatted == "£29.99"

    def test_no_categories_returns_none_for_first_element(self):
        product = SourceProduct(product_id="p3", title="Bare", price=1.0, stock=5, categories=[])
        assert self._product_mapper().map(product, TargetProduct).primary_category is None
