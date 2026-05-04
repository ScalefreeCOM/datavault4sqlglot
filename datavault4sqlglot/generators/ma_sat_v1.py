from __future__ import annotations

from typing import Optional

from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.config import config


class MultiActiveSatV1Generator(BaseGenerator):
    """
    Generates SQL for an end-dated Multi-Active Satellite v1 (ma_sat_v1).

    Reads from an underlying MA Sat v0 table and computes a load-end-timestamp
    (ledts) per (parent_hash_key, load_date) via LEAD — matching the
    datavault4dbt ma_sat_v1 Snowflake pattern.

    CTE chain:
        source_satellite  — SELECT * FROM sat_v0
        distinct_hk_ldts  — DISTINCT (parent_hk, ldts) pairs
        end_dated_loads   — LEAD-based ledts per parent_hk
        end_dated_source  — JOIN source with end_dated_loads + optional IS_CURRENT
    """

    def __init__(
        self,
        target_table: str,
        sat_v0_table: str,
        parent_hash_key: str,
        hash_diff: str,
        sat_v0_schema: Optional[str] = None,
        sat_v0_database: Optional[str] = None,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        payload: Optional[list[str]] = None,
        ma_attribute: Optional[list[str]] = None,
        add_is_current: bool = True,
        ledts_alias: Optional[str] = None,
        is_current_col: str = "is_current",
        end_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.sat_v0_table = sat_v0_table
        self.sat_v0_schema = sat_v0_schema
        self.sat_v0_database = sat_v0_database
        self.parent_hash_key = parent_hash_key
        self.hash_diff = hash_diff
        self.payload = payload or []
        self.ma_attribute = ma_attribute or []
        self.add_is_current = add_is_current
        self.ledts_alias = ledts_alias or config.ledts_alias
        self.is_current_col = is_current_col
        self.end_of_all_times = end_of_all_times or config.end_of_all_times

    def generate_sql(self) -> exp.Expression:
        parent_hk_col = self.parent_hash_key
        hash_diff_col = self.hash_diff
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        ledts_col = self.ledts_alias
        eoa = self.end_of_all_times

        src_exp = self._get_table_expression(
            self.sat_v0_table, self.sat_v0_schema, self.sat_v0_database
        )

        # ---------------------------------------------------------
        # CTE 1: source_satellite
        # ---------------------------------------------------------
        source_sat_query = exp.select(exp.Star()).from_(src_exp)

        # ---------------------------------------------------------
        # CTE 2: distinct_hk_ldts — one row per (parent_hk, ldts)
        # ---------------------------------------------------------
        distinct_hk_ldts_query = (
            exp.select(exp.column(parent_hk_col), exp.column(ldts_col))
            .distinct()
            .from_("source_satellite")
        )

        # ---------------------------------------------------------
        # CTE 3: end_dated_loads
        # COALESCE(LEAD(ldts) OVER (PARTITION BY parent_hk ORDER BY ldts),
        #          end_of_all_times) AS ledts
        # ---------------------------------------------------------
        lead_window = exp.Window(
            this=exp.Lead(this=exp.column(ldts_col)),
            partition_by=[exp.column(parent_hk_col)],
            order=exp.Order(
                expressions=[exp.Ordered(this=exp.column(ldts_col))]
            ),
        )
        ledts_expr = exp.Coalesce(
            this=lead_window,
            expressions=[exp.Literal.string(eoa)],
        ).as_(exp.Identifier(this=ledts_col, quoted=True))

        end_dated_loads_query = (
            exp.select(
                exp.column(parent_hk_col),
                exp.column(ldts_col),
                ledts_expr,
            )
            .from_("distinct_hk_ldts")
        )

        # ---------------------------------------------------------
        # CTE 4: end_dated_source
        # JOIN source_satellite with end_dated_loads on (parent_hk, ldts)
        # ---------------------------------------------------------
        src_alias = "src"
        edl_alias = "edl"

        join_on = exp.and_(
            exp.column(parent_hk_col, table=src_alias).eq(
                exp.column(parent_hk_col, table=edl_alias)
            ),
            exp.column(ldts_col, table=src_alias).eq(
                exp.column(ldts_col, table=edl_alias)
            ),
        )

        src_tbl = exp.alias_(
            exp.Table(this=exp.Identifier(this="source_satellite")),
            src_alias,
            table=True,
        )
        edl_tbl = exp.alias_(
            exp.Table(this=exp.Identifier(this="end_dated_loads")),
            edl_alias,
            table=True,
        )

        # Explicit columns: hk, hashdiff, rsrc, ldts, ledts, ma_attributes, payload, IS_CURRENT
        select_cols: list[exp.Expression] = [
            exp.column(parent_hk_col, table=src_alias).as_(parent_hk_col),
            exp.column(hash_diff_col, table=src_alias).as_(hash_diff_col),
            exp.column(rsrc_col, table=src_alias).as_(rsrc_col),
            exp.column(ldts_col, table=src_alias).as_(ldts_col),
            exp.column(ledts_col, table=edl_alias).as_(ledts_col),
        ]

        if self.add_is_current:
            is_current_expr = (
                exp.Case()
                .when(
                    exp.column(ledts_col, table=edl_alias).eq(exp.Literal.string(eoa)),
                    exp.true(),
                )
                .else_(exp.false())
            ).as_(exp.Identifier(this=self.is_current_col, quoted=True))
            select_cols.append(is_current_expr)

        for attr in self.ma_attribute:
            select_cols.append(exp.column(attr, table=src_alias).as_(attr))

        for col in self.payload:
            select_cols.append(exp.column(col, table=src_alias).as_(col))

        end_dated_source_query = (
            exp.select(*select_cols)
            .from_(src_tbl)
            .join(edl_tbl, on=join_on, join_type="LEFT")
        )

        # ---------------------------------------------------------
        # Final select + assemble CTEs
        # ---------------------------------------------------------
        final_query = exp.select("*").from_("end_dated_source")
        for name, expr in [
            ("source_satellite", source_sat_query),
            ("distinct_hk_ldts", distinct_hk_ldts_query),
            ("end_dated_loads", end_dated_loads_query),
            ("end_dated_source", end_dated_source_query),
        ]:
            final_query = final_query.with_(name, as_=expr)

        return final_query
