# jmespath-mapper

A Python library for **pydantic model-to-model conversion** powered by [JMESPath](https://jmespath.org/).

## Features

- Map any pydantic `BaseModel` to another using a declarative schema
- Schema values can be **JMESPath expressions**, **Python callables**, or a **dict** combining both with an optional `transform`
- Full support for all **JMESPath built-in functions** (`length`, `sort`, `max_by`, `contains`, `join`, `keys`, `to_string`, …)
- **Custom JMESPath functions** via `jmespath.functions.Functions` subclass
- **Filter expressions**, multi-select hash/list, pipe expressions, wildcards, and or-expressions
- Solid **error handling** with `ConfigurationError`, `MappingError`, and `FieldMappingError` – all with clear, field-specific messages
- **Fail-fast config checks** for invalid JMESPath expressions and schema fields missing from the target model
- Pydantic validators (`@field_validator`, `@model_validator`) and type coercion run on the target model automatically
- `map_many()` for batch conversion of model lists

## Installation

```bash
pip install jmespath-mapper
# or with uv
uv add jmespath-mapper
```

## Quick Start

```python
from pydantic import BaseModel
from jmespath_mapper import Mapper, MappingConfig

class Source(BaseModel):
    first_name: str
    last_name: str
    contact: dict  # {"email": "...", "phone": "..."}
    tags: list[dict]  # [{"name": "...", "weight": 1.0}]

class Target(BaseModel):
    full_name: str
    email: str
    tag_count: int
    upper_name: str

mapper = Mapper()
mapper.add_config(
    MappingConfig(
        from_type=Source,
        to_type=Target,
        schema={
            # Python callable
            "full_name": lambda d: f"{d['first_name']} {d['last_name']}",
            # Nested JMESPath expression
            "email": "contact.email",
            # JMESPath built-in function
            "tag_count": "length(tags)",
            # JMESPath expression + Python transform
            "upper_name": {"expression": "first_name", "transform": str.upper},
        },
    )
)

result: Target = mapper.map(source_instance, Target)
```

## Schema Value Types

| Type | Description | Example |
|------|-------------|---------|
| `str` | JMESPath expression | `"contact.email"`, `"tags[*].name"`, `"length(tags)"` |
| `Callable[[dict], Any]` | Python function receiving the full source dict | `lambda d: d["x"] + d["y"]` |
| `dict` | `{"expression": str\|Callable, "transform": Callable}` | `{"expression": "price", "transform": lambda p: f"£{p:.2f}"}` |

## Custom JMESPath Functions

```python
import jmespath.functions
from jmespath_mapper import Mapper, MappingConfig

class MyFunctions(jmespath.functions.Functions):
    @jmespath.functions.signature({"types": ["string"]})
    def _func_upper(self, value: str) -> str:
        return value.upper()

mapper.add_config(
    MappingConfig(
        from_type=Source,
        to_type=Target,
        schema={"name": "upper(first_name)"},
        custom_functions=MyFunctions(),
    )
)
```

## Batch Mapping

```python
results: list[Target] = mapper.map_many(source_list, Target)
```

## Error Hierarchy

```
JmespathMapperError
├── ConfigurationError   – invalid config (bad types, missing keys, unregistered pair)
└── MappingError         – runtime mapping failure
    └── FieldMappingError – failure for a specific field (has .field attribute)
```
