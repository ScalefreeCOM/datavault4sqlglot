import pytest
from datavault4sqlglot import RefHubGenerator
from datavault4sqlglot.metadata import SourceModel

SOURCE = SourceModel(schema="stage", table_name="stg_order_status")
BASE = dict(
    target_table="order_status_rh",
    target_schema="dv",
    source_model=SOURCE,
    business_keys=["status_code"],
    hash_diff_col="hd_order_status_rh",
)


def test_ref_hub_full_load():
    sql = RefHubGenerator(**BASE).to_sql()
    assert "src_new" in sql
    assert "latest_records" in sql
    assert "status_code" in sql
    assert "hd_order_status_rh" in sql


def test_ref_hub_no_hash_key():
    sql = RefHubGenerator(**BASE).to_sql()
    assert "hk_" not in sql


def test_ref_hub_hash_diff_present():
    sql = RefHubGenerator(**BASE).to_sql()
    assert "hd_order_status_rh" in sql


def test_ref_hub_partition_by_business_keys():
    sql = RefHubGenerator(**BASE).to_sql()
    upper = sql.upper()
    assert "PARTITION BY" in upper
    assert "status_code" in sql


def test_ref_hub_order_desc():
    sql = RefHubGenerator(**BASE).to_sql()
    assert "DESC" in sql.upper()


def test_ref_hub_incremental_hwm():
    sql = RefHubGenerator(**{**BASE, "is_incremental": True}).to_sql()
    assert "order_status_rh" in sql.lower()
    assert "MAX" in sql.upper()


def test_ref_hub_disable_hwm():
    sql = RefHubGenerator(**{**BASE, "is_incremental": True, "disable_hwm": True}).to_sql()
    # When disabled, target table must not appear in a subquery context
    lines = [l.strip() for l in sql.splitlines() if "order_status_rh" in l.lower()]
    assert not any("MAX" in l.upper() for l in lines)


def test_ref_hub_multiple_business_keys():
    sql = RefHubGenerator(
        **{**BASE, "business_keys": ["status_code", "region_code"]}
    ).to_sql()
    assert "status_code" in sql
    assert "region_code" in sql


def test_ref_hub_requires_business_keys():
    with pytest.raises(ValueError):
        RefHubGenerator(**{**BASE, "business_keys": []})
