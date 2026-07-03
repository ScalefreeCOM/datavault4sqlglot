# datavault4sqlglot

A Python library for generating Data Vault 2 SQL using [sqlglot](https://github.com/tobymao/sqlglot).
Produces dialect-agnostic SQL for Hubs, Links, Satellites, and Staging layers — no dbt, no live database connection required.

## Quick Start

```python
from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.metadata import SourceModel, SourceBinding

# Describe the staged source table
source = SourceModel(
    schema="stage",
    table_name="stg_orders",
    load_date_col="ldts",
    record_source_col="rsrc",
)

# Bind the source to a Hub: declare which column is the business key
binding = SourceBinding(
    source=source,
    business_keys=["order_id"],
)

# Generate the Hub SQL
generator = HubGenerator(
    sources=[binding],
    hashkey="hk_order_h",
    target_schema="dv",
    target_table="order_h",
    is_incremental=True,
)

print(generator.to_sql())
```

## Configuration

The library uses a global configuration object (`datavault4sqlglot.config`) with the following defaults:

| Key | Default | Description |
|---|---|---|
| `dialect` | `snowflake` | Target SQL dialect |
| `hash` | `MD5` | Hash algorithm (`MD5`, `SHA256`, `SHA1`) |
| `ldts_alias` | `ldts` | Load date timestamp column name |
| `rsrc_alias` | `rsrc` | Record source column name |
| `ledts_alias` | `ledts` | Load end date column name |
| `end_of_all_times` | `9999-12-31` | Sentinel for open-ended records |
| `beginning_of_all_times` | `0001-01-01` | Sentinel for ghost records |
| `hashkey_input_case_sensitive` | `false` | Apply `UPPER()` before hashing hash keys |
| `hashdiff_input_case_sensitive` | `false` | Apply `UPPER()` before hashing hash diffs |
| `use_trim` | `true` | Apply `TRIM()` before hashing |
| `quote_identifiers` | `true` | Quote table and column identifiers |
| `ghost_record_rsrc` | `SYSTEM` | Record source value for the unknown ghost row |
| `ghost_record_error_rsrc` | `ERROR` | Record source value for the error ghost row |

You can override any of these by placing a `config.json` file in your current working directory.
The library will automatically load and apply these settings when imported.

**Example `config.json`:**

```json
{
  "ldts_alias": "load_date_timestamp",
  "hash": "SHA256",
  "dialect": "bigquery"
}
```

You can also manually load a configuration file from a specific path:

```python
from datavault4sqlglot.config import config, load_config

load_config(config, "/path/to/my/custom_config.json")
```

## Models

Three distinct classes, each for a different layer:

### `StageModel` — used exclusively by `StageGenerator`

Describes a raw source table that needs to be hashed and prepared. It owns everything about that transformation: which columns to hash, derived expressions, missing columns for schema evolution, etc. It's a self-contained description of one staging job — no binding to anything else.

```python
StageModel(
    table_name="raw.orders",
    hashed_columns={"HK_ORDER_H": ["ORDER_ID"]},
    derived_columns={"ldts": "CURRENT_TIMESTAMP()"},
)
```

### `SourceModel` — the physical table pointer used by vault generators (Hub, Link, Sat)

Just says where to find the already-staged data: table name, optional schema/database, and which
columns are `ldts`/`rsrc` if they differ from the config defaults. No transformation logic.

```python
SourceModel(
    database="RAW_DB",
    schema="STAGE",
    table_name="STG_ORDERS",
    load_date_col="LOAD_DATE",
    record_source_col="RECORD_SOURCE",
)
```

### `SourceBinding` — wraps a `SourceModel` with DV-loading intent

Answers what to extract from that staged table for a specific vault entity: per-source physical
`bk_columns` (when they differ from the hub's canonical names), foreign hash keys (for links),
`rsrc_statics` for HWM scoping, etc. A single `SourceModel` can be wrapped in different
`SourceBinding`s for different vault entities.

The hub-level *canonical* `business_keys` live on `HubGenerator` itself (not on the binding) —
every binding into the same hub maps onto that same canonical name set.

```python
SourceBinding(
    source=_SRC_ORDERS_MODEL,        # the SourceModel
    bk_columns=["SAP_ORDER_ID"],     # only needed when the source's column
                                     # name differs from the hub canonical
    rsrc_statics=["ERP/ORDERS"],
)
```

## Conceptual split

→ Staging table  
&emsp;→ `StageModel` → `StageGenerator` → staged table (to calculate hash keys)

→ Raw Data Vault table  
&emsp;→ `SourceModel` — where is the data?  
&emsp;&emsp;→ `SourceBinding` — what to extract, for which vault entity?  
&emsp;&emsp;&emsp;→ `HubGenerator` / `LinkGenerator` / `SatelliteGenerator`

`StageModel` and `SourceModel` are both Pydantic models (validated on construction). `SourceBinding` is a plain dataclass — it's just a lightweight container pairing a `SourceModel` with extraction metadata.

---

## 📄 License

This project is licensed under the **GNU Affero General Public License v3 (AGPL-3.0)** - see the [LICENSE](LICENSE) file for details.

---
## 🤝 Contributing

We welcome and appreciate community contributions! To keep the project sustainable while ensuring the software remains open and accessible, we follow a **Dual-Licensing** model.

### 📜 Licensing & Open Source
This project is licensed under the **GNU Affero General Public License v3 (AGPL-3.0)**. 

The AGPL is a "strong copyleft" license. If you modify this software and provide it as a service over a network (SaaS), you **must** make your modified source code available to your users under the same license.

### ✍️ Contributor License Agreement (CLA)
To contribute code, all contributors are required to sign our **Contributor License Agreement (CLA)**. 
* **Why?** This ensures that you have the right to contribute the code and grants us the necessary rights to include your work in future versions of the project, including potential commercial or non-AGPL distributions.
* **How?** **FIXME**

### 💼 Commercial Usage & Licensing
We understand that the AGPL-3.0 may not be suitable for every organization's internal policies or proprietary products. 

If you wish to use this project in a commercial or proprietary setting without the "copyleft" requirements of the AGPL, we offer **alternative commercial licenses**. This allows you to:
* Use the software without disclosing your own source code.
* Receive dedicated support and enterprise-grade warranties.
* Support the development team.

Please contact us at **contact@scalefree.com** to discuss a commercial license tailored to your needs.

---

Built by [Scalefree](https://scalefree.com)
