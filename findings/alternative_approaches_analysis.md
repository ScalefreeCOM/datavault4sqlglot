# Alternative Approaches to datavault4sqlglot

Analysis date: 2026-05-08

## Context

The current `datavault4sqlglot` package generates Data Vault 2.0 SQL using sqlglot ASTs. This document explores whether a PySpark or DataFrame-based alternative would be viable, and how it would interact with the two integration targets: Bruin and SQLMesh.

---

## What the current package actually does

It operates at the **SQL generation layer** — it produces SQL ASTs (via sqlglot) that are executed by whatever tool runs the pipeline. No data ever touches Python at runtime. This is why it composes so well with SQLMesh.

A DataFrame-based alternative operates at the **execution layer** — Python code actually processes the data rows. This is a fundamentally different paradigm.

---

## The three realistic alternatives

### 1. PySpark DataFrames

```python
class HubGenerator:
    def generate(self, spark, source_df: DataFrame) -> DataFrame:
        from pyspark.sql import functions as F, Window
        hk = source_df.withColumn(
            self.hashkey,
            F.lower(F.md5(F.concat_ws("|", *self.business_keys)))
        )
        w = Window.partitionBy(self.hashkey).orderBy(F.col(self.ldts).asc())
        return hk.withColumn("_rn", F.row_number().over(w))\
                 .filter(F.col("_rn") == 1).drop("_rn")
```

**Compatibility:**

| Tool | Compatible? | Notes |
|------|-------------|-------|
| Bruin | **Yes** | Bruin supports `type: python` assets with a `materialize()` function that returns a pandas/polars DataFrame or list of dicts. Bruin materializes it to the target table via ingestr (Apache Arrow transport). Supports `append`, `merge`, `delete+insert`, `create+replace` strategies. Incremental window injected via `BRUIN_START_DATE` / `BRUIN_END_DATETIME` env vars. |
| SQLMesh | **Conditionally yes** | SQLMesh has native Python model support that returns DataFrames. But the current SQLMesh project targets **Postgres**, not Spark. Switching to Databricks or another Spark-compatible engine would be required. For Postgres, SQLMesh would have to pull all data into Python memory — completely impractical at scale. |

**Verdict:** Works with Bruin. For SQLMesh, only efficient on a Spark backend (Databricks); Postgres requires pulling all data into Python memory.

---

### 2. Pandas / Polars DataFrames

```python
class HubGenerator:
    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        df["hk_customer_h"] = df[self.business_keys].apply(
            lambda row: hashlib.md5("|".join(str(v) for v in row).encode()).hexdigest(), axis=1
        )
        return df.sort_values(self.ldts).groupby(self.hashkey).first().reset_index()
```

**Compatibility:**

| Tool | Compatible? | Notes |
|------|-------------|-------|
| Bruin | **Yes** | Same Python asset support as above — `materialize()` returning a pandas/polars DataFrame is fully supported and materialized by Bruin automatically. |
| SQLMesh | **Technically yes, practically no** | SQLMesh can use Python models that return pandas DataFrames and insert them via its engine adapter. But for large tables this pulls everything into Python RAM. SQLMesh's framework-level incremental management (time-range injection) is bypassed and must be reimplemented manually. |

**Verdict:** Only useful for testing/dev, not production-scale DV pipelines. The RAM problem is fundamental to pandas — it applies equally regardless of which orchestration tool (Bruin or SQLMesh) runs the model, because the data must be fully loaded into Python memory before any filtering or transformation can occur.

---

### 3. Ibis (most viable alternative to sqlglot)

Ibis is a Python DataFrame-like API that **compiles to SQL** for 20+ backends. It is the closest philosophical alternative to the current sqlglot approach.

```python
import ibis

class HubGenerator:
    def generate(self, source_table: ibis.Table) -> ibis.Table:
        hashed = source_table.mutate(
            hk_customer_h=source_table[self.business_keys].hash()
        )
        return hashed.group_by(self.hashkey)\
                     .aggregate(load_date=hashed[self.ldts].min(), ...)
```

**Compatibility:**

| Tool | Compatible? | Notes |
|------|-------------|-------|
| Bruin | **Possible** | Call `ibis_table.compile()` to get a SQL string, then embed it in Bruin assets. Same integration pattern as today. |
| SQLMesh | **Yes** | SQLMesh Python models can return Ibis tables directly (SQLMesh has a native Ibis integration), or call `.to_sql()` and return a string. |

**Key trade-off vs sqlglot:** Ibis is higher-level and more ergonomic, but gives less control over exact SQL output. For DV-specific patterns like consecutive LAG-based hash-diff detection or rsrc_static-scoped HWM CTEs, sqlglot's AST manipulation gives more precision. Ibis would struggle with some of the complex CTE compositions in the satellite and hub generators.

---

## What a PySpark/DataFrame package structure would look like

If building for a Spark-first world (Databricks), the package would be:

```
datavault4spark/
├── datavault4spark/
│   ├── __init__.py
│   ├── config.py          # same config concept
│   ├── metadata/
│   │   └── source.py      # same Pydantic models (reusable as-is)
│   ├── generators/
│   │   ├── base.py        # base with hash UDFs via pyspark.sql.functions
│   │   ├── stage.py       # returns DataFrame
│   │   ├── hub.py         # returns DataFrame
│   │   ├── link.py
│   │   └── satellite.py   # LAG via Window functions
│   └── utils/
│       └── hash.py        # MD5/SHA256 via F.md5/F.sha2
```

The metadata layer (Pydantic models) and generator class API would look almost identical to `datavault4sqlglot`. Only the internals change — instead of building sqlglot AST nodes, the generators build PySpark Column/DataFrame transformations. The `metadata/` package could in principle be shared between both libraries.

---

## Summary comparison

| Approach | Bruin | SQLMesh (Postgres) | SQLMesh (Spark) | Control over SQL |
|---|---|---|---|---|
| **sqlglot AST (current)** | Yes (via SQL string) | Yes | Yes | Full |
| **PySpark DataFrames** | Yes (via `materialize()`) | No | Yes | N/A (execution layer) |
| **Pandas/Polars** | Impractical (all data in RAM) | Impractical (all data in RAM) | No | N/A (execution layer) |
| **Ibis** | Possible | Yes | Yes | Medium |

---

## Recommendation

**If target environments stay Postgres + Bruin + SQLMesh**, the current sqlglot approach is the right layer. The alternatives either don't integrate or require pulling data into Python at runtime.

**If a Databricks/Spark variant is ever needed**, PySpark is the natural extension. Because the metadata layer (Pydantic models: `SourceModel`, `SourceBinding`, `StageModel`) is already decoupled from the generation logic, a `datavault4spark` package could reuse the same config and metadata models with different generator internals — no duplication needed.
