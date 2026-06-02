"""
AST-shape assertions for HubGenerator output.

Where test_hub.py confirms substrings appear in the generated SQL, these tests
parse the SQL back into a sqlglot AST and assert structural properties that
substring matches cannot — e.g. that the HWM filter uses `>` not `>=`, that
the rsrc_static CTE has the right number of UNION ALL branches, that the
COALESCE wraps MAX with the configured beginning_of_all_times.

These catch the class of regressions where the SQL "still mentions MAX" but
the operator, the column, or the CTE wiring has silently broken.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel


def _parse(sql: str) -> exp.Expression:
    return sqlglot.parse_one(sql, dialect=config.dialect)


def _find_cte(tree: exp.Expression, alias: str) -> exp.CTE | None:
    for cte in tree.find_all(exp.CTE):
        ident = cte.alias_or_name
        if ident == alias:
            return cte
    return None


def _binding(table: str, *, statics: list[str] | None = None) -> SourceBinding:
    return SourceBinding(
        source=SourceModel(
            table_name=table,
            load_date_col="LOAD_DATE",
            record_source_col="RECORD_SOURCE",
        ),
        rsrc_statics=statics,
    )


# ---------------------------------------------------------------------------
# rsrc_static HWM CTE — UNION ALL branch count + per-branch shape
# ---------------------------------------------------------------------------
def test_rsrc_static_hwm_cte_has_one_branch_per_static():
    """Two sources × one static each → two UNION ALL branches, no more, no less."""
    gen = HubGenerator(
        target_table="HUB_ORDER",
        sources=[
            _binding("STG_SAP", statics=["SAP/ORDERS"]),
            _binding("STG_WEB", statics=["WEB/%"]),
        ],
        hashkey="HK_ORDER_H",
        business_keys=["ORDER_ID"],
        is_incremental=True,
    )
    tree = _parse(gen.to_sql())
    hwm_cte = _find_cte(tree, "max_ldts_per_rsrc_static_in_target")
    assert hwm_cte is not None, "HWM CTE missing"

    # Top-level body is a chain of unions for N>1 statics. Count leaves.
    body = hwm_cte.this
    leaves = list(body.find_all(exp.Select))
    # find_all is a tree walk, but each SELECT in a UNION is still a leaf Select.
    # For two statics we expect exactly two leaf SELECTs.
    assert len(leaves) == 2, f"expected 2 UNION ALL branches, got {len(leaves)}"


def test_rsrc_static_hwm_branch_uses_like_not_equals():
    """Each HWM branch must filter rsrc with LIKE — '%' wildcard support depends on it."""
    gen = HubGenerator(
        target_table="HUB_ORDER",
        sources=[_binding("STG_WEB", statics=["WEB/%"])],
        hashkey="HK_ORDER_H",
        business_keys=["ORDER_ID"],
        is_incremental=True,
    )
    tree = _parse(gen.to_sql())
    hwm_cte = _find_cte(tree, "max_ldts_per_rsrc_static_in_target")
    assert hwm_cte is not None
    likes = list(hwm_cte.find_all(exp.Like))
    assert len(likes) >= 1, "HWM CTE must use LIKE for rsrc_static filtering"


# ---------------------------------------------------------------------------
# rsrc_static OR-filter on src_new_*
# ---------------------------------------------------------------------------
def test_src_new_filter_uses_strict_gt_not_gte():
    """The HWM ldts filter must be `>` — `>=` would cause duplicate inserts on overlap."""
    gen = HubGenerator(
        target_table="HUB_ORDER",
        sources=[_binding("STG_SAP", statics=["SAP/ORDERS"])],
        hashkey="HK_ORDER_H",
        business_keys=["ORDER_ID"],
        is_incremental=True,
    )
    tree = _parse(gen.to_sql())
    src_cte = _find_cte(tree, "src_new_0")
    assert src_cte is not None

    where = src_cte.find(exp.Where)
    assert where is not None, "src_new_0 must have a WHERE clause"

    # The WHERE must contain a GT (strict) and must NOT contain a GTE.
    gts = list(where.find_all(exp.GT))
    gtes = list(where.find_all(exp.GTE))
    assert gts, "src_new_0 WHERE must contain a strict-greater-than comparison"
    assert not gtes, "src_new_0 WHERE must not use >= (would produce duplicates on equal-ldts rows)"


def test_src_new_filter_coalesces_with_beginning_of_all_times():
    """Cold-start safety: COALESCE must wrap MAX with beginning_of_all_times."""
    beginning_of_all_times = "1900-01-01"
    config.beginning_of_all_times = beginning_of_all_times
    gen = HubGenerator(
        target_table="HUB_ORDER",
        sources=[_binding("STG_SAP", statics=["SAP/ORDERS"])],
        hashkey="HK_ORDER_H",
        business_keys=["ORDER_ID"],
        is_incremental=True,
    )
    tree = _parse(gen.to_sql())
    src_cte = _find_cte(tree, "src_new_0")
    assert src_cte is not None

    coalesces = list(src_cte.find_all(exp.Coalesce))
    assert coalesces, "src_new_0 must COALESCE the HWM lookup with beginning_of_all_times"
    # At least one COALESCE must mention the configured beginning_of_all_times literal.
    literals = [
        lit.this for c in coalesces for lit in c.find_all(exp.Literal) if lit.is_string
    ]
    assert beginning_of_all_times in literals, f"COALESCE must fall back to {beginning_of_all_times!r}, got literals={literals}"


def test_src_new_filter_branch_count_matches_statics():
    """Single source with N statics → N OR branches in the WHERE clause."""
    gen = HubGenerator(
        target_table="HUB_ORDER",
        sources=[_binding("STG_SAP", statics=["SAP/ORDERS", "SAP/ARCHIVE", "SAP/EXT"])],
        hashkey="HK_ORDER_H",
        business_keys=["ORDER_ID"],
        is_incremental=True,
    )
    tree = _parse(gen.to_sql())
    src_cte = _find_cte(tree, "src_new_0")
    assert src_cte is not None
    where = src_cte.find(exp.Where)
    assert where is not None

    # Top-level OR chain — count GT subexpressions, one per static.
    gts = list(where.find_all(exp.GT))
    assert len(gts) == 3, f"expected 3 GT branches for 3 statics, got {len(gts)}"


# ---------------------------------------------------------------------------
# Single-source-no-rsrc_static branch — global HWM via direct subquery
# ---------------------------------------------------------------------------
def test_single_source_no_static_uses_direct_target_hwm():
    """Without rsrc_static, a single source should HWM directly off the target."""
    gen = HubGenerator(
        target_table="HUB_ORDER",
        sources=[_binding("STG_ORDERS")],
        hashkey="HK_ORDER_H",
        business_keys=["ORDER_ID"],
        is_incremental=True,
    )
    tree = _parse(gen.to_sql())

    # No rsrc_static CTE should exist in this branch.
    assert _find_cte(tree, "max_ldts_per_rsrc_static_in_target") is None

    src_cte = _find_cte(tree, "src_new_0")
    assert src_cte is not None
    where = src_cte.find(exp.Where)
    assert where is not None
    # Strict-GT, COALESCE present, MAX present.
    assert list(where.find_all(exp.GT)), "WHERE missing strict >"
    assert list(where.find_all(exp.Coalesce)), "WHERE missing COALESCE"
    assert list(where.find_all(exp.Max)), "WHERE missing MAX(ldts)"


# ---------------------------------------------------------------------------
# Dedup window — partition + order
# ---------------------------------------------------------------------------
def test_dedup_window_partitions_by_hashkey_orders_by_ldts():
    """earliest_hk_over_all_sources must dedup by ROW_NUMBER over (hk, ldts)."""
    gen = HubGenerator(
        target_table="HUB_ORDER",
        sources=[_binding("STG_ORDERS")],
        hashkey="HK_ORDER_H",
        business_keys=["ORDER_ID"],
        is_incremental=False,
    )
    tree = _parse(gen.to_sql())
    dedup_cte = _find_cte(tree, "earliest_hk_over_all_sources")
    assert dedup_cte is not None

    windows = list(dedup_cte.find_all(exp.Window))
    assert windows, "dedup CTE must use a window function"
    win = windows[0]
    assert isinstance(win.this, exp.RowNumber), "dedup window must be ROW_NUMBER()"

    partition_cols = [c.name for c in win.args.get("partition_by", [])]
    assert "HK_ORDER_H" in partition_cols, f"partition cols={partition_cols}"

    order = win.args.get("order")
    assert order is not None, "dedup window needs ORDER BY"
    order_cols = [c.this.name for c in order.expressions]
    assert "ldts" in order_cols or "LOAD_DATE" in order_cols, f"order cols={order_cols}"
