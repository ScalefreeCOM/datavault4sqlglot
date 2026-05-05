"""Generates example SQL files for every generator type into temp_sql/."""
from pathlib import Path

from datavault4sqlglot.generators.eff_sat import EffSatGenerator
from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.generators.link import LinkGenerator
from datavault4sqlglot.generators.ma_sat_v0 import MultiActiveSatV0Generator
from datavault4sqlglot.generators.ma_sat_v1 import MultiActiveSatV1Generator
from datavault4sqlglot.generators.nh_link import NonHistorizedLinkGenerator
from datavault4sqlglot.generators.nh_sat import NonHistorizedSatGenerator
from datavault4sqlglot.generators.pit import PITGenerator, PitSatConfig
from datavault4sqlglot.generators.rec_track_sat import RecordTrackingSatGenerator
from datavault4sqlglot.generators.satellite import SatelliteGenerator
from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import SourceModel

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
        source_model=SourceModel(
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
        source_models=[
            SourceModel(
                table_name="stg_orders",
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
        source_models=[
            SourceModel(
                table_name="stg_orders_web",
                hash_key_col="hk_order",
                business_keys=["order_id"],
            ),
            SourceModel(
                table_name="stg_orders_store",
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
        source_models=[
            SourceModel(
                table_name="stg_orders",
                link_hash_key="hk_lnk_order_customer",
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
        source_models=[
            SourceModel(
                table_name="stg_orders",
                hash_key_col="hk_order",
                rsrc_statics=["SAP/ORDERS/%"],
            )
        ],
        parent_hash_key="hk_order",
        hash_diff="hd_order_details",
        payload=["status", "amount", "currency"],
        is_incremental=True,
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 06 — Non-Historized Satellite (incremental)
# ---------------------------------------------------------------------------
write(
    "06_nh_sat_incremental.sql",
    NonHistorizedSatGenerator(
        target_table="nh_sat_order_snapshot",
        target_schema="dv",
        source_model=SourceModel(
            table_name="stg_orders",
            hash_key_col="hk_order",
            payload=["status", "amount"],
        ),
        parent_hash_key="hk_order",
        is_incremental=True,
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 07 — Non-Historized Link (incremental, UNION DISTINCT, rsrc_static HWM)
# ---------------------------------------------------------------------------
write(
    "07_nh_link_incremental.sql",
    NonHistorizedLinkGenerator(
        target_table="nh_lnk_order_product",
        target_schema="dv",
        source_models=[
            SourceModel(
                table_name="stg_order_lines",
                link_hash_key="hk_lnk_order_product",
                foreign_hash_keys=["hk_order", "hk_product"],
                payload=["quantity", "unit_price"],
                rsrc_statics=["SAP/ORDER_LINES/%"],
            )
        ],
        link_hash_key="hk_lnk_order_product",
        is_incremental=True,
        union_strategy="UNION",
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 08 — Multi-Active Satellite v0 (incremental, LAG dedup)
# ---------------------------------------------------------------------------
write(
    "08_ma_sat_v0_incremental.sql",
    MultiActiveSatV0Generator(
        target_table="ma_sat_customer_phones",
        target_schema="dv",
        source_models=[
            SourceModel(
                table_name="stg_customers",
                hash_key_col="hk_customer",
            )
        ],
        parent_hash_key="hk_customer",
        hash_diff="hd_phone",
        payload=["phone_number", "phone_type"],
        is_incremental=True,
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 09 — Multi-Active Satellite v1 (end-dating, is_current flag)
# ---------------------------------------------------------------------------
write(
    "09_ma_sat_v1_end_dating.sql",
    MultiActiveSatV1Generator(
        target_table="ma_sat_v1_customer_phones",
        target_schema="dv",
        sat_v0_table="ma_sat_customer_phones",
        parent_hash_key="hk_customer",
        hash_diff="hd_phone",
        payload=["phone_number", "phone_type"],
        ma_attribute=["phone_type"],
        add_is_current=True,
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 10 — Effectivity Satellite, multi-batch (incremental)
# ---------------------------------------------------------------------------
write(
    "10_eff_sat_multi_batch_incremental.sql",
    EffSatGenerator(
        target_table="eff_sat_order_customer",
        target_schema="dv",
        source_models=[
            SourceModel(
                table_name="stg_orders",
                hash_key_col="hk_lnk_order_customer",
            )
        ],
        tracked_hashkey="hk_lnk_order_customer",
        is_active_alias="is_active",
        is_incremental=True,
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 11 — Effectivity Satellite, single-batch (incremental)
# ---------------------------------------------------------------------------
write(
    "11_eff_sat_single_batch_incremental.sql",
    EffSatGenerator(
        target_table="eff_sat_order_customer",
        target_schema="dv",
        source_models=[
            SourceModel(
                table_name="stg_orders",
                hash_key_col="hk_lnk_order_customer",
            )
        ],
        tracked_hashkey="hk_lnk_order_customer",
        is_active_alias="is_active",
        source_is_single_batch=True,
        is_incremental=True,
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 12 — Point-In-Time table (incremental)
# ---------------------------------------------------------------------------
write(
    "12_pit_incremental.sql",
    PITGenerator(
        target_table="pit_customer",
        target_schema="dv",
        tracked_entity="hub_customer",
        hashkey="hk_customer",
        sat_configs=[
            PitSatConfig(
                name="sat_customer_details",
                table_name="sat_customer_details",
                hashkey="hk_customer",
            ),
            PitSatConfig(
                name="sat_customer_contact",
                table_name="sat_customer_contact",
                hashkey="hk_customer",
                ledts="ledts",
            ),
        ],
        snapshot_relation="snap_dates",
        sdts="sdts",
        dimension_key="pk_pit_customer",
        refer_to_ghost_records=True,
        is_incremental=True,
    ).to_sql(),
)

# ---------------------------------------------------------------------------
# 13 — Record Tracking Satellite (incremental, rsrc_static HWM)
# ---------------------------------------------------------------------------
write(
    "13_rec_track_sat_incremental.sql",
    RecordTrackingSatGenerator(
        target_table="rec_track_order",
        target_schema="dv",
        source_models=[
            SourceModel(
                table_name="stg_orders",
                hash_key_col="hk_order",
                rsrc_statics=["SAP/ORDERS/%"],
            ),
            SourceModel(
                table_name="stg_orders_web",
                hash_key_col="hk_order",
                rsrc_statics=["WEB/ORDERS/%"],
            ),
        ],
        tracked_hashkey="hk_order",
        is_incremental=True,
    ).to_sql(),
)

print("Done.")
