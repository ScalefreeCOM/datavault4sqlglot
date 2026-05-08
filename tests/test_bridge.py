"""
BridgeGenerator SQL generation tests.
Run with:  pytest tests/test_bridge.py -v -s
"""
from __future__ import annotations

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.bridge import BridgeGenerator, BridgeLink

LINK = BridgeLink(
    link_table="order_customer_nl",
    link_hash_key="hk_l_order_customer",
    driving_hash_key="hk_h_order",
    foreign_hash_keys=["hk_h_customer"],
    link_schema="RAW_VAULT",
    link_database="DV_DB",
)

TARGET = dict(
    target_database="DV_DB",
    target_schema="MART",
    target_table="order_bridge",
    hub_table="order_h",
    hub_hash_key="hk_h_order",
    hub_database="DV_DB",
    hub_schema="RAW_VAULT",
    links=[LINK],
    snapshot_table="snapshot_dates",
    snapshot_database="DV_DB",
    snapshot_schema="MART",
    snapshot_date_col="snapshot_date",
)


# ---------------------------------------------------------------------------
# 1. CROSS JOIN hub × snapshot_dates
# ---------------------------------------------------------------------------
def test_bridge_cross_join(write_sql):
    gen = BridgeGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("Bridge — CROSS JOIN hub × snapshot_dates", sql)
    assert "CROSS JOIN" in sql.upper()
    assert "order_h" in sql.lower()
    assert "snapshot_dates" in sql.lower()


# ---------------------------------------------------------------------------
# 2. LEFT JOIN the link on driving_hk and ldts <= snapshot_date
# ---------------------------------------------------------------------------
def test_bridge_left_join_link(write_sql):
    gen = BridgeGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("Bridge — LEFT JOIN link (driving_hk + ldts <= snap)", sql)
    assert "LEFT JOIN" in sql.upper()
    assert "order_customer_nl" in sql.lower()
    assert "hk_h_order" in sql.lower()
    assert "snapshot_date" in sql.lower()


# ---------------------------------------------------------------------------
# 3. Link hash key and foreign hash keys in SELECT
# ---------------------------------------------------------------------------
def test_bridge_link_keys_selected(write_sql):
    gen = BridgeGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("Bridge — Link keys in SELECT", sql)
    assert "hk_l_order_customer" in sql.lower()
    assert "hk_h_customer" in sql.lower()


# ---------------------------------------------------------------------------
# 4. No effectivity satellite — no extra join
# ---------------------------------------------------------------------------
def test_bridge_no_eff_sat(write_sql):
    gen = BridgeGenerator(**TARGET)
    sql = gen.to_sql()
    write_sql("Bridge — No effectivity satellite", sql)
    assert "is_active" not in sql.lower()
    assert "ledts" not in sql.lower()


# ---------------------------------------------------------------------------
# 5. With effectivity satellite — LEFT JOIN on eff_sat + ledts condition
# ---------------------------------------------------------------------------
def test_bridge_with_eff_sat(write_sql):
    link_with_eff = BridgeLink(
        link_table="order_customer_nl",
        link_hash_key="hk_l_order_customer",
        driving_hash_key="hk_h_order",
        foreign_hash_keys=["hk_h_customer"],
        link_schema="RAW_VAULT",
        link_database="DV_DB",
        eff_sat_table="order_customer_0_es",
        eff_sat_schema="RAW_VAULT",
        eff_sat_database="DV_DB",
    )
    gen = BridgeGenerator(**{**TARGET, "links": [link_with_eff]})
    sql = gen.to_sql()
    write_sql("Bridge — With effectivity satellite", sql)
    assert "order_customer_0_es" in sql.lower()
    assert config.ledts_alias in sql.lower()


# ---------------------------------------------------------------------------
# 6. Multiple links
# ---------------------------------------------------------------------------
def test_bridge_multiple_links(write_sql):
    link2 = BridgeLink(
        link_table="customer_account_nl",
        link_hash_key="hk_l_customer_account",
        driving_hash_key="hk_h_customer",
        foreign_hash_keys=["hk_h_account"],
    )
    gen = BridgeGenerator(**{**TARGET, "links": [LINK, link2]})
    sql = gen.to_sql()
    write_sql("Bridge — Multiple links", sql)
    assert "order_customer_nl" in sql.lower()
    assert "customer_account_nl" in sql.lower()
    assert "hk_h_account" in sql.lower()
