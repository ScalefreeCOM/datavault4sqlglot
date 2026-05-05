"""Generates example SQL files for every generator type into temp_sql/."""
from pathlib import Path

from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.generators.link import LinkGenerator
from datavault4sqlglot.generators.satellite import SatelliteGenerator
from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel, StageModel

OUT = Path("temp_sql")
OUT.mkdir(exist_ok=True)


def write(name: str, sql: str) -> None:
    path = OUT / name
    path.write_text(sql, encoding="utf-8")
    print(f"  wrote {path}")


# ---------------------------------------------------------------------------
# 01 — Stage (full load, hash key + hashdiff)
# ---------------------------------------------------------------------------
write(
    "01_stage.sql",
    StageGenerator(
        source_model=StageModel(
            table_name="raw_orders",
            hashed_columns={
                "hk_order": ["order_id"],
                "hd_order_details": ["status", "amount", "currency"],
            },
            derived_columns={
                "load_tss": "CURRENT_TIMESTAMP()",
                "record_source": "'SAP/ORDERS'",
            },
        ),
        target_table="stg_orders",
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 02 — Hub (incremental, single source, rsrc_static HWM)
# ---------------------------------------------------------------------------
write(
    "02_hub_incremental_rsrc_static.sql",
    HubGenerator(
        target_table="hub_order",
        target_schema="dv",
        sources=[
            SourceBinding(
                source=SourceModel(table_name="stg_orders"),
                hash_key_col="hk_order",
                business_keys=["order_id"],
                rsrc_statics=["SAP/ORDERS/%"],
            )
        ],
        hashkey="hk_order",
        is_incremental=True,
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 03 — Hub (incremental, multi-source, generic HWM)
# ---------------------------------------------------------------------------
write(
    "03_hub_incremental_multi_source.sql",
    HubGenerator(
        target_table="hub_order",
        target_schema="dv",
        sources=[
            SourceBinding(
                source=SourceModel(table_name="stg_orders_web"),
                hash_key_col="hk_order",
                business_keys=["order_id"],
            ),
            SourceBinding(
                source=SourceModel(table_name="stg_orders_store"),
                hash_key_col="hk_order",
                business_keys=["order_id"],
            ),
        ],
        hashkey="hk_order",
        is_incremental=True,
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 04 — Link (incremental, rsrc_static HWM)
# ---------------------------------------------------------------------------
write(
    "04_link_incremental_rsrc_static.sql",
    LinkGenerator(
        target_table="lnk_order_customer",
        target_schema="dv",
        sources=[
            SourceBinding(
                source=SourceModel(table_name="stg_orders"),
                hash_key_col="hk_lnk_order_customer",
                foreign_hash_keys=["hk_order", "hk_customer"],
                rsrc_statics=["SAP/ORDERS/%"],
            )
        ],
        link_hash_key="hk_lnk_order_customer",
        is_incremental=True,
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 05 — Satellite v0 (incremental, LAG dedup + NOT EXISTS, rsrc_static HWM)
# ---------------------------------------------------------------------------
write(
    "05_satellite_v0_incremental.sql",
    SatelliteGenerator(
        target_table="sat_order_details",
        target_schema="dv",
        source_model=SourceModel(table_name="stg_orders"),
        parent_hash_key="hk_order",
        hash_diff="hd_order_details",
        payload=["status", "amount", "currency"],
        is_incremental=True,
    ).to_sql(),
)

print("Done.")
