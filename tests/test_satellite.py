"""
Satellite v0 SQL generation — all parameter combinations.
Run with:  pytest tests/test_satellite.py -v -s
"""
from __future__ import annotations

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.satellite import SatelliteGenerator
from datavault4sqlglot.metadata import SourceModel


# ---------------------------------------------------------------------------
# Shared source fixtures
# ---------------------------------------------------------------------------

SRC = SourceModel(
    database="RAW_DB",
    schema="STAGE",
    table_name="STG_ORDERS",
    load_date_col="LOAD_DATE",
    record_source_col="RECORD_SOURCE",
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="SAT_ORDER_DETAILS",
    parent_hash_key="HK_ORDER_H",
    hash_diff="HD_ORDER_DETAILS",
    payload=["ORDER_STATUS", "TOTAL_PRICE", "ORDER_DATE"],
)


# ---------------------------------------------------------------------------
# 1. Full load — LAG/QUALIFY dedup, no incremental CTEs
# ---------------------------------------------------------------------------
def test_sat_v0_full_load(write_sql):
    gen = SatelliteGenerator(**TARGET, source_model=SRC, is_incremental=False)
    sql = gen.to_sql()
    write_sql("Full Load (LAG dedup, no incremental CTEs)", sql)
    assert "deduplicated_numbered_source" in sql
    assert "LAG" in sql
    assert "CASE WHEN" in sql
    assert "latest_entries_in_sat" not in sql
    assert "records_to_insert" not in sql


# ---------------------------------------------------------------------------
# 2. Incremental — global HWM (COALESCE MAX from target) + NOT EXISTS dedup
# ---------------------------------------------------------------------------
def test_sat_v0_incremental_global_hwm(write_sql):
    gen = SatelliteGenerator(**TARGET, source_model=SRC, is_incremental=True)
    sql = gen.to_sql()
    write_sql("Incremental — global HWM (COALESCE MAX from target)", sql)
    assert "latest_entries_in_sat" in sql
    assert "NOT EXISTS" in sql
    assert "records_to_insert" in sql
    assert "COALESCE" in sql


# ---------------------------------------------------------------------------
# 3. Incremental — disable_hwm → skip time filter, keep NOT EXISTS
# ---------------------------------------------------------------------------
def test_sat_v0_incremental_disable_hwm(write_sql):
    gen = SatelliteGenerator(
        **TARGET, source_model=SRC, is_incremental=True, disable_hwm=True
    )
    sql = gen.to_sql()
    write_sql("Incremental — disable_hwm=True (no time filter, NOT EXISTS only)", sql)
    assert "COALESCE" not in sql
    assert "latest_entries_in_sat" in sql
    assert "records_to_insert" in sql


# ---------------------------------------------------------------------------
# 4. hash_diff as dict {source_column, alias}
# ---------------------------------------------------------------------------
def test_sat_v0_hash_diff_dict(write_sql):
    gen = SatelliteGenerator(
        target_database="DV_DB",
        target_schema="RAW_VAULT",
        target_table="SAT_ORDER_DETAILS",
        parent_hash_key="HK_ORDER_H",
        hash_diff={"source_column": "RAW_HASHDIFF", "alias": "HD_ORDER_DETAILS"},
        payload=["ORDER_STATUS", "TOTAL_PRICE"],
        source_model=SRC,
        is_incremental=False,
    )
    sql = gen.to_sql()
    write_sql("hash_diff as dict {source_column: RAW_HASHDIFF, alias: HD_ORDER_DETAILS}", sql)
    assert "RAW_HASHDIFF" in sql
    assert "HD_ORDER_DETAILS" in sql


# ---------------------------------------------------------------------------
# 6. Config — custom ldts_alias propagates
# ---------------------------------------------------------------------------
def test_sat_v0_custom_ldts_alias(write_sql):
    config.ldts_alias = "load_ts"
    src = SourceModel(table_name="stg_orders")
    sql = SatelliteGenerator(
        target_table="sat_orders",
        source_model=src,
        parent_hash_key="hk_order",
        hash_diff="hashdiff",
        is_incremental=True,
    ).to_sql()
    write_sql("Config — custom ldts_alias=load_ts", sql)
    assert "load_ts" in sql


# ---------------------------------------------------------------------------
# 7. Config — custom rsrc_alias propagates
# ---------------------------------------------------------------------------
def test_sat_v0_custom_rsrc_alias(write_sql):
    config.rsrc_alias = "rec_src"
    src = SourceModel(table_name="stg_orders")
    sql = SatelliteGenerator(
        target_table="sat_orders",
        source_model=src,
        parent_hash_key="hk_order",
        hash_diff="hashdiff",
    ).to_sql()
    write_sql("Config — custom rsrc_alias=rec_src", sql)
    assert "rec_src" in sql
