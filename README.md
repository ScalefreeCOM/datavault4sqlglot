# datavault4sqlglot

## Configuration

The library uses a global configuration object (`datavault4sqlglot.config`) with sane defaults. 
You can override these defaults by placing a `config.json` file in your current working directory. 
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




Three distinct classes, each for a different layer:

---
StageModel — used exclusively by StageGenerator

Describes a raw source table that needs to be hashed and prepared. It owns everything about that transformation: which columns to hash, derived expressions, missing columns for schema evolution, etc. It's a self-contained description of one staging job — no binding to anything else.

StageModel(
    table_name="raw.orders",
    hashed_columns={"HK_ORDER_H": ["ORDER_ID"]},
    derived_columns={"ldts": "CURRENT_TIMESTAMP()"},
)

---
SourceModel — the physical table pointer used by vault generators (Hub, Link, Sat)

Just says where to find the already-staged data: table name, optional schema/database, and which columns are ldts/rsrc if they differ from the config defaults. No transformation logic.

SourceModel(
    database="RAW_DB", schema="STAGE", table_name="STG_ORDERS",
    load_date_col="LOAD_DATE", record_source_col="RECORD_SOURCE",
)

---
SourceBinding — wraps a SourceModel with DV-loading intent

Answers what to extract from that staged table for a specific vault entity: which columns are business keys, which are foreign hash keys (for links), what the rsrc_statics are for HWM scoping, etc. A single SourceModel can be wrapped in different SourceBindings for different vault entities.

SourceBinding(
    source=_SRC_ORDERS_MODEL,   # ← the SourceModel
    business_keys=["ORDER_ID"],
    rsrc_statics=["ERP/ORDERS"],
)

---
The conceptual split:

Raw DB table
    └── StageModel  →  StageGenerator  →  staged table (with hash keys)

Staged table
    └── SourceModel (where is it?)
          └── SourceBinding (what do I want from it, for which vault entity?)
                └── HubGenerator / LinkGenerator / SatelliteGenerator

StageModel and SourceModel are both Pydantic models (validated on construction). SourceBinding is a plain dataclass — it's just a lightweight container pairing a SourceModel with extraction metadata, so Pydantic validation would be overkill there.