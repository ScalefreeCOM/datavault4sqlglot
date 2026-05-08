"""
LinkNHGenerator SQL generation tests.
Run with:  pytest tests/test_link_nh.py -v -s
"""
from __future__ import annotations

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.link_nh import LinkNHGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel

SRC = SourceModel(
    database="RAW_DB",
    schema="STAGE",
    table_name="STG_ORDERS",
    load_date_col="LOAD_DATE",
    record_source_col="RECORD_SOURCE",
)

BINDING = SourceBinding(
    source=SRC,
    foreign_hash_keys=["HK_ORDER_H", "HK_CUSTOMER_H"],
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="ORDER_CUSTOMER_NH_L",
    link_hash_key="HK_ORDER_CUSTOMER_L",
    driving_hash_key="HK_ORDER_H",
    sources=[BINDING],
)


# ---------------------------------------------------------------------------
# 1. Full load — ROW_NUMBER DESC, no incremental CTEs
# ---------------------------------------------------------------------------
def test_link_nh_full_load(write_sql):
    gen = LinkNHGenerator(**TARGET, is_incremental=False)
    sql = gen.to_sql()
    write_sql("NH Link — Full Load (latest per driving_hk, no HWM)", sql)
    assert "latest_records" in sql
    assert "ROW_NUMBER" in sql.upper()
    assert "DESC" in sql.upper()
    assert "src_new_0" in sql
    # No HWM subquery
    assert "COALESCE" not in sql
    assert "MAX" not in sql


# ---------------------------------------------------------------------------
# 2. No hash diff column in output
# ---------------------------------------------------------------------------
def test_link_nh_no_hash_diff(write_sql):
    gen = LinkNHGenerator(**TARGET, is_incremental=False)
    sql = gen.to_sql()
    write_sql("NH Link — No hash diff column", sql)
    assert "hd_" not in sql.lower()
    assert "hashdiff" not in sql.lower()


# ---------------------------------------------------------------------------
# 3. Foreign hash keys present
# ---------------------------------------------------------------------------
def test_link_nh_foreign_keys_present(write_sql):
    gen = LinkNHGenerator(**TARGET, is_incremental=False)
    sql = gen.to_sql()
    write_sql("NH Link — Foreign hash keys present", sql)
    assert "HK_ORDER_H" in sql
    assert "HK_CUSTOMER_H" in sql
    assert "HK_ORDER_CUSTOMER_L" in sql


# ---------------------------------------------------------------------------
# 4. Driving key used as PARTITION BY
# ---------------------------------------------------------------------------
def test_link_nh_driving_key_partition(write_sql):
    gen = LinkNHGenerator(**TARGET, is_incremental=False)
    sql = gen.to_sql()
    write_sql("NH Link — driving_hash_key used for PARTITION BY", sql)
    partition_pos = sql.upper().find("PARTITION BY")
    driving_pos = sql.upper().find("HK_ORDER_H", partition_pos)
    assert partition_pos != -1
    assert driving_pos != -1


# ---------------------------------------------------------------------------
# 5. Defaults: driving_hash_key falls back to link_hash_key
# ---------------------------------------------------------------------------
def test_link_nh_driving_key_defaults_to_link_hk(write_sql):
    gen = LinkNHGenerator(
        target_table="ORDER_CUSTOMER_NH_L",
        sources=[BINDING],
        link_hash_key="HK_ORDER_CUSTOMER_L",
        is_incremental=False,
    )
    sql = gen.to_sql()
    write_sql("NH Link — driving_hash_key defaults to link_hash_key", sql)
    # PARTITION BY should reference the link hash key
    partition_pos = sql.upper().find("PARTITION BY")
    lhk_pos = sql.upper().find("HK_ORDER_CUSTOMER_L", partition_pos)
    assert partition_pos != -1 and lhk_pos != -1


# ---------------------------------------------------------------------------
# 6. Incremental — global HWM filter added
# ---------------------------------------------------------------------------
def test_link_nh_incremental_hwm(write_sql):
    gen = LinkNHGenerator(**TARGET, is_incremental=True)
    sql = gen.to_sql()
    write_sql("NH Link — Incremental (global HWM)", sql)
    assert "MAX" in sql
    assert "COALESCE" in sql
    assert "ORDER_CUSTOMER_NH_L" in sql


# ---------------------------------------------------------------------------
# 7. disable_hwm — skips HWM filter
# ---------------------------------------------------------------------------
def test_link_nh_incremental_disable_hwm(write_sql):
    gen = LinkNHGenerator(**TARGET, is_incremental=True, disable_hwm=True)
    sql = gen.to_sql()
    write_sql("NH Link — Incremental, disable_hwm=True", sql)
    assert "MAX" not in sql
    assert "COALESCE" not in sql
    assert "latest_records" in sql


# ---------------------------------------------------------------------------
# 8. Additional columns carried through
# ---------------------------------------------------------------------------
def test_link_nh_additional_columns(write_sql):
    gen = LinkNHGenerator(
        **TARGET,
        is_incremental=False,
        additional_columns=["BATCH_ID"],
    )
    sql = gen.to_sql()
    write_sql("NH Link — additional_columns=[BATCH_ID]", sql)
    assert "BATCH_ID" in sql


# ---------------------------------------------------------------------------
# 9. Error when fewer than 2 foreign hash keys
# ---------------------------------------------------------------------------
def test_link_nh_requires_two_foreign_keys():
    import pytest
    bad_binding = SourceBinding(source=SRC, foreign_hash_keys=["HK_ORDER_H"])
    gen = LinkNHGenerator(
        target_table="bad_l",
        sources=[bad_binding],
        link_hash_key="hk_bad_l",
    )
    with pytest.raises(ValueError, match="at least 2 foreign_hash_keys"):
        gen.to_sql()
