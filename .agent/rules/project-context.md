---
trigger: always_on
---

# Project Context: `datavault4sqlglot`

## 1. What is `datavault4sqlglot`?
`datavault4sqlglot` is a Python library that ports the logic and functionality of the popular [`datavault4dbt`](https://github.com/ScalefreeCOM/datavault4dbt) package into a standalone, pure-Python solution. 

`datavault4sqlglot` leverages **sqlglot** to generate syntactically correct, dialect-agnostic SQL for Data Vault 2.0 entities.

## 2. Goal & Vision
The primary goal is to **generalize the Data Vault automation logic** found in `datavault4dbt` and make it available to the wider Python ecosystem, not just dbt users.

**Key Objectives:**
-   **Expansion**: Enable use cases like standalone ETL scripts, dynamic SQL generation in Airflow/Dagster, or custom platform integrations.
-   **Parity**: Replicate the core standard Data Vault 2.0 patterns (Hubs, Links, Satellites) and advanced features (incremental loading, ghost records, multisource support).

## 3. Scope & Responsibilities

### In Scope
-   **Entity Generators**: Python classes to generate SQL for:
    -   **Stage**: Hashing, aliasing, constants.
    -   **Standard Entities**: Hubs, Links, Satellites.
    -   **Advanced Entities**: Multi-Active Satellites, Effectivity Satellites, Non-Historized Links/Sats.
    -   **Query Helpers**: Point-In-Time (PIT) tables, Bridge tables.
-   **Incremental Logic**:
    -   Implementing the **High-Water-Mark (HWM)** strategy for efficient incremental loads.
    -   Handling "End-dated" records and snapshot logic.
-   **Platform Agnostic**: generating SQL that `sqlglot` can transpile to Snowflake, BigQuery, Redshift, Postgres, etc.

### Out of Scope (for now)
-   **Execution**: This library generates SQL; it does not execute it against a database (though it may include helpers for testing).
-   **CLI**: The focus is on the library/API, not a command-line tool.

## 4. Architecture

### Core Design Principles
1.  **Object-Oriented Generators**: Each entity type (e.g., `Hub`, `Satellite`) has a corresponding Python class (e.g., `HubGenerator`) responsible for building its SQL.
2.  **Native sqlglot**: Logic is built using `sqlglot.exp` native expressions (not string manipulation or generic `exp.func`), ensuring the Abstract Syntax Tree (AST) is valid and transpilable.
3.  **Modular Logic**: Common patterns (e.g., "calculate HWM", "deduplicate source rows") are encapsulated in reusable, testable helper functions.

### Data Flow
1.  **Input**: Metadata describing the source tables, columns, and business keys (likely via Pydantic models or typed dictionaries).
2.  **Processing**: The `Generator` class applies Data Vault 2.0 patterns and incremental logic (HWM) to build a `sqlglot` expression tree.
3.  **Output**: A SQL string (compiled for the target dialect) or a `sqlglot` expression object for further manipulation.

## 5. Usage Example (Conceptual)

```python
from datavault4sqlglot.generators import HubGenerator
from datavault4sqlglot.models import SourceTable

# 1. Define Metadata
source = SourceTable(
    table_name="raw.orders",
    business_keys=["order_id"],
    load_date_col="load_date",
    source_col="record_source"
)

# 2. Instantiate Generator
generator = HubGenerator(
    target_table="dv.hub_orders",
    source_models=[source],
    is_incremental=True
)

# 3. Generate SQL
sql = generator.generate_sql()
print(sql)
# Output: INSERT INTO dv.hub_orders (...) SELECT ... WHERE ...
```
