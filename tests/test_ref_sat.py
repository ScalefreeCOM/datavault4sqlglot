import pytest
from datavault4sqlglot import RefSatGenerator
from datavault4sqlglot.metadata import SourceModel

SOURCE = SourceModel(schema="stage", table_name="stg_order_status")
BASE = dict(
    target_table="order_status_rs",
    target_schema="dv",
    source_model=SOURCE,
    business_keys=["status_code"],
    hash_diff_col="hd_order_status_rs",
    payload=["status_description"],
)


def test_ref_sat_full_load():
    sql = RefSatGenerator(**BASE).to_sql()
    assert "src_new" in sql
    assert "latest_records" in sql
    assert "status_code" in sql
    assert "status_description" in sql
    assert "hd_order_status_rs" in sql


def test_ref_sat_no_hash_key():
    sql = RefSatGenerator(**BASE).to_sql()
    assert "hk_" not in sql


def test_ref_sat_payload_present():
    sql = RefSatGenerator(**BASE).to_sql()
    assert "status_description" in sql


def test_ref_sat_hash_diff_present():
    sql = RefSatGenerator(**BASE).to_sql()
    assert "hd_order_status_rs" in sql


def test_ref_sat_partition_by_business_keys():
    sql = RefSatGenerator(**BASE).to_sql()
    assert "PARTITION BY" in sql.upper()
    assert "status_code" in sql


def test_ref_sat_order_desc():
    sql = RefSatGenerator(**BASE).to_sql()
    assert "DESC" in sql.upper()


def test_ref_sat_incremental_hwm():
    sql = RefSatGenerator(**{**BASE, "is_incremental": True}).to_sql()
    assert "order_status_rs" in sql.lower()
    assert "MAX" in sql.upper()


def test_ref_sat_disable_hwm():
    sql = RefSatGenerator(**{**BASE, "is_incremental": True, "disable_hwm": True}).to_sql()
    lines = [l.strip() for l in sql.splitlines() if "order_status_rs" in l.lower()]
    assert not any("MAX" in l.upper() for l in lines)


def test_ref_sat_requires_business_keys():
    with pytest.raises(ValueError):
        RefSatGenerator(**{**BASE, "business_keys": []})
