"""
Hub SQL generation — all parameter combinations.
Run with:  pytest tests/test_hub.py -v -s
"""
from __future__ import annotations

import pytest

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel


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
)

SRC_ORDERS_WITH_STATIC = SourceBinding(
    source=_SRC_ORDERS_MODEL,
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
    bk_columns=["SAP_ORDER_ID"],
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
    bk_columns=["WEB_ORDER_ID"],
    rsrc_statics=["WEB/%"],
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="HUB_ORDER",
    hashkey="HK_ORDER_H",
    business_keys=["ORDER_ID"],
)


# ---------------------------------------------------------------------------
# 1. Full load — single source
# ---------------------------------------------------------------------------
def test_hub_full_load_single_source(write_sql):
    gen = HubGenerator(**TARGET, sources=[SRC_ORDERS], is_incremental=False)
    sql = gen.to_sql()
    write_sql("Full Load — Single Source", sql)
    assert "STG_ORDERS" in sql
    assert "ORDER_ID" in sql
    assert "earliest_hk_over_all_sources" in sql
    assert "distinct_target_hashkeys" not in sql
    assert "records_to_insert" not in sql
    assert "max_ldts_per_rsrc_static_in_target" not in sql


# ---------------------------------------------------------------------------
# 2. Full load — multi source (UNION ALL)
# ---------------------------------------------------------------------------
def test_hub_full_load_multi_source(write_sql):
    gen = HubGenerator(**TARGET, sources=[SRC_ORDERS, SRC_WEB], is_incremental=False)
    sql = gen.to_sql()
    write_sql("Full Load — Multi Source (UNION ALL)", sql)
    assert "source_new_union" in sql
    assert "STG_ORDERS" in sql
    assert "STG_WEB_ORDERS" in sql


# ---------------------------------------------------------------------------
# 3. Incremental — single source, no rsrc_static → global HWM (COALESCE MAX)
# ---------------------------------------------------------------------------
def test_hub_incremental_single_source_no_rsrc_static(write_sql):
    gen = HubGenerator(**TARGET, sources=[SRC_ORDERS], is_incremental=True)
    sql = gen.to_sql()
    write_sql("Incremental — Single Source, no rsrc_static (global HWM)", sql)
    assert "MAX" in sql
    assert "COALESCE" in sql
    assert "distinct_target_hashkeys" in sql
    assert "records_to_insert" in sql


# ---------------------------------------------------------------------------
# 4. Incremental — single source, rsrc_static → per-source HWM
# ---------------------------------------------------------------------------
def test_hub_incremental_single_source_rsrc_static(write_sql):
    gen = HubGenerator(**TARGET, sources=[SRC_ORDERS_WITH_STATIC], is_incremental=True)
    sql = gen.to_sql()
    write_sql("Incremental — Single Source, rsrc_static=ERP/ORDERS (per-source HWM)", sql)
    assert "max_ldts_per_rsrc_static_in_target" in sql
    assert "ERP/ORDERS" in sql
    assert "COALESCE" in sql


# ---------------------------------------------------------------------------
# 5. Incremental — multi source, all rsrc_static → per-source HWM per source
# ---------------------------------------------------------------------------
def test_hub_incremental_multi_source_all_rsrc_static(write_sql):
    gen = HubGenerator(**TARGET, sources=[SRC_SAP, SRC_WEB], is_incremental=True)
    sql = gen.to_sql()
    write_sql("Incremental — Multi Source, all rsrc_static (per-source HWM)", sql)
    assert "max_ldts_per_rsrc_static_in_target" in sql
    assert "SAP/ORDERS" in sql
    assert "WEB/%" in sql


# ---------------------------------------------------------------------------
# 6. Incremental — multi source, no rsrc_static → no time filter (safe)
# ---------------------------------------------------------------------------
def test_hub_incremental_multi_source_no_rsrc_static(write_sql):
    src_a = SourceBinding(source=SourceModel(table_name="STG_A"))
    src_b = SourceBinding(source=SourceModel(table_name="STG_B"))
    gen = HubGenerator(**TARGET, sources=[src_a, src_b], is_incremental=True)
    sql = gen.to_sql()
    write_sql(
        "Incremental — Multi Source, no rsrc_static (no HWM, only NOT IN dedup)",
        sql,
    )
    assert "max_ldts_per_rsrc_static_in_target" not in sql
    assert "distinct_target_hashkeys" in sql
    assert "records_to_insert" in sql


# ---------------------------------------------------------------------------
# 7. Incremental — disable_hwm → skip HWM, keep NOT IN dedup
# ---------------------------------------------------------------------------
def test_hub_incremental_disable_hwm(write_sql):
    gen = HubGenerator(
        **TARGET, sources=[SRC_ORDERS], is_incremental=True, disable_hwm=True
    )
    sql = gen.to_sql()
    write_sql("Incremental — disable_hwm=True (no time filter, still deduplicates via NOT IN)", sql)
    assert "max_ldts_per_rsrc_static_in_target" not in sql
    assert "distinct_target_hashkeys" in sql
    assert "records_to_insert" in sql


# ---------------------------------------------------------------------------
# 8. Full load — additional_columns carried through
# ---------------------------------------------------------------------------
def test_hub_additional_columns(write_sql):
    gen = HubGenerator(
        **TARGET,
        sources=[SRC_ORDERS],
        is_incremental=False,
        additional_columns=["BATCH_ID", "FILE_NAME"],
    )
    sql = gen.to_sql()
    write_sql("Full Load — additional_columns=[BATCH_ID, FILE_NAME]", sql)
    assert "BATCH_ID" in sql
    assert "FILE_NAME" in sql


# ---------------------------------------------------------------------------
# 9. Config — custom ldts_alias propagates throughout
# ---------------------------------------------------------------------------
def test_hub_custom_ldts_alias(write_sql):
    config.ldts_alias = "load_ts"
    src = SourceBinding(source=SourceModel(table_name="stg_orders"))
    sql = HubGenerator(
        target_table="hub_orders",
        sources=[src],
        hashkey="hk_order",
        business_keys=["order_id"],
        is_incremental=True,
    ).to_sql()
    write_sql("Config — custom ldts_alias=load_ts", sql)
    assert "load_ts" in sql


# ---------------------------------------------------------------------------
# 10. Config — custom rsrc_alias propagates throughout
# ---------------------------------------------------------------------------
def test_hub_custom_rsrc_alias(write_sql):
    config.rsrc_alias = "rec_src"
    src = SourceBinding(source=SourceModel(table_name="stg_orders"))
    sql = HubGenerator(
        target_table="hub_orders",
        sources=[src],
        hashkey="hk_order",
        business_keys=["order_id"],
    ).to_sql()
    write_sql("Config — custom rsrc_alias=rec_src", sql)
    assert "rec_src" in sql


# ---------------------------------------------------------------------------
# 11. Incremental — single source, multiple rsrc_statics → one HWM branch each
# ---------------------------------------------------------------------------
def test_hub_incremental_single_source_multiple_rsrc_statics(write_sql):
    """
    A single source carrying rows from N record-source patterns must produce:
      • N branches in the HWM CTE (one MAX(ldts) per pattern), and
      • N OR branches in the src_new_0 WHERE (one strict-GT filter per pattern),
    so each pattern's high-water-mark advances independently.
    """
    src = SourceBinding(
        source=_SRC_ORDERS_MODEL,
        rsrc_statics=["ERP/ORDERS", "ERP/ARCHIVE", "ERP/EXT"],
    )
    gen = HubGenerator(**TARGET, sources=[src], is_incremental=True)
    sql = gen.to_sql()
    write_sql(
        "Incremental — Single Source, multiple rsrc_statics (per-pattern HWM)",
        sql,
    )

    # All three patterns appear in the rendered SQL.
    for static in ("ERP/ORDERS", "ERP/ARCHIVE", "ERP/EXT"):
        assert static in sql, f"missing rsrc_static literal {static!r}"

    # HWM CTE present and built as a UNION ALL of N=3 per-pattern branches.
    # Single source → no source-level UNION, so all UNION ALLs come from the
    # HWM CTE: 3 branches → exactly 2 UNION ALL operators.
    assert "max_ldts_per_rsrc_static_in_target" in sql
    assert sql.upper().count("UNION ALL") == 2


# ---------------------------------------------------------------------------
# 12. Incremental — multi source × multi rsrc_statics → cross-product HWM
# ---------------------------------------------------------------------------
def test_hub_incremental_multi_source_multi_rsrc_statics(write_sql):
    """
    Cross-product case: two sources, each carrying rows from multiple record-
    source patterns. The HWM CTE iterates ``for binding in sources: for sv in
    binding.rsrc_statics`` (see base.py:106), so the total branch count must
    equal the sum of statics across all bindings — and each per-source CTE
    keeps its own pattern set in the WHERE clause.
    """
    sap = SourceBinding(
        source=SourceModel(
            database="RAW_DB", schema="STAGE", table_name="STG_SAP_ORDERS",
            load_date_col="LOAD_DATE", record_source_col="RECORD_SOURCE",
        ),
        bk_columns=["SAP_ORDER_ID"],
        rsrc_statics=["SAP/ORDERS", "SAP/ARCHIVE"],
    )
    web = SourceBinding(
        source=SourceModel(
            database="RAW_DB", schema="STAGE", table_name="STG_WEB_ORDERS",
            load_date_col="LOAD_DATE", record_source_col="RECORD_SOURCE",
        ),
        bk_columns=["WEB_ORDER_ID"],
        rsrc_statics=["WEB/EU/%", "WEB/US/%"],
    )
    gen = HubGenerator(**TARGET, sources=[sap, web], is_incremental=True)
    sql = gen.to_sql()
    write_sql(
        "Incremental — Multi Source × Multi rsrc_statics (cross-product HWM)",
        sql,
    )

    # All four pattern literals appear.
    for static in ("SAP/ORDERS", "SAP/ARCHIVE", "WEB/EU/%", "WEB/US/%"):
        assert static in sql, f"missing rsrc_static literal {static!r}"

    # HWM CTE: 4 branches (sum across sources) → 3 UNION ALLs.
    # Source-level union: 2 sources → 1 UNION ALL.
    # Total UNION ALL keywords = 4.
    assert "max_ldts_per_rsrc_static_in_target" in sql
    assert "source_new_union" in sql
    assert sql.upper().count("UNION ALL") == 4

    # Each per-source CTE must reference *its own* patterns — never the other
    # source's. This protects against an accidental cross-binding leak in the
    # OR-filter builder.
    src0 = sql.split("src_new_0")[1].split("src_new_1")[0]
    src1 = sql.split("src_new_1")[1].split("source_new_union")[0]
    for sap_static in ("SAP/ORDERS", "SAP/ARCHIVE"):
        assert sap_static in src0, f"src_new_0 missing {sap_static!r}"
        assert sap_static not in src1, f"src_new_1 leaked {sap_static!r}"
    for web_static in ("WEB/EU/%", "WEB/US/%"):
        assert web_static in src1, f"src_new_1 missing {web_static!r}"
        assert web_static not in src0, f"src_new_0 leaked {web_static!r}"
