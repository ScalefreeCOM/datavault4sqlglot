"""
SatelliteNHGenerator SQL generation tests.
Run with:  pytest tests/test_satellite_nh.py -v -s
"""
from __future__ import annotations

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.satellite_nh import SatelliteNHGenerator
from datavault4sqlglot.metadata import SourceModel

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
    target_table="ORDER_NH_S",
    parent_hash_key="HK_ORDER_H",
    payload=["ORDER_STATUS", "TOTAL_PRICE"],
)


# ---------------------------------------------------------------------------
# 1. Full load — latest per parent_hk (ROW_NUMBER DESC), no incremental CTEs
# ---------------------------------------------------------------------------
def test_sat_nh_full_load(write_sql):
    gen = SatelliteNHGenerator(**TARGET, source_model=SRC, is_incremental=False)
    sql = gen.to_sql()
    write_sql("NH Sat — Full Load (latest per parent_hk, no HWM)", sql)
    assert "latest_records" in sql
    assert "ROW_NUMBER" in sql.upper()
    assert "DESC" in sql.upper()
    assert "src_new" in sql
    # No HWM subquery
    assert "COALESCE" not in sql
    assert "MAX" not in sql


# ---------------------------------------------------------------------------
# 2. Full load — no hash diff column present
# ---------------------------------------------------------------------------
def test_sat_nh_no_hash_diff(write_sql):
    gen = SatelliteNHGenerator(**TARGET, source_model=SRC, is_incremental=False)
    sql = gen.to_sql()
    write_sql("NH Sat — No hash diff column", sql)
    assert "hd_" not in sql.lower()
    assert "hashdiff" not in sql.lower()


# ---------------------------------------------------------------------------
# 3. Full load — payload columns selected
# ---------------------------------------------------------------------------
def test_sat_nh_payload_columns(write_sql):
    gen = SatelliteNHGenerator(**TARGET, source_model=SRC, is_incremental=False)
    sql = gen.to_sql()
    write_sql("NH Sat — Payload columns present", sql)
    assert "ORDER_STATUS" in sql
    assert "TOTAL_PRICE" in sql


# ---------------------------------------------------------------------------
# 4. Incremental — global HWM filter added
# ---------------------------------------------------------------------------
def test_sat_nh_incremental_hwm(write_sql):
    gen = SatelliteNHGenerator(**TARGET, source_model=SRC, is_incremental=True)
    sql = gen.to_sql()
    write_sql("NH Sat — Incremental (global HWM)", sql)
    assert "MAX" in sql
    assert "COALESCE" in sql
    assert "ORDER_NH_S" in sql


# ---------------------------------------------------------------------------
# 5. Incremental — disable_hwm skips HWM filter
# ---------------------------------------------------------------------------
def test_sat_nh_incremental_disable_hwm(write_sql):
    gen = SatelliteNHGenerator(
        **TARGET, source_model=SRC, is_incremental=True, disable_hwm=True
    )
    sql = gen.to_sql()
    write_sql("NH Sat — Incremental, disable_hwm=True", sql)
    assert "MAX" not in sql
    assert "COALESCE" not in sql
    assert "latest_records" in sql


# ---------------------------------------------------------------------------
# 6. Additional columns carried through
# ---------------------------------------------------------------------------
def test_sat_nh_additional_columns(write_sql):
    gen = SatelliteNHGenerator(
        **TARGET, source_model=SRC, is_incremental=False, additional_columns=["BATCH_ID"]
    )
    sql = gen.to_sql()
    write_sql("NH Sat — additional_columns=[BATCH_ID]", sql)
    assert "BATCH_ID" in sql


# ---------------------------------------------------------------------------
# 7. Config — custom ldts_alias propagates
# ---------------------------------------------------------------------------
def test_sat_nh_custom_ldts_alias(write_sql):
    config.ldts_alias = "load_date"
    src = SourceModel(table_name="stg_orders")
    sql = SatelliteNHGenerator(
        target_table="order_nh_s",
        source_model=src,
        parent_hash_key="hk_order",
        payload=["status"],
    ).to_sql()
    write_sql("NH Sat — custom ldts_alias=load_date", sql)
    assert "load_date" in sql


# ---------------------------------------------------------------------------
# 8. ROW_NUMBER window is DESC (latest, not earliest)
# ---------------------------------------------------------------------------
def test_sat_nh_rownumber_desc(write_sql):
    gen = SatelliteNHGenerator(**TARGET, source_model=SRC, is_incremental=False)
    sql = gen.to_sql()
    write_sql("NH Sat — ROW_NUMBER ORDER BY ldts DESC (latest wins)", sql)
    # DESC must appear after the ldts column reference in the OVER clause
    desc_pos = sql.upper().find("DESC")
    rn_pos = sql.upper().find("ROW_NUMBER")
    assert rn_pos != -1 and desc_pos != -1
    assert desc_pos > rn_pos
