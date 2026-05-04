"""
Non-Historized Link and Non-Historized Satellite SQL generation.
Run with:  pytest tests/test_nh_entities.py -v -s
"""
from __future__ import annotations

import inspect
from pathlib import Path

from datavault4sqlglot.generators.nh_link import NonHistorizedLinkGenerator
from datavault4sqlglot.generators.nh_sat import NonHistorizedSatGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"


def _print(label: str, sql: str) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    caller = inspect.currentframe().f_back.f_code.co_name
    (_OUT_DIR / f"{caller}.sql").write_text(
        f"-- NH -- {label}\n\n{sql}\n", encoding="utf-8"
    )
    print(f"\n{'='*70}\nNH -- {label}\n{'='*70}\n{sql}\n")


# ===========================================================================
# NH-LINK fixtures
# ===========================================================================

NH_LINK_SRC = SourceBinding(
    source=SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name="STG_ORDER_PRODUCT",
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    ),
    hash_key_col="HK_ORDER_PRODUCT_L",
    foreign_hash_keys=["HK_ORDER_H", "HK_PRODUCT_H"],
    payload=["QUANTITY", "UNIT_PRICE"],
)

NH_LINK_SRC_SAP = SourceBinding(
    source=SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name="STG_SAP_ORDER_PRODUCT",
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    ),
    hash_key_col="HK_ORDER_PRODUCT_L",
    foreign_hash_keys=["HK_ORDER_H", "HK_PRODUCT_H"],
    payload=["QUANTITY", "UNIT_PRICE"],
    rsrc_statics=["SAP/ORDERS"],
)

NH_LINK_SRC_WEB = SourceBinding(
    source=SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name="STG_WEB_ORDER_PRODUCT",
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    ),
    hash_key_col="HK_ORDER_PRODUCT_L",
    foreign_hash_keys=["HK_ORDER_H", "HK_PRODUCT_H"],
    payload=["QUANTITY", "UNIT_PRICE"],
    rsrc_statics=["WEB/%"],
)

NH_LINK_TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="NH_LNK_ORDER_PRODUCT",
    link_hash_key="HK_ORDER_PRODUCT_L",
)

# ===========================================================================
# NH-SAT fixtures
# ===========================================================================

NH_SAT_SRC = SourceModel(
    database="RAW_DB",
    schema="STAGE",
    table_name="STG_PRODUCT_DETAILS",
    load_date_col="LOAD_DATE",
    record_source_col="RECORD_SOURCE",
)

NH_SAT_TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="NH_SAT_PRODUCT_DETAILS",
    parent_hash_key="HK_PRODUCT_H",
)

NH_SAT_PAYLOAD = ["PRODUCT_NAME", "CATEGORY", "LIST_PRICE"]


# ===========================================================================
# NH-LINK tests
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Full load — single source
# ---------------------------------------------------------------------------
def test_nh_link_full_load():
    gen = NonHistorizedLinkGenerator(**NH_LINK_TARGET, sources=[NH_LINK_SRC], is_incremental=False)
    sql = gen.to_sql()
    _print("NH-Link Full Load — Single Source (link_hk + foreign_hks + payload)", sql)
    assert "HK_ORDER_H" in sql
    assert "QUANTITY" in sql
    assert "earliest_hk_over_all_sources" in sql
    assert "distinct_target_hashkeys" not in sql


# ---------------------------------------------------------------------------
# 2. Incremental — single source, no rsrc_static → global HWM + NOT IN
# ---------------------------------------------------------------------------
def test_nh_link_incremental_global_hwm():
    gen = NonHistorizedLinkGenerator(**NH_LINK_TARGET, sources=[NH_LINK_SRC], is_incremental=True)
    sql = gen.to_sql()
    _print("NH-Link Incremental — Single Source, no rsrc_static (global HWM + NOT IN)", sql)
    assert "distinct_target_hashkeys" in sql
    assert "COALESCE" in sql
    assert "records_to_insert" in sql


# ---------------------------------------------------------------------------
# 3. Incremental — rsrc_static → per-source HWM
# ---------------------------------------------------------------------------
def test_nh_link_incremental_rsrc_static():
    gen = NonHistorizedLinkGenerator(**NH_LINK_TARGET, sources=[NH_LINK_SRC_SAP], is_incremental=True)
    sql = gen.to_sql()
    _print("NH-Link Incremental — rsrc_static=SAP/ORDERS (per-source HWM)", sql)
    assert "max_ldts_per_rsrc_static_in_target" in sql
    assert "SAP/ORDERS" in sql


# ---------------------------------------------------------------------------
# 4. Incremental — multi source, all rsrc_static
# ---------------------------------------------------------------------------
def test_nh_link_incremental_multi_source_rsrc_static():
    gen = NonHistorizedLinkGenerator(
        **NH_LINK_TARGET, sources=[NH_LINK_SRC_SAP, NH_LINK_SRC_WEB], is_incremental=True
    )
    sql = gen.to_sql()
    _print("NH-Link Incremental — Multi Source (SAP + WEB), per-source HWM", sql)
    assert "source_new_union" in sql
    assert "SAP/ORDERS" in sql
    assert "WEB/%" in sql


# ---------------------------------------------------------------------------
# 5. Incremental — disable_hwm
# ---------------------------------------------------------------------------
def test_nh_link_incremental_disable_hwm():
    gen = NonHistorizedLinkGenerator(
        **NH_LINK_TARGET, sources=[NH_LINK_SRC], is_incremental=True, disable_hwm=True
    )
    sql = gen.to_sql()
    _print("NH-Link Incremental — disable_hwm=True (NOT IN only, no time filter)", sql)
    assert "COALESCE" not in sql
    assert "distinct_target_hashkeys" in sql


# ---------------------------------------------------------------------------
# 6. Multi-source UNION (distinct) vs UNION ALL
# ---------------------------------------------------------------------------
def test_nh_link_union_strategy_union():
    src2 = SourceBinding(
        source=SourceModel(table_name="STG_WEB_ORDER_PRODUCT"),
        hash_key_col="HK_ORDER_PRODUCT_L",
        foreign_hash_keys=["HK_ORDER_H", "HK_PRODUCT_H"],
        payload=["QUANTITY", "UNIT_PRICE"],
    )
    gen = NonHistorizedLinkGenerator(
        **NH_LINK_TARGET, sources=[NH_LINK_SRC, src2],
        is_incremental=False, union_strategy="UNION"
    )
    sql = gen.to_sql()
    _print("NH-Link Full Load — Multi Source, union_strategy=UNION (DISTINCT across sources)", sql)
    assert "UNION" in sql


# ---------------------------------------------------------------------------
# 7. Additional columns
# ---------------------------------------------------------------------------
def test_nh_link_additional_columns():
    gen = NonHistorizedLinkGenerator(
        **NH_LINK_TARGET, sources=[NH_LINK_SRC],
        is_incremental=False, additional_columns=["BATCH_ID"],
    )
    sql = gen.to_sql()
    _print("NH-Link Full Load — additional_columns=[BATCH_ID]", sql)
    assert "BATCH_ID" in sql


# ===========================================================================
# NH-SAT tests
# ===========================================================================

# ---------------------------------------------------------------------------
# 8. Full load, multi-batch — QUALIFY ROW_NUMBER to keep latest per hk
# ---------------------------------------------------------------------------
def test_nh_sat_full_load_multi_batch():
    gen = NonHistorizedSatGenerator(
        **NH_SAT_TARGET, source_model=NH_SAT_SRC,
        payload=NH_SAT_PAYLOAD,
        source_is_single_batch=False, is_incremental=False
    )
    sql = gen.to_sql()
    _print("NH-Sat Full Load, Multi-Batch (QUALIFY ROW_NUMBER -> latest per hk)", sql)
    assert "source_data" in sql
    assert "QUALIFY" in sql
    assert "ROW_NUMBER" in sql
    assert "distinct_target_hashkeys" not in sql


# ---------------------------------------------------------------------------
# 9. Full load, single-batch — no QUALIFY (source already contains one batch)
# ---------------------------------------------------------------------------
def test_nh_sat_full_load_single_batch():
    gen = NonHistorizedSatGenerator(
        **NH_SAT_TARGET, source_model=NH_SAT_SRC,
        payload=NH_SAT_PAYLOAD,
        source_is_single_batch=True, is_incremental=False
    )
    sql = gen.to_sql()
    _print("NH-Sat Full Load, Single-Batch (no QUALIFY, source is one snapshot)", sql)
    assert "QUALIFY" not in sql


# ---------------------------------------------------------------------------
# 10. Incremental — NOT IN on parent_hk (existing keys skipped)
# ---------------------------------------------------------------------------
def test_nh_sat_incremental():
    gen = NonHistorizedSatGenerator(
        **NH_SAT_TARGET, source_model=NH_SAT_SRC,
        payload=NH_SAT_PAYLOAD,
        is_incremental=True,
    )
    sql = gen.to_sql()
    _print("NH-Sat Incremental (NOT IN on parent_hk, existing keys skipped)", sql)
    assert "distinct_target_hashkeys" in sql
    assert "records_to_insert" in sql


# ---------------------------------------------------------------------------
# 11. Additional columns
# ---------------------------------------------------------------------------
def test_nh_sat_additional_columns():
    gen = NonHistorizedSatGenerator(
        **NH_SAT_TARGET, source_model=NH_SAT_SRC,
        payload=NH_SAT_PAYLOAD,
        is_incremental=False, additional_columns=["BATCH_ID", "FILE_DATE"],
    )
    sql = gen.to_sql()
    _print("NH-Sat Full Load — additional_columns=[BATCH_ID, FILE_DATE]", sql)
    assert "BATCH_ID" in sql
    assert "FILE_DATE" in sql
