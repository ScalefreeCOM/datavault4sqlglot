"""
Point-In-Time (PIT) table SQL generation — all parameter combinations.
Run with:  pytest tests/test_pit.py -v -s
"""
from __future__ import annotations

import inspect
from pathlib import Path

from datavault4sqlglot.generators.pit import PITGenerator, PitSatConfig

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"


def _print(label: str, sql: str) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    caller = inspect.currentframe().f_back.f_code.co_name
    (_OUT_DIR / f"{caller}.sql").write_text(
        f"-- PIT -- {label}\n\n{sql}\n", encoding="utf-8"
    )
    print(f"\n{'='*70}\nPIT -- {label}\n{'='*70}\n{sql}\n")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAT_DETAILS = PitSatConfig(
    name="sat_customer_details",
    table_name="SAT_CUSTOMER_DETAILS",
    hashkey="HK_CUSTOMER_H",
    schema_name="RAW_VAULT",
    database="DV_DB",
)

SAT_CONTACT = PitSatConfig(
    name="sat_customer_contact",
    table_name="SAT_CUSTOMER_CONTACT",
    hashkey="HK_CUSTOMER_H",
    schema_name="RAW_VAULT",
    database="DV_DB",
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="BUSINESS_VAULT",
    target_table="PIT_CUSTOMER",
    tracked_entity="HUB_CUSTOMER",
    tracked_entity_database="DV_DB",
    tracked_entity_schema="RAW_VAULT",
    hashkey="HK_CUSTOMER_H",
    snapshot_relation="SNAP_DATES",
    snapshot_schema="CONTROL",
    snapshot_database="DV_DB",
    sdts="SDTS",
    dimension_key="DIM_CUSTOMER_KEY",
)


# ---------------------------------------------------------------------------
# 1. Full load — 2 satellites, ghost records enabled
# ---------------------------------------------------------------------------
def test_pit_full_load_ghost_records():
    gen = PITGenerator(
        **TARGET,
        sat_configs=[SAT_DETAILS, SAT_CONTACT],
        refer_to_ghost_records=True,
        is_incremental=False,
    )
    sql = gen.to_sql()
    _print("Full Load — 2 sats, refer_to_ghost_records=True (COALESCE to ghost key)", sql)
    assert "pit_records" in sql
    assert "COALESCE" in sql
    assert "FULL OUTER JOIN" in sql
    assert sql.count("LEFT JOIN") == 2


# ---------------------------------------------------------------------------
# 2. Full load — 2 satellites, no ghost records
# ---------------------------------------------------------------------------
def test_pit_full_load_no_ghost_records():
    gen = PITGenerator(
        **TARGET,
        sat_configs=[SAT_DETAILS, SAT_CONTACT],
        refer_to_ghost_records=False,
        is_incremental=False,
    )
    sql = gen.to_sql()
    _print("Full Load — 2 sats, refer_to_ghost_records=False (NULL for missing sat entry)", sql)
    assert "pit_records" in sql
    assert "BETWEEN" in sql
    assert "LEAD" in sql


# ---------------------------------------------------------------------------
# 3. Full load — single satellite
# ---------------------------------------------------------------------------
def test_pit_full_load_single_sat():
    gen = PITGenerator(
        **TARGET,
        sat_configs=[SAT_DETAILS],
        refer_to_ghost_records=True,
        is_incremental=False,
    )
    sql = gen.to_sql()
    _print("Full Load — Single Satellite", sql)
    assert "sat_customer_details" in sql
    assert "sat_customer_contact" not in sql


# ---------------------------------------------------------------------------
# 4. Incremental — existing dimension keys excluded via NOT IN
# ---------------------------------------------------------------------------
def test_pit_incremental():
    gen = PITGenerator(
        **TARGET,
        sat_configs=[SAT_DETAILS, SAT_CONTACT],
        refer_to_ghost_records=True,
        is_incremental=True,
    )
    sql = gen.to_sql()
    _print("Incremental — existing_dimension_keys CTE, NOT IN filter on SDTS", sql)
    assert "existing_dimension_keys" in sql
    assert "NOT" in sql

# ---------------------------------------------------------------------------
# 5. Full load — schema-qualified snapshot + entity table
# ---------------------------------------------------------------------------
def test_pit_full_load_schema_qualified():
    gen = PITGenerator(
        target_database="DV_DB",
        target_schema="BUSINESS_VAULT",
        target_table="PIT_CUSTOMER",
        tracked_entity="HUB_CUSTOMER",
        tracked_entity_database="DV_DB",
        tracked_entity_schema="RAW_VAULT",
        hashkey="HK_CUSTOMER_H",
        sat_configs=[SAT_DETAILS, SAT_CONTACT],
        snapshot_relation="SNAP_DATES",
        snapshot_schema="CONTROL",
        snapshot_database="DV_DB",
        sdts="SDTS",
        dimension_key="DIM_CUSTOMER_KEY",
        refer_to_ghost_records=False,
        is_incremental=False,
    )
    sql = gen.to_sql()
    _print("Full Load — fully schema-qualified (DB.SCHEMA.TABLE throughout)", sql)
    assert "DV_DB" in sql
    assert "RAW_VAULT" in sql
    assert "CONTROL" in sql


# ---------------------------------------------------------------------------
# 6. Satellite with pre-existing ledts column — skip LEAD computation
# ---------------------------------------------------------------------------
def test_pit_satellite_with_existing_ledts():
    sat_v1 = PitSatConfig(
        name="sat_v1",
        table_name="SAT_CUSTOMER_DETAILS_V1",
        hashkey="HK_CUSTOMER_H",
        ledts="ledts",
    )
    gen = PITGenerator(
        target_table="PIT_CUSTOMER",
        tracked_entity="HUB_CUSTOMER",
        hashkey="HK_CUSTOMER_H",
        sat_configs=[sat_v1],
        snapshot_relation="SNAP_DATES",
        sdts="SDTS",
        dimension_key="DIM_CUSTOMER_KEY",
    )
    sql = gen.to_sql()
    _print("Satellite with ledts column — BETWEEN uses ledts directly, no LEAD", sql)
    assert "ledts" in sql


# ---------------------------------------------------------------------------
# 7. Dimension key hash + BETWEEN ldts/ledts
# ---------------------------------------------------------------------------
def test_pit_dimension_key_and_between():
    gen = PITGenerator(
        target_table="pit_orders",
        tracked_entity="hub_orders",
        hashkey="hk_order",
        sat_configs=[
            PitSatConfig(name="sat_orders", table_name="sat_orders", hashkey="hk_order"),
            PitSatConfig(name="sat_details", table_name="sat_orders_details", hashkey="hk_order"),
        ],
        snapshot_relation="snap_dates",
        sdts="sdts",
        dimension_key="pk_pit",
    )
    sql = gen.to_sql()
    _print("Dimension key hash + BETWEEN ldts/ledts", sql)
    assert "pk_pit" in sql
    assert "BETWEEN" in sql
