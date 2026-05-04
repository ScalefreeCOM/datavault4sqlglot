"""
Effectivity Satellite SQL generation — all parameter combinations.
Run with:  pytest tests/test_eff_sat.py -v -s
"""
from __future__ import annotations

import inspect
from pathlib import Path

from datavault4sqlglot.generators.eff_sat import EffSatGenerator
from datavault4sqlglot.metadata import SourceModel

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"


def _print(label: str, sql: str) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    caller = inspect.currentframe().f_back.f_code.co_name
    (_OUT_DIR / f"{caller}.sql").write_text(
        f"-- EFF-SAT -- {label}\n\n{sql}\n", encoding="utf-8"
    )
    print(f"\n{'='*70}\nEFF-SAT -- {label}\n{'='*70}\n{sql}\n")


SRC = SourceModel(
    database="RAW_DB",
    schema="STAGE",
    table_name="STG_ORDER_CUSTOMER",
    load_date_col="LOAD_DATE",
    record_source_col="RECORD_SOURCE",
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="EFF_SAT_ORDER_CUSTOMER",
    tracked_hashkey="HK_ORDER_CUSTOMER_L",
)


# ---------------------------------------------------------------------------
# 1. Multi-batch full load — CROSS JOIN history × load_dates, LAG dedup
# ---------------------------------------------------------------------------
def test_eff_sat_multi_batch_full_load():
    gen = EffSatGenerator(**TARGET, source_model=SRC, source_is_single_batch=False, is_incremental=False)
    sql = gen.to_sql()
    _print("Multi-Batch Full Load (CROSS JOIN history x load_dates, LAG dedup)", sql)
    assert "source_data" in sql
    assert "hashkeys" in sql
    assert "load_dates" in sql
    assert "history" in sql
    assert "is_active" in sql
    assert "deduplicated_incoming" in sql
    assert "records_to_insert" in sql
    assert "CROSS JOIN" in sql
    assert "LAG" in sql
    assert "QUALIFY" in sql
    assert "BOOLEAN" in sql


# ---------------------------------------------------------------------------
# 2. Single-batch full load — new_hashkeys only, no CROSS JOIN
# ---------------------------------------------------------------------------
def test_eff_sat_single_batch_full_load():
    gen = EffSatGenerator(**TARGET, source_model=SRC, source_is_single_batch=True, is_incremental=False)
    sql = gen.to_sql()
    _print("Single-Batch Full Load (new_hashkeys, every key -> is_active=1)", sql)
    assert "new_hashkeys" in sql
    assert "CROSS JOIN" not in sql
    assert "load_dates" not in sql
    assert "deduplicated_incoming" not in sql


# ---------------------------------------------------------------------------
# 3. Multi-batch incremental — current_status CTE, disappeared_hashkeys → is_active=0
# ---------------------------------------------------------------------------
def test_eff_sat_multi_batch_incremental():
    gen = EffSatGenerator(**TARGET, source_model=SRC, source_is_single_batch=False, is_incremental=True)
    sql = gen.to_sql()
    _print("Multi-Batch Incremental (current_status, disappeared_hashkeys -> is_active=0)", sql)
    assert "current_status" in sql
    assert "disappeared_hashkeys" in sql
    assert "NOT EXISTS" in sql


# ---------------------------------------------------------------------------
# 4. Single-batch incremental — new/reactivated keys + disappeared keys
# ---------------------------------------------------------------------------
def test_eff_sat_single_batch_incremental():
    gen = EffSatGenerator(**TARGET, source_model=SRC, source_is_single_batch=True, is_incremental=True)
    sql = gen.to_sql()
    _print("Single-Batch Incremental (LEFT JOIN current_status, disappeared -> is_active=0)", sql)
    assert "current_status" in sql
    assert "new_hashkeys" in sql
    assert "disappeared_hashkeys" in sql


# ---------------------------------------------------------------------------
# 5. Incremental — disable_hwm: skip time filter, keep current_status
# ---------------------------------------------------------------------------
def test_eff_sat_incremental_disable_hwm():
    gen = EffSatGenerator(
        **TARGET, source_model=SRC, source_is_single_batch=False,
        is_incremental=True, disable_hwm=True,
    )
    sql = gen.to_sql()
    _print("Multi-Batch Incremental, disable_hwm=True (no time filter on source_data)", sql)
    assert "current_status" in sql
    assert "beginning_of_all_times" not in sql
    assert "COALESCE(MAX" not in sql


# ---------------------------------------------------------------------------
# 6. Additional columns carried through all CTEs
# ---------------------------------------------------------------------------
def test_eff_sat_additional_columns():
    gen = EffSatGenerator(
        **TARGET, source_model=SRC, source_is_single_batch=False,
        is_incremental=False, additional_columns=["CONTRACT_ID", "REGION"],
    )
    sql = gen.to_sql()
    _print("Full Load — additional_columns=[CONTRACT_ID, REGION]", sql)
    assert "CONTRACT_ID" in sql
    assert "REGION" in sql


# ---------------------------------------------------------------------------
# 7. Incremental HWM uses COALESCE to handle empty target on first load
# ---------------------------------------------------------------------------
def test_eff_sat_hwm_coalesce():
    gen = EffSatGenerator(
        **TARGET,
        source_model=SRC,
        is_incremental=True,
        beginning_of_all_times="1970-01-01 00:00:00",
    )
    sql = gen.to_sql()
    _print("Incremental HWM — COALESCE(MAX(ldts), boa) handles empty target", sql)
    assert "COALESCE" in sql
    assert "1970-01-01 00:00:00" in sql
