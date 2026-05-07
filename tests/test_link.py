"""
Link SQL generation — all parameter combinations.
Run with:  pytest tests/test_link.py -v -s
"""
from __future__ import annotations

import pytest

from datavault4sqlglot.generators.link import LinkGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel


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
    rsrc_statics=["WEB/%"],
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="RAW_VAULT",
    target_table="LNK_ORDER_CUSTOMER",
    link_hash_key="HK_ORDER_CUSTOMER_L",
    foreign_hash_keys=["HK_ORDER_H", "HK_CUSTOMER_H"],
)


# ---------------------------------------------------------------------------
# 1. Full load — single source
# ---------------------------------------------------------------------------
def test_link_full_load_single_source(write_sql):
    gen = LinkGenerator(**TARGET, sources=[SRC_ORDERS], is_incremental=False)
    sql = gen.to_sql()
    write_sql("Full Load — Single Source", sql)
    assert "HK_ORDER_H" in sql
    assert "HK_CUSTOMER_H" in sql
    assert "earliest_hk_over_all_sources" in sql
    assert "distinct_target_hashkeys" not in sql


# ---------------------------------------------------------------------------
# 2. Incremental — single source, no rsrc_static → global HWM (COALESCE MAX)
# ---------------------------------------------------------------------------
def test_link_incremental_single_source(write_sql):
    gen = LinkGenerator(**TARGET, sources=[SRC_ORDERS], is_incremental=True)
    sql = gen.to_sql()
    write_sql("Incremental — Single Source, no rsrc_static (global HWM)", sql)
    assert "distinct_target_hashkeys" in sql
    assert "MAX" in sql
    assert "COALESCE" in sql


# ---------------------------------------------------------------------------
# 3. Incremental — single source, rsrc_static → per-source HWM
# ---------------------------------------------------------------------------
def test_link_incremental_rsrc_static(write_sql):
    gen = LinkGenerator(**TARGET, sources=[SRC_SAP], is_incremental=True)
    sql = gen.to_sql()
    write_sql("Incremental — Single Source, rsrc_static=SAP/ORDERS (per-source HWM)", sql)
    assert "max_ldts_per_rsrc_static_in_target" in sql
    assert "SAP/ORDERS" in sql
    assert "COALESCE" in sql


# ---------------------------------------------------------------------------
# 4. Incremental — multi source, all rsrc_static → per-source HWM
# ---------------------------------------------------------------------------
def test_link_incremental_multi_source_rsrc_static(write_sql):
    gen = LinkGenerator(**TARGET, sources=[SRC_SAP, SRC_WEB], is_incremental=True)
    sql = gen.to_sql()
    write_sql("Incremental — Multi Source (SAP + WEB), per-source HWM", sql)
    assert "source_new_union" in sql
    assert "SAP/ORDERS" in sql
    assert "WEB/%" in sql


# ---------------------------------------------------------------------------
# 5. Incremental — multi source, no rsrc_static → no time filter
# ---------------------------------------------------------------------------
def test_link_incremental_multi_source_no_rsrc_static(write_sql):
    src_a = SourceBinding(
        source=SourceModel(table_name="STG_A"),
        hash_key_col="HK_ORDER_CUSTOMER_L",
    )
    src_b = SourceBinding(
        source=SourceModel(table_name="STG_B"),
        hash_key_col="HK_ORDER_CUSTOMER_L",
    )
    gen = LinkGenerator(**TARGET, sources=[src_a, src_b], is_incremental=True)
    sql = gen.to_sql()
    write_sql("Incremental — Multi Source, no rsrc_static (no HWM, only NOT IN dedup)", sql)
    assert "max_ldts_per_rsrc_static_in_target" not in sql
    assert "distinct_target_hashkeys" in sql


# ---------------------------------------------------------------------------
# 6. Incremental — disable_hwm → skip HWM, keep NOT IN dedup
# ---------------------------------------------------------------------------
def test_link_incremental_disable_hwm(write_sql):
    gen = LinkGenerator(
        **TARGET, sources=[SRC_ORDERS], is_incremental=True, disable_hwm=True
    )
    sql = gen.to_sql()
    write_sql("Incremental — disable_hwm=True (NOT IN only, no time filter)", sql)
    assert "max_ldts_per_rsrc_static_in_target" not in sql
    assert "distinct_target_hashkeys" in sql


# ---------------------------------------------------------------------------
# 7. Full load — additional columns
# ---------------------------------------------------------------------------
def test_link_additional_columns(write_sql):
    gen = LinkGenerator(
        **TARGET,
        sources=[SRC_ORDERS],
        is_incremental=False,
        additional_columns=["BATCH_ID"],
    )
    sql = gen.to_sql()
    write_sql("Full Load — additional_columns=[BATCH_ID]", sql)
    assert "BATCH_ID" in sql


# ---------------------------------------------------------------------------
# 8. Validation — fewer than 2 foreign_hash_keys raises ValueError at __init__
# ---------------------------------------------------------------------------
def test_link_fk_validation_raises():
    src = SourceBinding(source=SourceModel(table_name="stg_orders"))
    with pytest.raises(ValueError, match="at least 2 foreign_hash_keys"):
        LinkGenerator(
            target_table="lnk_orders",
            sources=[src],
            link_hash_key="hk_lnk_orders",
            foreign_hash_keys=["hk_customer"],
        )


# ---------------------------------------------------------------------------
# 8b. Validation — fk_columns length must match foreign_hash_keys length
# ---------------------------------------------------------------------------
def test_link_fk_columns_length_mismatch_raises():
    src = SourceBinding(
        source=SourceModel(table_name="stg_orders"),
        fk_columns=["HK_ORDER_H"],  # only 1 — link expects 2
    )
    with pytest.raises(ValueError, match="fk_columns has length 1"):
        LinkGenerator(
            target_table="lnk_orders",
            sources=[src],
            link_hash_key="hk_lnk_orders",
            foreign_hash_keys=["HK_ORDER_H", "HK_CUSTOMER_H"],
        )


# ---------------------------------------------------------------------------
# 9. Incremental — single source, multiple rsrc_statics → one HWM branch each
# ---------------------------------------------------------------------------
def test_link_incremental_single_source_multiple_rsrc_statics(write_sql):
    """
    A single source carrying rows from N record-source patterns must produce:
      • N branches in the HWM CTE (one MAX(ldts) per pattern), and
      • N OR branches in the src_new_0 WHERE (one strict-GT filter per pattern),
    so each pattern's high-water-mark advances independently. Mirrors the Hub
    behaviour — both delegate to the same helpers in base.py.
    """
    src = SourceBinding(
        source=SourceModel(
            database="RAW_DB", schema="STAGE", table_name="STG_SAP_ORDERS",
            load_date_col="LOAD_DATE", record_source_col="RECORD_SOURCE",
        ),
        hash_key_col="HK_ORDER_CUSTOMER_L",
        rsrc_statics=["SAP/ORDERS", "SAP/ARCHIVE", "SAP/EXT"],
    )
    gen = LinkGenerator(**TARGET, sources=[src], is_incremental=True)
    sql = gen.to_sql()
    write_sql(
        "Incremental — Single Source, multiple rsrc_statics (per-pattern HWM)",
        sql,
    )

    # All three patterns appear in the rendered SQL.
    for static in ("SAP/ORDERS", "SAP/ARCHIVE", "SAP/EXT"):
        assert static in sql, f"missing rsrc_static literal {static!r}"

    # HWM CTE present and built as a UNION ALL of N=3 per-pattern branches.
    # Single source → no source-level UNION, so all UNION ALLs come from the
    # HWM CTE: 3 branches → exactly 2 UNION ALL operators.
    assert "max_ldts_per_rsrc_static_in_target" in sql
    assert sql.upper().count("UNION ALL") == 2


# ---------------------------------------------------------------------------
# 10. Incremental — multi source × multi rsrc_statics → cross-product HWM
# ---------------------------------------------------------------------------
def test_link_incremental_multi_source_multi_rsrc_statics(write_sql):
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
        hash_key_col="HK_ORDER_CUSTOMER_L",
        rsrc_statics=["SAP/ORDERS", "SAP/ARCHIVE"],
    )
    web = SourceBinding(
        source=SourceModel(
            database="RAW_DB", schema="STAGE", table_name="STG_WEB_ORDERS",
            load_date_col="LOAD_DATE", record_source_col="RECORD_SOURCE",
        ),
        hash_key_col="HK_ORDER_CUSTOMER_L",
        rsrc_statics=["WEB/EU/%", "WEB/US/%"],
    )
    gen = LinkGenerator(**TARGET, sources=[sap, web], is_incremental=True)
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
    # source's. Protects against a cross-binding leak in the OR-filter builder.
    src0 = sql.split("src_new_0")[1].split("src_new_1")[0]
    src1 = sql.split("src_new_1")[1].split("source_new_union")[0]
    for sap_static in ("SAP/ORDERS", "SAP/ARCHIVE"):
        assert sap_static in src0, f"src_new_0 missing {sap_static!r}"
        assert sap_static not in src1, f"src_new_1 leaked {sap_static!r}"
    for web_static in ("WEB/EU/%", "WEB/US/%"):
        assert web_static in src1, f"src_new_1 missing {web_static!r}"
        assert web_static not in src0, f"src_new_0 leaked {web_static!r}"
