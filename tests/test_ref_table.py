"""
RefTableGenerator SQL generation tests.
Run with:  pytest tests/test_ref_table.py -v -s
"""
from __future__ import annotations

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.ref_table import RefTableGenerator
from datavault4sqlglot.metadata import SourceModel

SRC = SourceModel(
    database="RAW_DB",
    schema="STAGE",
    table_name="STG_ORDER_STATUS",
    load_date_col="LOAD_DATE",
    record_source_col="RECORD_SOURCE",
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="ORDER_STATUS_R",
    ref_hash_key="HK_ORDER_STATUS_R",
    ref_key_columns=["STATUS_CODE"],
    payload=["STATUS_DESCRIPTION"],
    source_model=SRC,
)


# ---------------------------------------------------------------------------
# 1. Full load — latest per ref_hash_key (ROW_NUMBER DESC), no incremental CTEs
# ---------------------------------------------------------------------------
def test_ref_table_full_load(write_sql):
    gen = RefTableGenerator(**TARGET, is_incremental=False)
    sql = gen.to_sql()
    write_sql("Ref Table — Full Load (latest per ref_hk, no HWM)", sql)
    assert "latest_records" in sql
    assert "ROW_NUMBER" in sql.upper()
    assert "DESC" in sql.upper()
    assert "src_new" in sql
    assert "COALESCE" not in sql
    assert "MAX" not in sql


# ---------------------------------------------------------------------------
# 2. No hash diff column present
# ---------------------------------------------------------------------------
def test_ref_table_no_hash_diff(write_sql):
    gen = RefTableGenerator(**TARGET, is_incremental=False)
    sql = gen.to_sql()
    write_sql("Ref Table — No hash diff column", sql)
    assert "hd_" not in sql.lower()
    assert "hashdiff" not in sql.lower()


# ---------------------------------------------------------------------------
# 3. ref_hash_key and payload columns present
# ---------------------------------------------------------------------------
def test_ref_table_columns_present(write_sql):
    gen = RefTableGenerator(**TARGET, is_incremental=False)
    sql = gen.to_sql()
    write_sql("Ref Table — ref_hash_key and payload present", sql)
    assert "HK_ORDER_STATUS_R" in sql
    assert "STATUS_CODE" in sql
    assert "STATUS_DESCRIPTION" in sql


# ---------------------------------------------------------------------------
# 4. ref_hash_key used as PARTITION BY
# ---------------------------------------------------------------------------
def test_ref_table_partition_by_ref_hk(write_sql):
    gen = RefTableGenerator(**TARGET, is_incremental=False)
    sql = gen.to_sql()
    write_sql("Ref Table — PARTITION BY ref_hash_key", sql)
    partition_pos = sql.upper().find("PARTITION BY")
    hk_pos = sql.upper().find("HK_ORDER_STATUS_R", partition_pos)
    assert partition_pos != -1 and hk_pos != -1


# ---------------------------------------------------------------------------
# 5. Incremental — global HWM filter added
# ---------------------------------------------------------------------------
def test_ref_table_incremental_hwm(write_sql):
    gen = RefTableGenerator(**TARGET, is_incremental=True)
    sql = gen.to_sql()
    write_sql("Ref Table — Incremental (global HWM)", sql)
    assert "MAX" in sql
    assert "COALESCE" in sql
    assert "ORDER_STATUS_R" in sql


# ---------------------------------------------------------------------------
# 6. disable_hwm — skips HWM filter
# ---------------------------------------------------------------------------
def test_ref_table_incremental_disable_hwm(write_sql):
    gen = RefTableGenerator(**TARGET, is_incremental=True, disable_hwm=True)
    sql = gen.to_sql()
    write_sql("Ref Table — Incremental, disable_hwm=True", sql)
    assert "MAX" not in sql
    assert "COALESCE" not in sql
    assert "latest_records" in sql


# ---------------------------------------------------------------------------
# 7. No ref_key_columns — only hash key and payload
# ---------------------------------------------------------------------------
def test_ref_table_no_ref_key_columns(write_sql):
    gen = RefTableGenerator(
        target_table="ORDER_STATUS_R",
        source_model=SRC,
        ref_hash_key="HK_ORDER_STATUS_R",
        payload=["STATUS_DESCRIPTION"],
        is_incremental=False,
    )
    sql = gen.to_sql()
    write_sql("Ref Table — No ref_key_columns, only hash + payload", sql)
    assert "HK_ORDER_STATUS_R" in sql
    assert "STATUS_DESCRIPTION" in sql


# ---------------------------------------------------------------------------
# 8. Additional columns carried through
# ---------------------------------------------------------------------------
def test_ref_table_additional_columns(write_sql):
    gen = RefTableGenerator(**TARGET, is_incremental=False, additional_columns=["BATCH_ID"])
    sql = gen.to_sql()
    write_sql("Ref Table — additional_columns=[BATCH_ID]", sql)
    assert "BATCH_ID" in sql


# ---------------------------------------------------------------------------
# 9. Custom ldts_alias propagates
# ---------------------------------------------------------------------------
def test_ref_table_custom_ldts_alias(write_sql):
    config.ldts_alias = "load_date"
    src = SourceModel(table_name="stg_order_status")
    gen = RefTableGenerator(
        target_table="order_status_r",
        source_model=src,
        ref_hash_key="hk_order_status_r",
        payload=["status_desc"],
    )
    sql = gen.to_sql()
    write_sql("Ref Table — custom ldts_alias=load_date", sql)
    assert "load_date" in sql
