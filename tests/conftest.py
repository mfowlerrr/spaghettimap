"""Shared pytest fixtures and model definitions for jmespath-mapper tests."""

from __future__ import annotations

from datetime import date
from typing import Optional

import jmespath.functions
import pytest
from pydantic import BaseModel, Field

from jmespath_mapper import MappingConfig, Mapper


# ---------------------------------------------------------------------------
# Source models
# ---------------------------------------------------------------------------


class Address(BaseModel):
    street: str
    city: str
    postcode: str


class ContactInfo(BaseModel):
    email: str
    phone: Optional[str] = None


class Tag(BaseModel):
    name: str
    weight: float = 1.0


class SourceUser(BaseModel):
    first_name: str
    last_name: str
    age: int
    contact: ContactInfo
    address: Address
    tags: list[Tag] = []
    score: float = 0.0
    active: bool = True
    birth_date: Optional[date] = None
    metadata: dict[str, str] = {}


class SourceProduct(BaseModel):
    product_id: str
    title: str
    price: float
    stock: int
    categories: list[str] = []


# ---------------------------------------------------------------------------
# Target models
# ---------------------------------------------------------------------------


class TargetUser(BaseModel):
    full_name: str
    email: str
    age: int
    city: str
    tag_names: list[str] = []
    is_active: bool = True


class TargetUserDetailed(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    age: int
    city: str
    postcode: str
    tag_count: int = 0
    tag_names: list[str] = []
    score: float = 0.0
    active: bool = True
    birth_date: Optional[date] = None


class TargetProduct(BaseModel):
    id: str
    name: str
    price: float
    available: bool
    primary_category: Optional[str] = None


class TargetProductSummary(BaseModel):
    id: str
    name: str
    price_formatted: str


# ---------------------------------------------------------------------------
# Custom jmespath functions fixture
# ---------------------------------------------------------------------------


class CustomFunctions(jmespath.functions.Functions):
    @jmespath.functions.signature({"types": ["string"]})
    def _func_upper(self, value: str) -> str:
        return value.upper()

    @jmespath.functions.signature({"types": ["string"]}, {"types": ["string"]})
    def _func_concat(self, a: str, b: str) -> str:
        return a + b

    @jmespath.functions.signature({"types": ["number"]})
    def _func_double(self, value: float) -> float:
        return value * 2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_user() -> SourceUser:
    return SourceUser(
        first_name="Jane",
        last_name="Doe",
        age=30,
        contact=ContactInfo(email="jane@example.com", phone="+441234567890"),
        address=Address(street="10 High St", city="London", postcode="EC1A 1BB"),
        tags=[Tag(name="python", weight=2.0), Tag(name="jmespath", weight=1.5)],
        score=87.5,
        active=True,
        birth_date=date(1994, 6, 15),
        metadata={"role": "admin"},
    )


@pytest.fixture()
def sample_product() -> SourceProduct:
    return SourceProduct(
        product_id="prod-001",
        title="Widget Pro",
        price=29.99,
        stock=42,
        categories=["tools", "gadgets", "featured"],
    )


@pytest.fixture()
def custom_fn() -> CustomFunctions:
    return CustomFunctions()


@pytest.fixture()
def basic_mapper(sample_user: SourceUser) -> Mapper:
    """Mapper pre-loaded with a simple SourceUser → TargetUser config."""
    mapper = Mapper()
    mapper.add_config(
        MappingConfig(
            from_type=SourceUser,
            to_type=TargetUser,
            schema={
                "full_name": {
                    "expression": lambda d: f"{d['first_name']} {d['last_name']}"
                },
                "email": "contact.email",
                "age": "age",
                "city": "address.city",
                "tag_names": "tags[*].name",
                "is_active": "active",
            },
        )
    )
    return mapper
