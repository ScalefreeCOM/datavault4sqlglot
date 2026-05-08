"""
PITGenerator SQL generation tests.
Run with:  pytest tests/test_pit.py -v -s
"""
from __future__ import annotations

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.pit import PITGenerator, PitSatellite

SATS = [
    PitSatellite(sat_table="customer_0_s", hub_hash_key="hk_h_customer"),
    PitSatellite(sat_table="customer_1_s", hub_hash_key="hk_h_customer"),
]

TARGET = dict(
    target_database="DV_DB",
    target_schema="MART",
    target_table="customer_pit",
    hub_table="customer_h",
    hub_hash_key="hk_h_customer",
    hub_database="DV_DB",
    hub_schema="RAW_VAULT",
    satellites=SATS,
    snapshot_table="snapshot_dates",
    snapshot_database="DV_DB",
    snapshot_schema="MART",
    snapshot_date_col="snapshot_date",
)


# ---------------------------------------------------------------------------
# 1. CROSS JOIN hub × snapshot_dates
# ---------------------------------------------------------------------------
def test_pit_cross_join(write_sql):
    gen = PITGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("PIT — CROSS JOIN hub × snapshot_dates", sql)
    assert "CROSS JOIN" in sql.upper()
    assert "customer_h" in sql.lower()
    assert "snapshot_dates" in sql.lower()


# ---------------------------------------------------------------------------
# 2. One correlated subquery per satellite
# ---------------------------------------------------------------------------
def test_pit_sat_subqueries(write_sql):
    gen = PITGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("PIT — Satellite correlated subqueries", sql)
    assert "customer_0_s" in sql.lower()
    assert "customer_1_s" in sql.lower()
    assert "customer_0_s_ldts" in sql.lower()
    assert "customer_1_s_ldts" in sql.lower()


# ---------------------------------------------------------------------------
# 3. MAX(ldts) capped at snapshot_date
# ---------------------------------------------------------------------------
def test_pit_max_ldts_capped(write_sql):
    gen = PITGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("PIT — MAX(ldts) <= snapshot_date", sql)
    assert "MAX" in sql.upper()
    assert "snapshot_date" in sql.lower()


# ---------------------------------------------------------------------------
# 4. COALESCE with beginning_of_all_times (ghost record)
# ---------------------------------------------------------------------------
def test_pit_ghost_record(write_sql):
    gen = PITGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("PIT — COALESCE with BOA ghost record", sql)
    assert "COALESCE" in sql.upper()
    assert config.beginning_of_all_times in sql


# ---------------------------------------------------------------------------
# 5. hub_hash_key appears in SELECT
# ---------------------------------------------------------------------------
def test_pit_hub_hash_key_selected(write_sql):
    gen = PITGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("PIT — hub_hash_key in SELECT", sql)
    assert "hk_h_customer" in sql.lower()


# ---------------------------------------------------------------------------
# 6. Custom alias on PitSatellite
# ---------------------------------------------------------------------------
def test_pit_custom_alias(write_sql):
    custom_sat = PitSatellite(
        sat_table="customer_0_s",
        hub_hash_key="hk_h_customer",
        alias="cust_sat_v0_ldts",
    )
    gen = PITGenerator(**{**TARGET, "satellites": [custom_sat]})
    sql = gen.to_sql()
    write_sql("PIT — custom satellite alias", sql)
    assert "cust_sat_v0_ldts" in sql.lower()


# ---------------------------------------------------------------------------
# 7. PitSatellite default alias
# ---------------------------------------------------------------------------
def test_pit_satellite_default_alias():
    sat = PitSatellite(sat_table="my_sat_table", hub_hash_key="hk")
    assert sat.alias == "my_sat_table_ldts"
