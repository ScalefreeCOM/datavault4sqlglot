"""
Link SQL generation — all parameter combinations.
Run with:  pytest tests/test_link.py -v -s
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from datavault4sqlglot.generators.link import LinkGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"


def _print(label: str, sql: str) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    caller = inspect.currentframe().f_back.f_code.co_name
    (_OUT_DIR / f"{caller}.sql").write_text(
        f"-- LINK -- {label}\n\n{sql}\n", encoding="utf-8"
    )
    print(f"\n{'='*70}\nLINK -- {label}\n{'='*70}\n{sql}\n")


# ---------------------------------------------------------------------------
# Shared source fixtures
# ---------------------------------------------------------------------------

SRC_ORDERS = SourceBinding(
    source=SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name="STG_ORDERS",
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    ),
    hash_key_col="HK_ORDER_CUSTOMER_L",
    foreign_hash_keys=["HK_ORDER_H", "HK_CUSTOMER_H"],
)

SRC_SAP = SourceBinding(
    source=SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name="STG_SAP_ORDERS",
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    ),
    hash_key_col="HK_ORDER_CUSTOMER_L",
    foreign_hash_keys=["HK_ORDER_H", "HK_CUSTOMER_H"],
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
    hash_key_col="HK_ORDER_CUSTOMER_L",
    foreign_hash_keys=["HK_ORDER_H", "HK_CUSTOMER_H"],
    rsrc_statics=["WEB/%"],
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="LNK_ORDER_CUSTOMER",
    link_hash_key="HK_ORDER_CUSTOMER_L",
)


# ---------------------------------------------------------------------------
# 1. Full load — single source
# ---------------------------------------------------------------------------
def test_link_full_load_single_source():
    gen = LinkGenerator(**TARGET, sources=[SRC_ORDERS], is_incremental=False)
    sql = gen.to_sql()
    _print("Full Load — Single Source", sql)
    assert "HK_ORDER_H" in sql
    assert "HK_CUSTOMER_H" in sql
    assert "earliest_hk_over_all_sources" in sql
    assert "distinct_target_hashkeys" not in sql


# ---------------------------------------------------------------------------
# 2. Incremental — single source, no rsrc_static → global HWM (COALESCE MAX)
# ---------------------------------------------------------------------------
def test_link_incremental_single_source():
    gen = LinkGenerator(**TARGET, sources=[SRC_ORDERS], is_incremental=True)
    sql = gen.to_sql()
    _print("Incremental — Single Source, no rsrc_static (global HWM)", sql)
    assert "distinct_target_hashkeys" in sql
    assert "MAX" in sql
    assert "COALESCE" in sql


# ---------------------------------------------------------------------------
# 3. Incremental — single source, rsrc_static → per-source HWM
# ---------------------------------------------------------------------------
def test_link_incremental_rsrc_static():
    gen = LinkGenerator(**TARGET, sources=[SRC_SAP], is_incremental=True)
    sql = gen.to_sql()
    _print("Incremental — Single Source, rsrc_static=SAP/ORDERS (per-source HWM)", sql)
    assert "max_ldts_per_rsrc_static_in_target" in sql
    assert "SAP/ORDERS" in sql
    assert "COALESCE" in sql


# ---------------------------------------------------------------------------
# 4. Incremental — multi source, all rsrc_static → per-source HWM
# ---------------------------------------------------------------------------
def test_link_incremental_multi_source_rsrc_static():
    gen = LinkGenerator(**TARGET, sources=[SRC_SAP, SRC_WEB], is_incremental=True)
    sql = gen.to_sql()
    _print("Incremental — Multi Source (SAP + WEB), per-source HWM", sql)
    assert "source_new_union" in sql
    assert "SAP/ORDERS" in sql
    assert "WEB/%" in sql


# ---------------------------------------------------------------------------
# 5. Incremental — multi source, no rsrc_static → no time filter
# ---------------------------------------------------------------------------
def test_link_incremental_multi_source_no_rsrc_static():
    src_a = SourceBinding(
        source=SourceModel(table_name="STG_A"),
        hash_key_col="HK_ORDER_CUSTOMER_L",
        foreign_hash_keys=["HK_ORDER_H", "HK_CUSTOMER_H"],
    )
    src_b = SourceBinding(
        source=SourceModel(table_name="STG_B"),
        hash_key_col="HK_ORDER_CUSTOMER_L",
        foreign_hash_keys=["HK_ORDER_H", "HK_CUSTOMER_H"],
    )
    gen = LinkGenerator(**TARGET, sources=[src_a, src_b], is_incremental=True)
    sql = gen.to_sql()
    _print("Incremental — Multi Source, no rsrc_static (no HWM, only NOT IN dedup)", sql)
    assert "max_ldts_per_rsrc_static_in_target" not in sql
    assert "distinct_target_hashkeys" in sql


# ---------------------------------------------------------------------------
# 6. Incremental — disable_hwm → skip HWM, keep NOT IN dedup
# ---------------------------------------------------------------------------
def test_link_incremental_disable_hwm():
    gen = LinkGenerator(
        **TARGET, sources=[SRC_ORDERS], is_incremental=True, disable_hwm=True
    )
    sql = gen.to_sql()
    _print("Incremental — disable_hwm=True (NOT IN only, no time filter)", sql)
    assert "max_ldts_per_rsrc_static_in_target" not in sql
    assert "distinct_target_hashkeys" in sql


# ---------------------------------------------------------------------------
# 7. Full load — additional columns
# ---------------------------------------------------------------------------
def test_link_additional_columns():
    gen = LinkGenerator(
        **TARGET,
        sources=[SRC_ORDERS],
        is_incremental=False,
        additional_columns=["BATCH_ID"],
    )
    sql = gen.to_sql()
    _print("Full Load — additional_columns=[BATCH_ID]", sql)
    assert "BATCH_ID" in sql


# ---------------------------------------------------------------------------
# 8. Validation — fewer than 2 foreign_hash_keys raises ValueError
# ---------------------------------------------------------------------------
def test_link_fk_validation_raises():
    src = SourceBinding(
        source=SourceModel(table_name="stg_orders"),
        foreign_hash_keys=["hk_customer"],
    )
    gen = LinkGenerator(
        target_table="lnk_orders",
        sources=[src],
        link_hash_key="hk_lnk_orders",
    )
    with pytest.raises(ValueError, match="at least 2 foreign_hash_keys"):
        gen.generate_sql()
