# datavault4sqlglot — Claude Code Instructions

---

## 1. Project Context

### What is `datavault4sqlglot`?

`datavault4sqlglot` is a Python library that ports the logic and functionality of the popular [`datavault4dbt`](https://github.com/ScalefreeCOM/datavault4dbt) package into a standalone, pure-Python solution.

It leverages **sqlglot** to generate syntactically correct, dialect-agnostic SQL for Data Vault 2.0 entities — making DV automation available to the wider Python ecosystem, not just dbt users.

### Goal & Vision

**Key Objectives:**
- **Expansion**: Enable use cases like standalone ETL scripts, dynamic SQL generation in Airflow/Dagster, or custom platform integrations.
- **Parity**: Replicate core Data Vault 2.0 patterns (Hubs, Links, Satellites) and advanced features (incremental loading, ghost records, multisource support).

### Scope

**In Scope:**
- **Entity Generators**: Python classes to generate SQL for:
  - **Stage**: Hashing, aliasing, constants.
  - **Standard Entities**: Hubs, Links, Satellites.
  - **Advanced Entities**: Multi-Active Satellites, Effectivity Satellites, Non-Historized Links/Sats.
  - **Query Helpers**: Point-In-Time (PIT) tables, Bridge tables.
- **Incremental Logic**: High-Water-Mark (HWM) strategy; end-dated records; snapshot logic.
- **Platform Agnostic**: SQL that sqlglot can transpile to Snowflake, BigQuery, Redshift, Postgres, etc.

**Out of Scope (for now):**
- **Execution**: This library generates SQL; it does not execute it against a database.
- **CLI**: Focus is on the library/API, not a command-line tool.

### Architecture

**Core Design Principles:**
1. **Object-Oriented Generators**: Each entity type (e.g., `Hub`, `Satellite`) has a corresponding class (e.g., `HubGenerator`) responsible for building its SQL.
2. **Native sqlglot**: Logic is built using `sqlglot.exp` native expressions — not string manipulation or generic `exp.func` — so the AST is valid and transpilable.
3. **Modular Logic**: Common patterns (e.g., "calculate HWM", "deduplicate source rows") are encapsulated in reusable, testable helper functions.

**Data Flow:**
1. **Input**: Typed metadata describing source tables, columns, and business keys (Pydantic models or typed dicts).
2. **Processing**: The `Generator` class applies DV 2.0 patterns and incremental logic (HWM) to build a sqlglot expression tree.
3. **Output**: A SQL string (compiled for the target dialect) or a sqlglot expression object for further manipulation.

**Conceptual usage example:**
```python
from datavault4sqlglot.generators import HubGenerator
from datavault4sqlglot.models import SourceTable

source = SourceTable(
    table_name="raw.orders",
    business_keys=["order_id"],
    load_date_col="load_date",
    source_col="record_source"
)

generator = HubGenerator(
    target_table="dv.hub_orders",
    source_models=[source],
    is_incremental=True
)

sql = generator.generate_sql()
print(sql)
# Output: INSERT INTO dv.hub_orders (...) SELECT ... WHERE ...
```

---

## 2. Python Style & Coding Guidelines

### 2.1 Language & General Style

- Use **Python 3.x**; modern features are allowed and encouraged.
- Prefer **explicit, readable code** over clever one-liners.
- Follow **PEP 8** conventions unless otherwise stated.
- All new code **must be type-annotated** (see section 2.2).
- Code must be compatible with **black** (formatting), **ruff** (linting), and **mypy** (strict static type checking).

### 2.2 Type Hints

- All **public functions and methods** must include type hints for parameters and return values.
- Internal helpers should also be typed.
- Use `from __future__ import annotations` for forward references.
- Prefer precise types over `Any`:
  - Use `list[str]`, `dict[str, Any]`, `Optional[Foo]`, etc.

```python
# Good
def generate_hub(source: SourceTable) -> HubDefinition:
    ...
```

### 2.3 Imports & Module Structure

Group imports in the following order:
1. Standard library (e.g., `typing`, `pathlib`)
2. Third-party libraries (e.g., `sqlglot`, `pytest`)
3. Local application imports (e.g., `datavault4sqlglot.models`)

Use **absolute imports** within the project, not relative dot imports, unless there is a clear reason.

```python
# Good
import dataclasses
from typing import Any, Optional
import yaml
from django.db import transaction
from engine.models.source import SourceTable
from engine.services.config_loader import Config

# Avoid
from .models import *
from ..services import *
```

- **Do not use** `from module import *`.
- Keep module responsibilities cohesive:
  - Models → `engine/models/...`
  - Services → `engine/services/...`
  - CLI wiring → `engine/cli/...`

### 2.4 Naming Conventions

| Target | Convention | Example |
|---|---|---|
| Modules & files | `snake_case` | `hub_generator.py` |
| Classes | `PascalCase` | `HubGenerator`, `SourceTable` |
| Functions & methods | `snake_case` | `generate_sql` |
| Variables | `snake_case` | `source_tables`, `hash_key` |

### 2.5 Functions, Methods & Complexity

- **Keep functions focused and short.**
- If a function grows too large or does multiple things (e.g., parsing + validation + persistence), split it into smaller helpers.
- **Avoid deep nesting** — use early returns to simplify control flow.
- **Prefer pure functions** especially in services that: accept simple inputs, return values or raise exceptions, and have minimal side effects aside from well-defined DB operations or file writes.

### 2.6 Development with sqlglot

- **Always use native `sqlglot.exp` expression classes** — check if one exists before using a generic wrapper.
  - Good: `exp.Select()`, `exp.Column(this="col")`, `exp.Coalesce(this=...)`
  - Avoid: `exp.func("SELECT", ...)`, `exp.func("COALESCE", ...)`

```python
# Good
hashed_col = exp.MD5(this=exp.Upper(this=exp.Column(this="my_col")))

# Bad
hashed_col = exp.func("MD5", exp.func("UPPER", "my_col"))
```

- **Use Classes for Generators**: DV entities (Hubs, Links, Satellites) must be generated by dedicated classes (e.g., `HubGenerator`), not standalone scripts or large functions.
- **Granular Helpers**: Helper functions (e.g., for hashing, formatting) must be:
  - **Pure**: No side effects.
  - **Modular**: Small and reusable across different generators.

### 2.7 Testing

- All new features and logic must be tested using **pytest**.
- Write tests in the `tests/` directory.
- Use `pytest` fixtures for setup/teardown.
- Aim for high test coverage, especially for the SQL generation logic.

### 2.8 Exception Handling

- **Fail early**: Raise exceptions immediately when invalid state is detected.
- Use **custom exceptions** (e.g., `GeneratorError`, `ConfigurationError`) rather than generic `Exception`.
- Keep functions short and focused on a single task.

### 2.9 Docstrings

Public functions and classes must have short docstrings explaining:
- what they do,
- what arguments they expect,
- what they return or raise (if non-obvious).

```python
def generate_dbt_project(project: Project, output: OutputConfig) -> Path:
    """
    Generate a dbt project for the given project and write it to the output path.

    Returns the path to the generated project directory.
    Raises GenerationError if generation fails.
    """
```

- Use comments to explain **why** something is done, not just **what**.
- Avoid redundant comments that simply restate the code.

### 2.10 Logging

- Use Python's `logging` module over `print` for non-trivial code paths.
- Use log levels appropriately:
  - `logging.debug` — detailed internal state
  - `logging.info` — high-level process steps (e.g., "Starting metadata import…")
  - `logging.warning` / `logging.error` — problems
- Logging should be helpful for debugging, not excessively verbose in normal operation.

---

## 3. Data Vault Naming Conventions

These conventions apply to all generated entity names and column names in both `datavault4sqlglot` and `datavault4spark`.

### Entity (Table) Names

| Entity Type              | Pattern                                    | Example                  |
|--------------------------|--------------------------------------------|--------------------------|
| Hub                      | `<business_object>_h`                      | `customer_h`             |
| Link                     | `<business_object1>_<business_object2>_l`  | `order_customer_l`       |
| Satellite v0 (current)   | `<business_object>_[n\|p]0_s`              | `customer_0_s`           |
| Satellite v1 (end-dated) | `<business_object>_[n\|p]1_s`              | `customer_1_s`           |
| NH Satellite             | `<business_object>_[n\|p][0\|1]_ns`        | `customer_ns`            |
| NH Link                  | `<business_object1>_<business_object2>_nl` | `order_customer_nl`      |
| Effectivity Satellite    | `<business_object1>_<business_object2>_[0\|1]_es` | `order_customer_0_es` |
| Multi-Active Satellite   | `<business_object>_[n\|p][0\|1]_ms`        | `customer_0_ms`          |
| Reference Hub            | `<business_object>_rh`                     | `order_status_rh`        |
| Reference Satellite      | `<business_object>_rs`                     | `order_status_rs`        |

### Column Names (Hash Keys and Hash Diffs)

| Column Type    | Pattern                                          | Example                     |
|----------------|--------------------------------------------------|-----------------------------|
| Hub hash key   | `hk_h_<business_object>`                        | `hk_h_customer`             |
| Link hash key  | `hk_l_<business_object1>_<business_object2>`    | `hk_l_order_customer`       |
| Hash diff      | `hd_<business_object>_[n\|p]_s`                 | `hd_customer_s`             |

> `[n|p]` = optional namespace/partition prefix; `[0|1]` = version (0 = raw/current, 1 = end-dated).
> Hash diff names do **not** include the version number — `hd_customer_s` serves all versions.

---

## 4. Self-Review Checklist

When writing or refactoring code, verify:

1. **Existing patterns**: Does this match the existing `HubGenerator` structure?
2. **sqlglot usage**: Am I using `exp.func` where a native expression class exists?
3. **Imports**: Are they absolute and correctly sorted?
4. **Tooling**: Would `ruff`, `black`, and `mypy` pass on this code?

When generating or modifying code:
- Prefer small, cohesive changes over large, cross-cutting edits.
- Self-review generated code for:
  - Missing imports
  - Obvious type mismatches
  - Function/variable names that don't align with the naming conventions
- If unsure between multiple patterns, choose the one that is easiest to read, aligns with standard Python practices, and fits into the existing project structure.
