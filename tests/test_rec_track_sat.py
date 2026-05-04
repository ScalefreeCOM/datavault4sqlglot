"""
Record Tracking Satellite SQL generation — all parameter combinations.
Run with:  pytest tests/test_rec_track_sat.py -v -s
"""
from __future__ import annotations

import inspect
from pathlib import Path

from datavault4sqlglot.generators.rec_track_sat import RecordTrackingSatGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"


def _print(label: str, sql: str) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    caller = inspect.currentframe().f_back.f_code.co_name
    (_OUT_DIR / f"{caller}.sql").write_text(
        f"-- REC-TRACK -- {label}\n\n{sql}\n", encoding="utf-8"
    )
    print(f"\n{'='*70}\nREC-TRACK -- {label}\n{'='*70}\n{sql}\n")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SRC = SourceBinding(
    source=SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name="STG_ORDERS",
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    ),
    hash_key_col="HK_ORDER_H",
    rsrc_statics=["ERP/ORDERS"],
)

SRC_NO_STATIC = SourceBinding(
    source=SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name="STG_ORDERS",
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    ),
    hash_key_col="HK_ORDER_H",
)

SRC_SAP = SourceBinding(
    source=SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name="STG_SAP_ORDERS",
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    ),
    hash_key_col="HK_ORDER_H",
    rsrc_statics=["SAP/ORDERS"],
)

SRC_WEB = SourceBinding(
    source=SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name="STG_WEB_ORDERS",
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    ),
    hash_key_col="HK_ORDER_H",
    rsrc_statics=["WEB/%"],
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="REC_TRACK_SAT_ORDER",
    tracked_hashkey="HK_ORDER_H",
)


# ---------------------------------------------------------------------------
# 1. Full load — with rsrc_static (tracks first appearance per source)
# ---------------------------------------------------------------------------
def test_rec_track_full_load_rsrc_static():
    gen = RecordTrackingSatGenerator(**TARGET, sources=[SRC], is_incremental=False)
    sql = gen.to_sql()
    _print("Full Load — rsrc_static=ERP/ORDERS (tracks first appearance per source)", sql)
    assert "HK_ORDER_H" in sql
    assert "ERP/ORDERS" in sql
    assert "records_to_insert" in sql
    # Ghost records excluded
    assert "NOT" in sql


# ---------------------------------------------------------------------------
# 2. Full load — no rsrc_static (global dedup)
# ---------------------------------------------------------------------------
def test_rec_track_full_load_no_rsrc_static():
    gen = RecordTrackingSatGenerator(**TARGET, sources=[SRC_NO_STATIC], is_incremental=False)
    sql = gen.to_sql()
    _print("Full Load — no rsrc_static (global dedup, no source filter)", sql)
    assert "HK_ORDER_H" in sql
    assert "UPPER" in sql
    assert "src_new_0" in sql


# ---------------------------------------------------------------------------
# 3. Incremental — rsrc_static → per-source HWM + CONCAT dedup
# ---------------------------------------------------------------------------
def test_rec_track_incremental_rsrc_static():
    gen = RecordTrackingSatGenerator(**TARGET, sources=[SRC], is_incremental=True)
    sql = gen.to_sql()
    _print("Incremental — rsrc_static=ERP/ORDERS (per-source HWM + CONCAT dedup)", sql)
    assert "distinct_concated_target" in sql
    assert "ERP/ORDERS" in sql
    assert "CONCAT" in sql


# ---------------------------------------------------------------------------
# 4. Incremental — no rsrc_static → global HWM (single source)
# ---------------------------------------------------------------------------
def test_rec_track_incremental_no_rsrc_static():
    gen = RecordTrackingSatGenerator(**TARGET, sources=[SRC_NO_STATIC], is_incremental=True)
    sql = gen.to_sql()
    _print("Incremental — no rsrc_static, single source (global HWM)", sql)
    assert "COALESCE" in sql


# ---------------------------------------------------------------------------
# 5. Incremental — multi-source, all rsrc_static
# ---------------------------------------------------------------------------
def test_rec_track_incremental_multi_source():
    gen = RecordTrackingSatGenerator(**TARGET, sources=[SRC_SAP, SRC_WEB], is_incremental=True)
    sql = gen.to_sql()
    _print("Incremental — Multi Source (SAP + WEB), per-source HWM", sql)
    assert "source_new_union" in sql
    assert "SAP/ORDERS" in sql
    assert "WEB/%" in sql


# ---------------------------------------------------------------------------
# 6. Incremental — disable_hwm (CONCAT dedup only, no time filter)
# ---------------------------------------------------------------------------
def test_rec_track_incremental_disable_hwm():
    gen = RecordTrackingSatGenerator(
        **TARGET, sources=[SRC], is_incremental=True, disable_hwm=True
    )
    sql = gen.to_sql()
    _print("Incremental — disable_hwm=True (CONCAT dedup only, no time filter)", sql)
    assert "max_ldts_per_rsrc_static_in_target" not in sql
    assert "distinct_concated_target" in sql


# ---------------------------------------------------------------------------
# 7. Additional columns
# ---------------------------------------------------------------------------
def test_rec_track_additional_columns():
    gen = RecordTrackingSatGenerator(
        **TARGET,
        sources=[SRC],
        is_incremental=False,
        additional_columns=["BATCH_ID"],
    )
    sql = gen.to_sql()
    _print("Full Load — additional_columns=[BATCH_ID]", sql)
    assert "BATCH_ID" in sql


# ---------------------------------------------------------------------------
# 8. HWM COALESCE handles empty target on first load
# ---------------------------------------------------------------------------
def test_rec_track_hwm_coalesce_rsrc_static():
    gen = RecordTrackingSatGenerator(
        target_table="rec_track_orders",
        sources=[
            SourceBinding(
                source=SourceModel(table_name="stg_orders"),
                hash_key_col="hk_order",
                rsrc_statics=["SAP/ORDERS"],
            )
        ],
        tracked_hashkey="hk_order",
        is_incremental=True,
        beginning_of_all_times="1970-01-01 00:00:00",
    )
    sql = gen.to_sql()
    _print("Incremental HWM — COALESCE handles empty target, LEFT JOIN for rsrc_static", sql)
    assert "COALESCE" in sql
    assert "LEFT JOIN" in sql
    assert "1970-01-01 00:00:00" in sql
