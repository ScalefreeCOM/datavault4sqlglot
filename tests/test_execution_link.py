"""
DuckDB execution tests for LinkGenerator — full Link matrix.

Test numbering mirrors the test-spec hierarchy:

    3    Link
    3.1      one source, two FHKs
    3.1.1      initial
    3.1.2      incremental
    3.2      two sources, two FHKs
    3.2.1      initial
    3.2.2      incremental

Conventions used across all tests:
- Link hashkey:    HK_LNK_ORDER_CUSTOMER_L
- Foreign HKs:     HK_ORDER_H, HK_CUSTOMER_H
- LDTS / RSRC names: read from config.ldts_alias / config.rsrc_alias —
                     the casing follows whatever the project configures,
                     it is not hardcoded here.
- Stage LDTS values are always >= 2026-01-03 so the global-HWM filter
  used by the single-source incremental path never accidentally drops them.

Run with:  pytest tests/test_execution_link.py -v -s
"""
from __future__ import annotations

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.link import LinkGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _binding(
    table: str,
    *,
    fk_columns: list[str] | None = None,
) -> SourceBinding:
    """
    Build a SourceBinding for STG_<table>.

    `fk_columns` are the per-source physical *hashkey* columns that carry the
    parent-hub hashkeys this link references — not raw business keys. They
    map positionally to the canonical ``foreign_hash_keys`` declared on the
    link; when a physical name differs from the canonical, the generator
    emits ``physical AS canonical`` so multi-source UNIONs line up by name.
    """
    return SourceBinding(
        source=SourceModel(
            database="RAW_DB",
            schema="STAGE",
            table_name=table,
            load_date_col="LOAD_DATE",
            record_source_col="RECORD_SOURCE",
        ),
        fk_columns=fk_columns,
    )


def _link(*sources: SourceBinding, incremental: bool) -> LinkGenerator:
    return LinkGenerator(
        target_database="DV",
        target_schema="RAW_VAULT",
        target_table="LNK_ORDER_CUSTOMER",
        sources=list(sources),
        link_hash_key="HK_LNK_ORDER_CUSTOMER_L",
        foreign_hash_keys=["HK_ORDER_H", "HK_CUSTOMER_H"],
        is_incremental=incremental,
        dialect="duckdb",
    )


# ===========================================================================
# 3.1.1 — Initial load, one source
# ===========================================================================

def test_3_1_1_1_initial_same_hk_two_batches(seed, run_select, dump):
    """Same link HK appears over two batches → only the earliest is inserted."""
    ldts = config.ldts_alias

    seed("RAW_DB.STAGE.STG_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk1",
         "HK_ORDER_H": "ord_a", "HK_CUSTOMER_H": "cust_a",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "ERP/ORDERS"},
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk1",
         "HK_ORDER_H": "ord_a", "HK_CUSTOMER_H": "cust_a",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "ERP/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_ORDERS", label="3.1.1.1 stage")

    sql = _link(_binding("STG_ORDERS"), incremental=False).to_sql()
    rows = run_select(sql)
    dump(sql, label="3.1.1.1 result")

    assert len(rows) == 1
    assert rows[0]["HK_LNK_ORDER_CUSTOMER_L"] == "lnk1"
    assert rows[0][ldts] == "2026-01-03"


# ===========================================================================
# 3.1.2 — Incremental load, one source
# ===========================================================================

def test_3_1_2_1_incremental_existing_hk_in_incoming(seed, run_select, dump):
    """Existing link HK appears in incoming batch → no inserts."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk1",
         "HK_ORDER_H": "ord_a", "HK_CUSTOMER_H": "cust_a",
         ldts: "2026-01-01", rsrc: "ERP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk1",
         "HK_ORDER_H": "ord_a", "HK_CUSTOMER_H": "cust_a",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "ERP/ORDERS"},
    ])
    dump("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", label="3.1.2.1 target (existing)")
    dump("RAW_DB.STAGE.STG_ORDERS",         label="3.1.2.1 stage")

    sql = _link(_binding("STG_ORDERS"), incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="3.1.2.1 result")

    assert rows == []


def test_3_1_2_2_incremental_new_hk_two_batches(seed, run_select, dump):
    """New link HK appears in two incoming batches → earliest is inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_existing",
         "HK_ORDER_H": "ord_e", "HK_CUSTOMER_H": "cust_e",
         ldts: "2026-01-01", rsrc: "ERP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_new",
         "HK_ORDER_H": "ord_n", "HK_CUSTOMER_H": "cust_n",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "ERP/ORDERS"},
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_new",
         "HK_ORDER_H": "ord_n", "HK_CUSTOMER_H": "cust_n",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "ERP/ORDERS"},
    ])
    dump("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", label="3.1.2.2 target")
    dump("RAW_DB.STAGE.STG_ORDERS",         label="3.1.2.2 stage")

    sql = _link(_binding("STG_ORDERS"), incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="3.1.2.2 result")

    assert len(rows) == 1
    assert rows[0]["HK_LNK_ORDER_CUSTOMER_L"] == "lnk_new"
    assert rows[0][ldts] == "2026-01-03"


def test_3_1_2_3_incremental_new_hk_one_batch(seed, run_select, dump):
    """New link HK appears in one incoming batch → inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_existing",
         "HK_ORDER_H": "ord_e", "HK_CUSTOMER_H": "cust_e",
         ldts: "2026-01-01", rsrc: "ERP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_new",
         "HK_ORDER_H": "ord_n", "HK_CUSTOMER_H": "cust_n",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "ERP/ORDERS"},
    ])
    dump("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", label="3.1.2.3 target")
    dump("RAW_DB.STAGE.STG_ORDERS",         label="3.1.2.3 stage")

    sql = _link(_binding("STG_ORDERS"), incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="3.1.2.3 result")

    assert len(rows) == 1
    assert rows[0]["HK_LNK_ORDER_CUSTOMER_L"] == "lnk_new"
    assert rows[0][ldts] == "2026-01-05"


# ===========================================================================
# 3.2.1 — Initial load, two sources
# ===========================================================================

def test_3_2_1_1_initial_same_hk_diff_ldts(seed, run_select, dump):
    """Same link HK in both sources, different LDTS → earliest is inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk1",
         "HK_ORDER_H": "ord_a", "HK_CUSTOMER_H": "cust_a",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk1",
         "HK_ORDER_H": "ord_a", "HK_CUSTOMER_H": "cust_a",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_SAP_ORDERS", label="3.2.1.1 SAP")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS", label="3.2.1.1 WEB")

    sql = _link(
        _binding("STG_SAP_ORDERS"),
        _binding("STG_WEB_ORDERS"),
        incremental=False,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="3.2.1.1 result")

    assert len(rows) == 1
    assert rows[0]["HK_LNK_ORDER_CUSTOMER_L"] == "lnk1"
    assert rows[0][ldts] == "2026-01-03"
    assert rows[0][rsrc] == "WEB/ORDERS"


def test_3_2_1_2_initial_different_hks(seed, run_select, dump):
    """Each source has a different link HK → both are inserted."""
    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_sap",
         "HK_ORDER_H": "ord_s", "HK_CUSTOMER_H": "cust_s",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_web",
         "HK_ORDER_H": "ord_w", "HK_CUSTOMER_H": "cust_w",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_SAP_ORDERS", label="3.2.1.2 SAP")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS", label="3.2.1.2 WEB")

    sql = _link(
        _binding("STG_SAP_ORDERS"),
        _binding("STG_WEB_ORDERS"),
        incremental=False,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="3.2.1.2 result")

    assert {r["HK_LNK_ORDER_CUSTOMER_L"] for r in rows} == {"lnk_sap", "lnk_web"}


# ===========================================================================
# 3.2.2 — Incremental load, two sources
# ===========================================================================

def test_3_2_2_1_incremental_existing_one_source_new_other(
    seed, run_select, dump
):
    """Existing HK in source A, new HK in source B → only the new HK inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_existing",
         "HK_ORDER_H": "ord_e", "HK_CUSTOMER_H": "cust_e",
         ldts: "2026-01-01", rsrc: "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_existing",
         "HK_ORDER_H": "ord_e", "HK_CUSTOMER_H": "cust_e",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_new",
         "HK_ORDER_H": "ord_n", "HK_CUSTOMER_H": "cust_n",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", label="3.2.2.1 target")
    dump("RAW_DB.STAGE.STG_SAP_ORDERS",     label="3.2.2.1 SAP")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS",     label="3.2.2.1 WEB")

    sql = _link(
        _binding("STG_SAP_ORDERS"),
        _binding("STG_WEB_ORDERS"),
        incremental=True,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="3.2.2.1 result")

    assert len(rows) == 1
    assert rows[0]["HK_LNK_ORDER_CUSTOMER_L"] == "lnk_new"
    assert rows[0][rsrc] == "WEB/ORDERS"


def test_3_2_2_2_incremental_existing_in_both(seed, run_select, dump):
    """Existing HK appears in both sources → no inserts."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk1",
         "HK_ORDER_H": "ord_a", "HK_CUSTOMER_H": "cust_a",
         ldts: "2026-01-01", rsrc: "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk1",
         "HK_ORDER_H": "ord_a", "HK_CUSTOMER_H": "cust_a",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk1",
         "HK_ORDER_H": "ord_a", "HK_CUSTOMER_H": "cust_a",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", label="3.2.2.2 target")
    dump("RAW_DB.STAGE.STG_SAP_ORDERS",     label="3.2.2.2 SAP")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS",     label="3.2.2.2 WEB")

    sql = _link(
        _binding("STG_SAP_ORDERS"),
        _binding("STG_WEB_ORDERS"),
        incremental=True,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="3.2.2.2 result")

    assert rows == []


def test_3_2_2_3_incremental_new_hk_both_sources_diff_ldts(
    seed, run_select, dump
):
    """New HK in both sources with different LDTS → earliest is inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_existing",
         "HK_ORDER_H": "ord_e", "HK_CUSTOMER_H": "cust_e",
         ldts: "2026-01-01", rsrc: "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_new",
         "HK_ORDER_H": "ord_n", "HK_CUSTOMER_H": "cust_n",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_new",
         "HK_ORDER_H": "ord_n", "HK_CUSTOMER_H": "cust_n",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("DV.RAW_VAULT.LNK_ORDER_CUSTOMER", label="3.2.2.3 target")
    dump("RAW_DB.STAGE.STG_SAP_ORDERS",     label="3.2.2.3 SAP")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS",     label="3.2.2.3 WEB")

    sql = _link(
        _binding("STG_SAP_ORDERS"),
        _binding("STG_WEB_ORDERS"),
        incremental=True,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="3.2.2.3 result")

    assert len(rows) == 1
    assert rows[0]["HK_LNK_ORDER_CUSTOMER_L"] == "lnk_new"
    assert rows[0][ldts] == "2026-01-03"
    assert rows[0][rsrc] == "WEB/ORDERS"


# ===========================================================================
# 3.2.3 — Per-source FK aliasing (different physical FHK column names)
# ===========================================================================

def test_3_2_3_1_initial_per_source_fk_aliasing(seed, run_select, dump):
    """
    Both sources point to the same logical hubs (Order, Customer) but each
    staging pipeline carries the parent hashkeys under different physical
    column names. fk_columns on each binding maps those physical hashkey
    columns positionally to the canonical foreign_hash_keys declared on the
    link (HK_ORDER_H / HK_CUSTOMER_H), so the per-source UNION lines up by
    name.
    """
    # SAP staging carries the parent hashkeys as HK_SAP_ORDER / HK_SAP_CUSTOMER.
    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_sap",
         "HK_SAP_ORDER": "hk_ord_s", "HK_SAP_CUSTOMER": "hk_cust_s",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    # WEB staging carries them as HK_WEB_ORDER / HK_WEB_CUSTOMER.
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_LNK_ORDER_CUSTOMER_L": "lnk_web",
         "HK_WEB_ORDER": "hk_ord_w", "HK_WEB_CUSTOMER": "hk_cust_w",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_SAP_ORDERS", label="3.2.3.1 SAP (HK_SAP_ORDER/HK_SAP_CUSTOMER)")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS", label="3.2.3.1 WEB (HK_WEB_ORDER/HK_WEB_CUSTOMER)")

    sql = _link(
        _binding("STG_SAP_ORDERS", fk_columns=["HK_SAP_ORDER", "HK_SAP_CUSTOMER"]),
        _binding("STG_WEB_ORDERS", fk_columns=["HK_WEB_ORDER", "HK_WEB_CUSTOMER"]),
        incremental=False,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="3.2.3.1 result")

    # Both rows land, and both expose the canonical hashkey column names —
    # the UNION would have failed if positional aliasing weren't applied.
    by_lnk = {r["HK_LNK_ORDER_CUSTOMER_L"]: r for r in rows}
    assert set(by_lnk) == {"lnk_sap", "lnk_web"}
    assert by_lnk["lnk_sap"]["HK_ORDER_H"] == "hk_ord_s"
    assert by_lnk["lnk_sap"]["HK_CUSTOMER_H"] == "hk_cust_s"
    assert by_lnk["lnk_web"]["HK_ORDER_H"] == "hk_ord_w"
    assert by_lnk["lnk_web"]["HK_CUSTOMER_H"] == "hk_cust_w"
