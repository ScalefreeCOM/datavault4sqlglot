"""
Multi-Active Satellite (v0 + v1) SQL generation — all parameter combinations.
Run with:  pytest tests/test_ma_sat.py -v -s
"""
from __future__ import annotations

import inspect
from pathlib import Path

from datavault4sqlglot.generators.ma_sat_v0 import MultiActiveSatV0Generator
from datavault4sqlglot.generators.ma_sat_v1 import MultiActiveSatV1Generator
from datavault4sqlglot.metadata import SourceModel

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"


def _print(label: str, sql: str) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    caller = inspect.currentframe().f_back.f_code.co_name
    (_OUT_DIR / f"{caller}.sql").write_text(
        f"-- MA-SAT -- {label}\n\n{sql}\n", encoding="utf-8"
    )
    print(f"\n{'='*70}\nMA-SAT -- {label}\n{'='*70}\n{sql}\n")


# ---------------------------------------------------------------------------
# Shared source / target fixtures
# ---------------------------------------------------------------------------

SRC = SourceModel(
    database="RAW_DB",
    schema="STAGE",
    table_name="STG_CUSTOMER_PHONES",
    load_date_col="LOAD_DATE",
    record_source_col="RECORD_SOURCE",
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="MA_SAT_CUSTOMER_PHONES",
    parent_hash_key="HK_CUSTOMER_H",
    hash_diff="HD_CUSTOMER_PHONES",
    payload=["PHONE_NUMBER", "IS_PRIMARY"],
)


# ===========================================================================
# MA-SAT v0
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Full load — LAG dedup, INNER JOIN to recover payload
# ---------------------------------------------------------------------------
def test_ma_sat_v0_full_load():
    gen = MultiActiveSatV0Generator(**TARGET, source_model=SRC, is_incremental=False)
    sql = gen.to_sql()
    _print("v0 — Full Load (LAG dedup, INNER JOIN to recover payload)", sql)
    assert "deduped_row_hashdiff" in sql
    assert "deduped_rows" in sql
    assert "INNER JOIN" in sql
    assert "LAG" in sql
    assert "QUALIFY" in sql
    assert "latest_entries_in_sat" not in sql


# ---------------------------------------------------------------------------
# 2. Incremental — global HWM (COALESCE MAX) + NOT EXISTS dedup
# ---------------------------------------------------------------------------
def test_ma_sat_v0_incremental():
    gen = MultiActiveSatV0Generator(**TARGET, source_model=SRC, is_incremental=True)
    sql = gen.to_sql()
    _print("v0 — Incremental (global HWM, NOT EXISTS on parent_hk + hashdiff)", sql)
    assert "latest_entries_in_sat" in sql
    assert "NOT EXISTS" in sql
    assert "COALESCE" in sql
    assert "records_to_insert" in sql


# ---------------------------------------------------------------------------
# 3. Incremental — disable_hwm → skip time filter, keep NOT EXISTS
# ---------------------------------------------------------------------------
def test_ma_sat_v0_incremental_disable_hwm():
    gen = MultiActiveSatV0Generator(
        **TARGET, source_model=SRC, is_incremental=True, disable_hwm=True
    )
    sql = gen.to_sql()
    _print("v0 — Incremental, disable_hwm=True (no time filter, NOT EXISTS only)", sql)
    assert "COALESCE" not in sql
    assert "latest_entries_in_sat" in sql


# ---------------------------------------------------------------------------
# 4. hash_diff as dict {source_column, alias}
# ---------------------------------------------------------------------------
def test_ma_sat_v0_hash_diff_dict():
    gen = MultiActiveSatV0Generator(
        target_table="ma_sat_orders",
        source_model=SourceModel(table_name="stg_orders"),
        parent_hash_key="hk_order",
        hash_diff={"source_column": "raw_hd", "alias": "hashdiff"},
        payload=["phone"],
    )
    sql = gen.to_sql()
    _print("v0 — hash_diff as dict {source_column: raw_hd, alias: hashdiff}", sql)
    assert "raw_hd" in sql
    assert "hashdiff" in sql


# ---------------------------------------------------------------------------
# 5. Additional columns
# ---------------------------------------------------------------------------
def test_ma_sat_v0_additional_columns():
    gen = MultiActiveSatV0Generator(
        **TARGET,
        source_model=SRC,
        is_incremental=False,
        additional_columns=["PHONE_TYPE", "BATCH_ID"],
    )
    sql = gen.to_sql()
    _print("v0 — additional_columns=[PHONE_TYPE, BATCH_ID]", sql)
    assert "PHONE_TYPE" in sql
    assert "BATCH_ID" in sql


# ===========================================================================
# MA-SAT v1
# ===========================================================================

# ---------------------------------------------------------------------------
# 6. Default — LEAD → ledts per (parent_hk, ma_attribute) + is_current flag
# ---------------------------------------------------------------------------
def test_ma_sat_v1_default():
    gen = MultiActiveSatV1Generator(
        target_database="DV_DB",
        target_schema="RAW_VAULT",
        target_table="MA_SAT_CUSTOMER_PHONES_V1",
        sat_v0_database="DV_DB",
        sat_v0_schema="RAW_VAULT",
        sat_v0_table="MA_SAT_CUSTOMER_PHONES",
        parent_hash_key="HK_CUSTOMER_H",
        hash_diff="HD_CUSTOMER_PHONES",
        payload=["PHONE_NUMBER", "IS_PRIMARY"],
        ma_attribute=["PHONE_TYPE"],
        add_is_current=True,
    )
    sql = gen.to_sql()
    _print("v1 — LEAD → ledts per (parent_hk, ma_attribute), is_current flag", sql)
    assert "source_satellite" in sql
    assert "distinct_hk_ldts" in sql
    assert "end_dated_loads" in sql
    assert "end_dated_source" in sql
    assert "LEAD" in sql
    assert "COALESCE" in sql
    assert "is_current" in sql


# ---------------------------------------------------------------------------
# 7. No is_current flag
# ---------------------------------------------------------------------------
def test_ma_sat_v1_no_is_current():
    gen = MultiActiveSatV1Generator(
        target_table="MA_SAT_CUSTOMER_PHONES_V1",
        sat_v0_table="MA_SAT_CUSTOMER_PHONES",
        parent_hash_key="HK_CUSTOMER_H",
        hash_diff="HD_CUSTOMER_PHONES",
        ma_attribute=["PHONE_TYPE"],
        add_is_current=False,
    )
    sql = gen.to_sql()
    _print("v1 — add_is_current=False (only ledts, no flag)", sql)
    assert "LEAD" in sql
    assert "is_current" not in sql


# ---------------------------------------------------------------------------
# 8. Custom ledts_alias + is_current_col name
# ---------------------------------------------------------------------------
def test_ma_sat_v1_custom_aliases():
    gen = MultiActiveSatV1Generator(
        target_table="MA_SAT_CUSTOMER_PHONES_V1",
        sat_v0_table="MA_SAT_CUSTOMER_PHONES",
        parent_hash_key="HK_CUSTOMER_H",
        hash_diff="HD_CUSTOMER_PHONES",
        ma_attribute=["PHONE_TYPE"],
        ledts_alias="LOAD_END_DATE",
        is_current_col="IS_LATEST",
    )
    sql = gen.to_sql()
    _print("v1 — ledts_alias=LOAD_END_DATE, is_current_col=IS_LATEST", sql)
    assert "LOAD_END_DATE" in sql
    assert "IS_LATEST" in sql
