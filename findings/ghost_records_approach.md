# Ghost Records — Implementation Approach

Analysis date: 2026-05-08

## Context

In Data Vault 2.0, a ghost record (also called a zero record or default record) is a sentinel row
inserted once into every Hub and Satellite. It represents the "unknown" entity and allows foreign
keys in downstream models to always resolve — avoiding NULLs in link keys.

In `datavault4dbt`, ghost records are generated using the `dbt_utils.type_*` macros combined with
`adapter.get_columns_in_relation`, which introspects the live table schema at compile time to
produce correctly-typed NULLs or default values for every column. The Python package has no dbt
adapter — generators run offline and produce SQL strings without a live connection.

---

## The problem

Ghost record SQL must CAST each column to its correct type, e.g.:

```sql
INSERT INTO dv.customer_h
SELECT
  MD5('')                              AS hk_customer_h,
  CAST(NULL AS VARCHAR)                AS customer_id,
  CAST('0001-01-01' AS TIMESTAMP)      AS load_date,
  CAST('SYSTEM' AS VARCHAR)            AS record_source
```

Without knowing the schema, we cannot emit the CAST expressions. Getting the schema requires either
user-supplied metadata or a live DB connection.

---

## Option A — User-supplied type map (offline, pure)

The user provides `ghost_record_types: Dict[str, str]` on the generator. The generator emits a
ghost record INSERT using `exp.DataType.build(type_str)` for each column.

```python
HubGenerator(
    target_table="customer_h",
    target_schema="dv",
    sources=[binding],
    hashkey="hk_customer_h",
    is_incremental=True,
    ghost_record=True,
    ghost_record_types={
        "hk_customer_h": "VARCHAR",
        "customer_id":   "VARCHAR",
        "load_date":     "TIMESTAMP",
        "record_source": "VARCHAR",
    },
)
```

**Pros**: no side effects, fits the current offline generation model, simple to implement.
**Cons**: user must maintain the type map manually; types can drift if the schema evolves.

**Note**: `StageModel` already has the identical pattern via `missing_columns: Dict[str, str]`
(NULL placeholder columns for schema evolution). Ghost record types would reuse the same mechanism.

---

## Option B — DB introspection helper (closest to `adapter.get_columns_in_relation`)

Add a utility function to the package that queries `information_schema.columns`:

```python
from datavault4sqlglot.utils.introspect import get_columns_from_relation

# Postgres / Snowflake / Redshift
types = get_columns_from_relation(
    conn=conn,
    schema="dv",
    table="customer_h",
    dialect="postgres",   # drives which information_schema query to use
)
# → {"hk_customer_h": "character varying", "customer_id": "character varying",
#    "load_date": "timestamp without time zone", "record_source": "character varying"}
```

The returned dict is passed straight into `ghost_record_types=` on the generator. The generator
stays pure — introspection is the caller's responsibility (same separation dbt uses between the
adapter and the macro).

### Dialect-specific queries

```python
# Postgres / Redshift
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = %(schema)s AND table_name = %(table)s
ORDER BY ordinal_position

# Snowflake
SELECT COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = %(schema)s AND TABLE_NAME = %(table)s
ORDER BY ORDINAL_POSITION

# BigQuery
SELECT column_name, data_type
FROM `{project}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = %(table)s
ORDER BY ordinal_position
```

**Pros**: exact parity with dbt's approach; works for any table regardless of how it was created;
sub-project scripts (Bruin, pure_python) already hold a live connection.
**Cons**: requires a DB connection at generation time; adds a network call to the generation step.

### Integration in sub-project scripts

```python
# bruin / pure_python pattern
from datavault4sqlglot.utils.introspect import get_columns_from_relation

_conn = psycopg2.connect(...)
_types = get_columns_from_relation(_conn, schema="dv", table="customer_h", dialect="postgres")

_generator = HubGenerator(
    ...
    ghost_record=True,
    ghost_record_types=_types,
)
```

### Integration in SQLMesh

```python
# Inside execute(evaluator, **kwargs)
# SQLMesh exposes the engine via evaluator.engine
with evaluator.engine.connect() as conn:
    types = get_columns_from_relation(conn, schema="dv", table="customer_h", dialect="postgres")

return HubGenerator(..., ghost_record=True, ghost_record_types=types).generate_sql()
```

---

## Option C — Partial auto-inference from known DV types

Most DV columns have deterministic types regardless of the target schema:

| Column class        | Always                          |
|---------------------|---------------------------------|
| Hash key / hash diff | `VARCHAR` (MD5 hex, 32 chars)  |
| `load_date`         | `TIMESTAMP`                     |
| `record_source`     | `VARCHAR`                       |
| Business keys       | Unknown (usually VARCHAR)       |
| Payload columns     | Unknown — depends on source     |

The generator could auto-produce ghost record values for the DV-standard columns without any type
input, and only require explicit types for business keys and payload. Since `payload` is already
passed as a list, it could be extended to accept `{"col": "type"}` alongside `["col"]`:

```python
SatelliteGenerator(
    ...
    payload=["customer_name", "email"],                         # types unknown → CAST(NULL AS VARCHAR) default
    # or
    payload={"customer_name": "VARCHAR", "email": "VARCHAR"},   # explicit
)
```

**Pros**: zero config for standard DV columns; only requires types for the columns that actually
vary.
**Cons**: partial solution; payload types still need user input or introspection.

---

## Recommendation

Implement **B as the primary path, A as the fallback**:

1. **`get_columns_from_relation(conn, schema, table, dialect)`** — utility in
   `datavault4sqlglot/utils/introspect.py`. Dialect-switch on the `information_schema` query.
   Returns `Dict[str, str]` of column name → SQL type string (normalised to sqlglot type names).

2. **`ghost_record: bool = False`** and **`ghost_record_types: Optional[Dict[str, str]] = None`**
   on Hub and Satellite generators. When `ghost_record=True` and `ghost_record_types` is provided,
   prepend a ghost record INSERT to the generated SQL (or return it as a separate expression).

3. Use Option C's auto-inference as the fallback inside the generator: if `ghost_record_types` is
   missing a column that is a known DV-standard column (hash key, ldts, rsrc), fill in the default
   type rather than raising an error.

### Open questions

- Should the ghost record INSERT be part of `to_sql()` / `generate_sql()` output, or a separate
  method `ghost_record_sql()`? A separate method gives the caller more control (e.g. run once on
  first load only).
- Should `get_columns_from_relation` normalise vendor type strings to sqlglot canonical names
  (e.g. `"character varying"` → `"VARCHAR"`) using `sqlglot.dialects`? This would make the
  returned dict dialect-neutral and directly usable as `exp.DataType.build()` input.
- Does `datavault4spark` need ghost records? In Delta Lake / Databricks, ghost records are
  typically inserted via a DataFrame with explicit schema — `spark.createDataFrame([ghost_row], schema)`.
  The Spark generator would need a different approach (schema from `StructType` rather than
  `information_schema`).
