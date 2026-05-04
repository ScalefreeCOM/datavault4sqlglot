"""
Satellite v1 SQL generation — end-dated view on top of a sat_v0 table.

Mirrors the datavault4dbt sat_v1 macro which computes:
  ledts = COALESCE(LEAD(ldts) OVER (PARTITION BY parent_hk ORDER BY ldts), end_of_all_times)
  is_current = CASE WHEN ledts = end_of_all_times THEN TRUE ELSE FALSE END

Run with:  pytest tests/test_sat_v1.py -v -s
"""
from __future__ import annotations

import inspect
from pathlib import Path

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.sat_v1 import SatelliteV1Generator

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"


def _print(label: str, sql: str) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    caller = inspect.currentframe().f_back.f_code.co_name
    (_OUT_DIR / f"{caller}.sql").write_text(
        f"-- SAT v1 -- {label}\n\n{sql}\n", encoding="utf-8"
    )
    print(f"\n{'='*70}\nSAT v1 -- {label}\n{'='*70}\n{sql}\n")


def _gen(**kwargs: object) -> SatelliteV1Generator:
    defaults: dict[str, object] = dict(
        target_table="sat_orders_v1",
        sat_v0_table="sat_orders",
        parent_hash_key="hk_order",
        hash_diff="hashdiff",
        payload=["status", "amount"],
    )
    defaults.update(kwargs)
    return SatelliteV1Generator(**defaults)


# ---------------------------------------------------------------------------
# 1. Default: LEAD → ledts + is_current flag
# ---------------------------------------------------------------------------
def test_sat_v1_default():
    gen = SatelliteV1Generator(
        target_database="DV_DB",
        target_schema="RAW_VAULT",
        target_table="SAT_ORDER_DETAILS_V1",
        sat_v0_database="DV_DB",
        sat_v0_schema="RAW_VAULT",
        sat_v0_table="SAT_ORDER_DETAILS",
        parent_hash_key="HK_ORDER_H",
        hash_diff="HD_ORDER_DETAILS",
        payload=["ORDER_STATUS", "TOTAL_PRICE", "ORDER_DATE"],
    )
    sql = gen.to_sql()
    _print("Default — LEAD window for ledts, is_current flag", sql)
    assert "end_dated_source" in sql
    assert "LEAD" in sql
    assert "is_current" in sql
    assert "COALESCE" in sql
    assert "PARTITION BY" in sql


# ---------------------------------------------------------------------------
# 2. No is_current flag
# ---------------------------------------------------------------------------
def test_sat_v1_no_is_current():
    gen = _gen(add_is_current=False)
    sql = gen.to_sql()
    _print("add_is_current=False (only ledts, no flag)", sql)
    assert "LEAD" in sql
    assert "is_current" not in sql


# ---------------------------------------------------------------------------
# 3. Custom ledts_alias + custom is_current column name
# ---------------------------------------------------------------------------
def test_sat_v1_custom_aliases():
    gen = SatelliteV1Generator(
        target_database="DV_DB",
        target_schema="RAW_VAULT",
        target_table="SAT_ORDER_DETAILS_V1",
        sat_v0_database="DV_DB",
        sat_v0_schema="RAW_VAULT",
        sat_v0_table="SAT_ORDER_DETAILS",
        parent_hash_key="HK_ORDER_H",
        hash_diff="HD_ORDER_DETAILS",
        ledts_alias="LOAD_END_DATE",
        is_current_col="IS_LATEST",
    )
    sql = gen.to_sql()
    _print("Custom ledts_alias=LOAD_END_DATE, is_current_col=IS_LATEST", sql)
    assert "LOAD_END_DATE" in sql
    assert "IS_LATEST" in sql


# ---------------------------------------------------------------------------
# 4. LEAD partitioned by parent_hk, ordered by ldts
# ---------------------------------------------------------------------------
def test_sat_v1_lead_window_structure():
    sql = _gen().to_sql()
    _print("LEAD window partitioned by parent_hk, ordered by ldts", sql)
    assert "LEAD" in sql
    assert "hk_order" in sql
    assert "PARTITION BY" in sql
    assert "ORDER BY" in sql


# ---------------------------------------------------------------------------
# 5. COALESCE wraps LEAD with end_of_all_times
# ---------------------------------------------------------------------------
def test_sat_v1_coalesce_lead_with_eoa():
    sql = _gen(end_of_all_times="9999-12-31").to_sql()
    _print("COALESCE wraps LEAD result with end_of_all_times=9999-12-31", sql)
    assert "COALESCE" in sql
    assert "9999-12-31" in sql


# ---------------------------------------------------------------------------
# 6. Custom end_of_all_times appears in both COALESCE and is_current CASE
# ---------------------------------------------------------------------------
def test_sat_v1_custom_end_of_all_times():
    sql = _gen(end_of_all_times="2099-12-31").to_sql()
    _print("custom end_of_all_times=2099-12-31 in COALESCE + is_current CASE", sql)
    assert sql.count("2099-12-31") >= 2


# ---------------------------------------------------------------------------
# 7. is_current = TRUE when ledts equals end_of_all_times
# ---------------------------------------------------------------------------
def test_sat_v1_is_current_logic():
    sql = _gen(end_of_all_times="9999-12-31").to_sql()
    _print("is_current CASE: TRUE when ledts = end_of_all_times", sql)
    assert "CASE" in sql
    assert "9999-12-31" in sql
    assert "TRUE" in sql.upper() or "true" in sql


# ---------------------------------------------------------------------------
# 8. Config — ledts_alias from config
# ---------------------------------------------------------------------------
def test_sat_v1_ledts_alias_from_config():
    config.ledts_alias = "end_date"
    sql = _gen().to_sql()
    _print("config.ledts_alias=end_date used when ledts_alias not set explicitly", sql)
    assert "end_date" in sql


# ---------------------------------------------------------------------------
# 9. Source table — schema and database qualification
# ---------------------------------------------------------------------------
def test_sat_v1_sat_v0_fully_qualified():
    sql = _gen(sat_v0_database="my_db", sat_v0_schema="raw_vault").to_sql()
    _print("sat_v0 fully qualified: my_db.raw_vault.sat_orders", sql)
    assert "my_db" in sql
    assert "raw_vault" in sql
    assert "sat_orders" in sql
