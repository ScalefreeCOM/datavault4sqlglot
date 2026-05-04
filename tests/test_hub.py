"""
Hub SQL generation — all parameter combinations.
Run with:  pytest tests/test_hub.py -v -s
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"


def _print(label: str, sql: str) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    caller = inspect.currentframe().f_back.f_code.co_name
    (_OUT_DIR / f"{caller}.sql").write_text(
        f"-- HUB -- {label}\n\n{sql}\n", encoding="utf-8"
    )
    print(f"\n{'='*70}\nHUB -- {label}\n{'='*70}\n{sql}\n")


# ---------------------------------------------------------------------------
# Shared source fixtures
# ---------------------------------------------------------------------------

_SRC_ORDERS_MODEL = SourceModel(
    database="RAW_DB",
    schema="STAGE",
    table_name="STG_ORDERS",
    load_date_col="LOAD_DATE",
    record_source_col="RECORD_SOURCE",
)

SRC_ORDERS = SourceBinding(
    source=_SRC_ORDERS_MODEL,
    business_keys=["ORDER_ID"],
)

SRC_ORDERS_WITH_STATIC = SourceBinding(
    source=_SRC_ORDERS_MODEL,
    business_keys=["ORDER_ID"],
    rsrc_statics=["ERP/ORDERS"],
)

SRC_SAP = SourceBinding(
    source=SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name="STG_SAP_ORDERS",
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    ),
    business_keys=["SAP_ORDER_ID"],
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
    business_keys=["WEB_ORDER_ID"],
    rsrc_statics=["WEB/%"],
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="HUB_ORDER",
    hashkey="HK_ORDER_H",
)


# ---------------------------------------------------------------------------
# 1. Full load — single source
# ---------------------------------------------------------------------------
def test_hub_full_load_single_source():
    gen = HubGenerator(**TARGET, sources=[SRC_ORDERS], is_incremental=False)
    sql = gen.to_sql()
    _print("Full Load — Single Source", sql)
    assert "STG_ORDERS" in sql
    assert "ORDER_ID" in sql
    assert "earliest_hk_over_all_sources" in sql
    assert "distinct_target_hashkeys" not in sql
    assert "records_to_insert" not in sql
    assert "max_ldts_per_rsrc_static_in_target" not in sql


# ---------------------------------------------------------------------------
# 2. Full load — multi source (UNION ALL)
# ---------------------------------------------------------------------------
def test_hub_full_load_multi_source():
    gen = HubGenerator(**TARGET, sources=[SRC_ORDERS, SRC_WEB], is_incremental=False)
    sql = gen.to_sql()
    _print("Full Load — Multi Source (UNION ALL)", sql)
    assert "source_new_union" in sql
    assert "STG_ORDERS" in sql
    assert "STG_WEB_ORDERS" in sql


# ---------------------------------------------------------------------------
# 3. Incremental — single source, no rsrc_static → global HWM (COALESCE MAX)
# ---------------------------------------------------------------------------
def test_hub_incremental_single_source_no_rsrc_static():
    gen = HubGenerator(**TARGET, sources=[SRC_ORDERS], is_incremental=True)
    sql = gen.to_sql()
    _print("Incremental — Single Source, no rsrc_static (global HWM)", sql)
    assert "MAX" in sql
    assert "COALESCE" in sql
    assert "distinct_target_hashkeys" in sql
    assert "records_to_insert" in sql


# ---------------------------------------------------------------------------
# 4. Incremental — single source, rsrc_static → per-source HWM
# ---------------------------------------------------------------------------
def test_hub_incremental_single_source_rsrc_static():
    gen = HubGenerator(**TARGET, sources=[SRC_ORDERS_WITH_STATIC], is_incremental=True)
    sql = gen.to_sql()
    _print("Incremental — Single Source, rsrc_static=ERP/ORDERS (per-source HWM)", sql)
    assert "max_ldts_per_rsrc_static_in_target" in sql
    assert "ERP/ORDERS" in sql
    assert "COALESCE" in sql


# ---------------------------------------------------------------------------
# 5. Incremental — multi source, all rsrc_static → per-source HWM per source
# ---------------------------------------------------------------------------
def test_hub_incremental_multi_source_all_rsrc_static():
    gen = HubGenerator(**TARGET, sources=[SRC_SAP, SRC_WEB], is_incremental=True)
    sql = gen.to_sql()
    _print("Incremental — Multi Source, all rsrc_static (per-source HWM)", sql)
    assert "max_ldts_per_rsrc_static_in_target" in sql
    assert "SAP/ORDERS" in sql
    assert "WEB/%" in sql


# ---------------------------------------------------------------------------
# 6. Incremental — multi source, no rsrc_static → no time filter (safe)
# ---------------------------------------------------------------------------
def test_hub_incremental_multi_source_no_rsrc_static():
    src_a = SourceBinding(source=SourceModel(table_name="STG_A"), business_keys=["ORDER_ID"])
    src_b = SourceBinding(source=SourceModel(table_name="STG_B"), business_keys=["ORDER_ID"])
    gen = HubGenerator(**TARGET, sources=[src_a, src_b], is_incremental=True)
    sql = gen.to_sql()
    _print(
        "Incremental — Multi Source, no rsrc_static (no HWM, only NOT IN dedup)",
        sql,
    )
    assert "max_ldts_per_rsrc_static_in_target" not in sql
    assert "distinct_target_hashkeys" in sql
    assert "records_to_insert" in sql


# ---------------------------------------------------------------------------
# 7. Incremental — disable_hwm → skip HWM, keep NOT IN dedup
# ---------------------------------------------------------------------------
def test_hub_incremental_disable_hwm():
    gen = HubGenerator(
        **TARGET, sources=[SRC_ORDERS], is_incremental=True, disable_hwm=True
    )
    sql = gen.to_sql()
    _print("Incremental — disable_hwm=True (no time filter, still deduplicates via NOT IN)", sql)
    assert "max_ldts_per_rsrc_static_in_target" not in sql
    assert "distinct_target_hashkeys" in sql
    assert "records_to_insert" in sql


# ---------------------------------------------------------------------------
# 8. Full load — additional_columns carried through
# ---------------------------------------------------------------------------
def test_hub_additional_columns():
    gen = HubGenerator(
        **TARGET,
        sources=[SRC_ORDERS],
        is_incremental=False,
        additional_columns=["BATCH_ID", "FILE_NAME"],
    )
    sql = gen.to_sql()
    _print("Full Load — additional_columns=[BATCH_ID, FILE_NAME]", sql)
    assert "BATCH_ID" in sql
    assert "FILE_NAME" in sql


# ---------------------------------------------------------------------------
# 9. Config — custom ldts_alias propagates throughout
# ---------------------------------------------------------------------------
def test_hub_custom_ldts_alias():
    config.ldts_alias = "load_ts"
    src = SourceBinding(
        source=SourceModel(table_name="stg_orders"),
        business_keys=["order_id"],
    )
    sql = HubGenerator(
        target_table="hub_orders",
        sources=[src],
        hashkey="hk_order",
        is_incremental=True,
    ).to_sql()
    _print("Config — custom ldts_alias=load_ts", sql)
    assert "load_ts" in sql


# ---------------------------------------------------------------------------
# 10. Config — custom rsrc_alias propagates throughout
# ---------------------------------------------------------------------------
def test_hub_custom_rsrc_alias():
    config.rsrc_alias = "rec_src"
    src = SourceBinding(
        source=SourceModel(table_name="stg_orders"),
        business_keys=["order_id"],
    )
    sql = HubGenerator(
        target_table="hub_orders",
        sources=[src],
        hashkey="hk_order",
    ).to_sql()
    _print("Config — custom rsrc_alias=rec_src", sql)
    assert "rec_src" in sql
