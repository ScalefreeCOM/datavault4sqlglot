"""
EffectivitySatelliteGenerator SQL generation tests.
Run with:  pytest tests/test_effectivity_satellite.py -v -s
"""
from __future__ import annotations

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.effectivity_satellite import EffectivitySatelliteGenerator

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="ORDER_CUSTOMER_EFF_S",
    source_table="ORDER_CUSTOMER_L_S0",
    source_schema="RAW_VAULT",
    source_database="DV_DB",
    parent_hash_key="HK_ORDER_CUSTOMER_L",
    driving_hash_key="HK_ORDER_H",
)


# ---------------------------------------------------------------------------
# 1. Default — ledts computed via LEAD, is_active via CASE
# ---------------------------------------------------------------------------
def test_eff_sat_default(write_sql):
    gen = EffectivitySatelliteGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("Eff Sat — Default (ledts + is_active)", sql)
    assert "LEAD" in sql.upper()
    assert "COALESCE" in sql
    assert "end_dated_source" in sql
    assert "is_active" in sql.lower()


# ---------------------------------------------------------------------------
# 2. LEAD partitions by driving_hash_key
# ---------------------------------------------------------------------------
def test_eff_sat_lead_partition_by_driving_key(write_sql):
    gen = EffectivitySatelliteGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("Eff Sat — LEAD PARTITION BY driving_hash_key", sql)
    lead_pos = sql.upper().find("LEAD")
    partition_pos = sql.upper().find("PARTITION BY", lead_pos)
    hk_pos = sql.upper().find("HK_ORDER_H", partition_pos)
    assert lead_pos != -1 and partition_pos != -1 and hk_pos != -1


# ---------------------------------------------------------------------------
# 3. ledts uses config alias
# ---------------------------------------------------------------------------
def test_eff_sat_ledts_alias(write_sql):
    gen = EffectivitySatelliteGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("Eff Sat — ledts alias from config", sql)
    assert config.ledts_alias in sql


# ---------------------------------------------------------------------------
# 4. is_active: CASE WHEN ledts = eoa THEN TRUE ELSE FALSE
# ---------------------------------------------------------------------------
def test_eff_sat_is_active_logic(write_sql):
    gen = EffectivitySatelliteGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("Eff Sat — is_active CASE logic", sql)
    assert "CASE" in sql.upper()
    assert config.end_of_all_times in sql
    assert "TRUE" in sql.upper() or "true" in sql


# ---------------------------------------------------------------------------
# 5. add_is_active=False — no IS_ACTIVE column
# ---------------------------------------------------------------------------
def test_eff_sat_no_is_active(write_sql):
    gen = EffectivitySatelliteGenerator(**TARGET, add_is_active=False)
    sql = gen.to_sql()
    write_sql("Eff Sat — add_is_active=False", sql)
    assert "is_active" not in sql.lower()


# ---------------------------------------------------------------------------
# 6. Custom is_active_col name
# ---------------------------------------------------------------------------
def test_eff_sat_custom_is_active_col(write_sql):
    gen = EffectivitySatelliteGenerator(**TARGET, is_active_col="currently_active")
    sql = gen.to_sql()
    write_sql("Eff Sat — custom is_active_col=currently_active", sql)
    assert "currently_active" in sql.lower()


# ---------------------------------------------------------------------------
# 7. Custom ledts_alias
# ---------------------------------------------------------------------------
def test_eff_sat_custom_ledts_alias(write_sql):
    gen = EffectivitySatelliteGenerator(**TARGET, ledts_alias="load_end_date")
    sql = gen.to_sql()
    write_sql("Eff Sat — custom ledts_alias=load_end_date", sql)
    assert "load_end_date" in sql.lower()


# ---------------------------------------------------------------------------
# 8. Custom end_of_all_times
# ---------------------------------------------------------------------------
def test_eff_sat_custom_eoa(write_sql):
    gen = EffectivitySatelliteGenerator(**TARGET, end_of_all_times="9999-12-31")
    sql = gen.to_sql()
    write_sql("Eff Sat — custom end_of_all_times=9999-12-31", sql)
    assert "9999-12-31" in sql
