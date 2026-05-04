from __future__ import annotations

from typing import List, Optional  # List kept for additional_columns type hint

from sqlglot import exp
from sqlglot.expressions import DataType

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceModel
from datavault4sqlglot.config import config


class EffSatGenerator(BaseGenerator):
    """
    Generates SQL for an Effectivity Satellite (eff_sat_v0).

    Tracks when a relationship (represented by tracked_hashkey) becomes
    active or inactive across load batches — matching the datavault4dbt
    eff_sat_v0 Snowflake pattern.

    Two modes:
      - Multi-batch (source_is_single_batch=False, default):
        Builds a cross-join of hashkeys × load_dates to detect disappearances,
        then deduplicates consecutive is_active states via LAG QUALIFY.
      - Single-batch (source_is_single_batch=True):
        Treats each load as a complete snapshot; new keys → active,
        absent keys → deactivated.

    Args:
        tracked_hashkey:     Column name of the relationship hash key.
        source_model:        Single source SourceModel (eff_sat is always single-source).
        is_active_alias:     Column name for the is_active boolean flag.
        source_is_single_batch: If True, use single-batch logic.
        additional_columns:  Extra columns to carry through.
        is_incremental:      If True, generate incremental-mode SQL.
        disable_hwm:         If True, skip high-water-mark filter.
        end_of_all_times:    End-of-all-times sentinel value.
        beginning_of_all_times: Beginning-of-all-times sentinel.
    """

    def __init__(
        self,
        target_table: str,
        source_model: SourceModel,
        tracked_hashkey: str,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        is_active_alias: str = "is_active",
        source_is_single_batch: bool = False,
        additional_columns: Optional[List[str]] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.source_model = source_model
        self.tracked_hashkey = tracked_hashkey
        self.is_active_alias = is_active_alias
        self.source_is_single_batch = source_is_single_batch
        self.additional_columns = additional_columns or []
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

    def generate_sql(self) -> exp.Expression:
        hk_col = self.tracked_hashkey
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        is_active_col = self.is_active_alias
        extra_cols = self.additional_columns
        eoa = self.end_of_all_times
        boa = self.beginning_of_all_times
        unknown_rsrc = config.default_unknown_rsrc

        src = self.source_model
        src_table_exp = self._get_table_expression(
            src.table_name, src.schema_name, src.database
        )
        src_hk = hk_col
        src_ldts = src.load_date_col or ldts_col
        src_rsrc = src.record_source_col or rsrc_col

        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )

        ctes: dict = {}

        # ---------------------------------------------------------
        # 1. source_data — exclude ghost records, optional HWM
        # ---------------------------------------------------------
        sd_select = [
            exp.column(src_hk).as_(hk_col),
            *[exp.column(col) for col in extra_cols],
            exp.column(src_ldts).as_(ldts_col),
            exp.column(src_rsrc).as_(rsrc_col),
        ]
        source_data_query = (
            exp.select(*sd_select)
            .from_(exp.alias_(src_table_exp, "src", table=True))
            .where(
                exp.not_(
                    exp.column(src_ldts).isin(
                        exp.Literal.string(boa), exp.Literal.string(eoa)
                    )
                )
            )
        )

        if self.is_incremental and not self.disable_hwm:
            hwm_sub = (
                exp.select(
                    exp.Coalesce(
                        this=exp.Max(this=exp.column(ldts_col)),
                        expressions=[exp.Literal.string(boa)],
                    )
                )
                .from_(target_exp)
                .where(
                    exp.column(ldts_col).neq(exp.Literal.string(eoa))
                )
            )
            source_data_query = source_data_query.where(
                exp.column(src_ldts) > exp.Paren(this=hwm_sub)
            )
        ctes["source_data"] = source_data_query

        # ---------------------------------------------------------
        # 2. current_status — latest is_active per tracked_hk (incremental)
        # ---------------------------------------------------------
        if self.is_incremental:
            cs_window = exp.Window(
                this=exp.RowNumber(),
                partition_by=[exp.column(hk_col)],
                order=exp.Order(
                    expressions=[exp.Ordered(this=exp.column(ldts_col), desc=True)]
                ),
            )
            cs_select = [
                exp.column(hk_col),
                *[exp.column(col) for col in extra_cols],
                exp.column(is_active_col),
                exp.column(rsrc_col),
            ]
            ctes["current_status"] = (
                exp.select(*cs_select)
                .from_(target_exp)
                .qualify(cs_window.eq(1))
            )

        last_cte: str

        if not self.source_is_single_batch:
            # -------------------------------------------------------
            # Multi-batch mode
            # -------------------------------------------------------

            # hashkeys: first appearance of each tracked_hk
            ctes["hashkeys"] = (
                exp.select(
                    exp.column(hk_col),
                    exp.Min(this=exp.column(ldts_col)).as_("first_appearance"),
                )
                .from_("source_data")
                .group_by(exp.column(hk_col))
            )

            # load_dates: distinct ldts in this batch
            ctes["load_dates"] = (
                exp.select(exp.column(ldts_col))
                .distinct()
                .from_("source_data")
            )

            # history: CROSS JOIN hashkeys × load_dates WHERE ldts >= first_appearance
            hk_tbl = exp.alias_(
                exp.Table(this=exp.Identifier(this="hashkeys")), "hk", table=True
            )
            ld_tbl = exp.alias_(
                exp.Table(this=exp.Identifier(this="load_dates")), "ld", table=True
            )
            ctes["history"] = (
                exp.select(
                    exp.column(hk_col, table="hk"),
                    exp.column(ldts_col, table="ld"),
                )
                .from_(hk_tbl)
                .join(ld_tbl, join_type="CROSS")
                .where(
                    exp.column(ldts_col, table="ld") >= exp.column("first_appearance", table="hk")
                )
            )

            # is_active: LEFT JOIN history → source_data to set is_active flag
            src_tbl_ref = exp.alias_(
                exp.Table(this=exp.Identifier(this="source_data")), "src", table=True
            )
            h_tbl_ref = exp.alias_(
                exp.Table(this=exp.Identifier(this="history")), "h", table=True
            )

            left_join_on = exp.and_(
                exp.column(hk_col, table="src").eq(exp.column(hk_col, table="h")),
                exp.column(ldts_col, table="src").eq(exp.column(ldts_col, table="h")),
            )

            is_active_expr = (
                exp.Case()
                .when(exp.column(hk_col, table="src").is_(exp.null()), exp.Literal.number(0))
                .else_(exp.Literal.number(1))
            ).as_(is_active_col)

            ia_select = [
                exp.column(hk_col, table="h").as_(hk_col),
                *[exp.column(col, table="src") for col in extra_cols],
                exp.column(ldts_col, table="h").as_(ldts_col),
                exp.Coalesce(
                    this=exp.column(rsrc_col, table="src"),
                    expressions=[exp.Literal.string(unknown_rsrc)],
                ).as_(rsrc_col),
                is_active_expr,
            ]
            ctes["is_active"] = (
                exp.select(*ia_select)
                .from_(h_tbl_ref)
                .join(src_tbl_ref, on=left_join_on, join_type="LEFT")
            )

            # deduplicated_incoming: LAG-based dedup on is_active per tracked_hk
            lag_window = exp.Window(
                this=exp.Lag(this=exp.column(is_active_col)),
                partition_by=[exp.column(hk_col)],
                order=exp.Order(
                    expressions=[exp.Ordered(this=exp.column(ldts_col))]
                ),
            )
            qualify_case = (
                exp.Case()
                .when(exp.column(is_active_col).eq(lag_window), exp.false())
                .else_(exp.true())
            )
            ctes["deduplicated_incoming"] = (
                exp.select("*").from_("is_active").qualify(qualify_case)
            )
            last_cte = "deduplicated_incoming"

        else:
            # -------------------------------------------------------
            # Single-batch mode
            # -------------------------------------------------------
            new_hk_select = [
                exp.column(hk_col, table="src").as_(hk_col),
                *[exp.column(col, table="src") for col in extra_cols],
                exp.column(ldts_col, table="src").as_(ldts_col),
                exp.column(rsrc_col, table="src").as_(rsrc_col),
                exp.Literal.number(1).as_(is_active_col),
            ]
            src_for_new = exp.alias_(
                exp.Table(this=exp.Identifier(this="source_data")), "src", table=True
            )
            new_hk_query = exp.select(*new_hk_select).distinct().from_(src_for_new)

            if self.is_incremental:
                # LEFT JOIN current_status; only rows where cs.hk IS NULL (not currently active)
                cs_join_tbl = exp.alias_(
                    exp.Table(this=exp.Identifier(this="current_status")),
                    "cs",
                    table=True,
                )
                bool_type = DataType.build("BOOLEAN")
                cs_join_on = exp.and_(
                    exp.column(hk_col, table="src").eq(
                        exp.column(hk_col, table="cs")
                    ),
                    exp.column(is_active_col, table="cs").eq(
                        exp.Cast(this=exp.Literal.number(1), to=bool_type)
                    ),
                )
                new_hk_query = (
                    new_hk_query
                    .join(cs_join_tbl, on=cs_join_on, join_type="LEFT")
                    .where(exp.column(hk_col, table="cs").is_(exp.null()))
                )

            ctes["new_hashkeys"] = new_hk_query
            last_cte = "new_hashkeys"

        # ---------------------------------------------------------
        # 3. disappeared_hashkeys (incremental only)
        # ---------------------------------------------------------
        if self.is_incremental:
            bool_type = DataType.build("BOOLEAN")

            if not self.source_is_single_batch:
                # min_ldts from deduplicated_incoming
                min_ldts_sub = exp.Subquery(
                    this=(
                        exp.select(exp.Min(this=exp.column(ldts_col)).as_("min_ldts"))
                        .from_("deduplicated_incoming")
                    ),
                    alias=exp.TableAlias(this=exp.Identifier(this="ldts")),
                )
                dis_join_src = exp.alias_(
                    exp.Table(this=exp.Identifier(this="deduplicated_incoming")),
                    "src",
                    table=True,
                )
                dis_left_join_on = exp.and_(
                    exp.column(hk_col, table="src").eq(
                        exp.column(hk_col, table="cs")
                    ),
                    exp.column(ldts_col, table="src").eq(
                        exp.column("min_ldts", table="ldts")
                    ),
                )
                dis_select = [
                    exp.column(hk_col, table="cs").as_(hk_col),
                    *[exp.null().as_(col) for col in extra_cols],
                    exp.column("min_ldts", table="ldts").as_(ldts_col),
                    exp.Literal.string(unknown_rsrc).as_(rsrc_col),
                    exp.Literal.number(0).as_(is_active_col),
                ]
                cs_tbl = exp.alias_(
                    exp.Table(this=exp.Identifier(this="current_status")),
                    "cs",
                    table=True,
                )
                disappeared_query = (
                    exp.select(*dis_select)
                    .distinct()
                    .from_(cs_tbl)
                    .join(min_ldts_sub, on=exp.Literal.number(1).eq(exp.Literal.number(1)), join_type="LEFT")
                    .join(dis_join_src, on=dis_left_join_on, join_type="LEFT")
                    .where(
                        exp.and_(
                            exp.column(is_active_col, table="cs").eq(
                                exp.Cast(this=exp.Literal.number(1), to=bool_type)
                            ),
                            exp.column(hk_col, table="src").is_(exp.null()),
                            exp.Not(this=exp.column("min_ldts", table="ldts").is_(exp.null())),
                        )
                    )
                )
            else:
                # single-batch: disappeared = in current_status as active, NOT in source_data
                min_ldts_sub = exp.Subquery(
                    this=(
                        exp.select(exp.Min(this=exp.column(ldts_col)).as_("min_ldts"))
                        .from_("source_data")
                    ),
                    alias=exp.TableAlias(this=exp.Identifier(this="ldts")),
                )
                not_exists_sub = (
                    exp.select(exp.Literal.number(1))
                    .from_("source_data")
                    .where(
                        exp.column(hk_col, table="source_data").eq(
                            exp.column(hk_col, table="cs")
                        )
                    )
                )
                dis_select = [
                    exp.column(hk_col, table="cs").as_(hk_col),
                    *[exp.null().as_(col) for col in extra_cols],
                    exp.column("min_ldts", table="ldts").as_(ldts_col),
                    exp.Literal.string(unknown_rsrc).as_(rsrc_col),
                    exp.Literal.number(0).as_(is_active_col),
                ]
                cs_tbl = exp.alias_(
                    exp.Table(this=exp.Identifier(this="current_status")),
                    "cs",
                    table=True,
                )
                disappeared_query = (
                    exp.select(*dis_select)
                    .distinct()
                    .from_(cs_tbl)
                    .join(min_ldts_sub, on=exp.Literal.number(1).eq(exp.Literal.number(1)), join_type="LEFT")
                    .where(
                        exp.and_(
                            exp.Not(this=exp.Exists(this=not_exists_sub)),
                            exp.column(is_active_col, table="cs").eq(
                                exp.Cast(this=exp.Literal.number(1), to=bool_type)
                            ),
                            exp.Not(this=exp.column("min_ldts", table="ldts").is_(exp.null())),
                        )
                    )
                )

            ctes["disappeared_hashkeys"] = disappeared_query

        # ---------------------------------------------------------
        # 4. records_to_insert
        # ---------------------------------------------------------
        bool_type = DataType.build("BOOLEAN")

        if self.is_incremental and not self.source_is_single_batch:
            # Multi-batch incremental: filter by current_status + exclude ldts before max(target ldts)
            min_ldts_di_sub = exp.Paren(
                this=(
                    exp.select(exp.Min(this=exp.column(ldts_col)))
                    .from_("deduplicated_incoming")
                )
            )
            max_target_ldts_sub = exp.Paren(
                this=(
                    exp.select(exp.Max(this=exp.column(ldts_col)))
                    .from_(target_exp)
                )
            )
            not_exists_cs = (
                exp.select(exp.Literal.number(1))
                .from_("current_status")
                .where(
                    exp.and_(
                        exp.column(hk_col, table="current_status").eq(
                            exp.column(hk_col, table="di")
                        ),
                        exp.Cast(
                            this=exp.column(is_active_col, table="di"),
                            to=bool_type,
                        ).eq(exp.column(is_active_col, table="current_status")),
                        exp.column(ldts_col, table="di").eq(min_ldts_di_sub),
                    )
                )
            )
            di_tbl = exp.alias_(
                exp.Table(this=exp.Identifier(this=last_cte)), "di", table=True
            )
            part1 = (
                exp.select(exp.column("*", table="di"))
                .from_(di_tbl)
                .where(
                    exp.and_(
                        exp.Not(this=exp.Exists(this=not_exists_cs)),
                        exp.column(ldts_col, table="di") > max_target_ldts_sub,
                    )
                )
            )
            part2 = exp.select("*").from_("disappeared_hashkeys")
            insert_query = part1.union(part2, distinct=False)

        elif self.is_incremental and self.source_is_single_batch:
            # Single-batch incremental: union new_hashkeys + disappeared_hashkeys
            part1 = exp.select("*").from_(last_cte)
            part2 = exp.select("*").from_("disappeared_hashkeys")
            insert_query = part1.union(part2, distinct=False)

        else:
            insert_query = exp.select("*").from_(last_cte)

        ctes["records_to_insert"] = insert_query

        # ---------------------------------------------------------
        # 5. Final SELECT — cast is_active to BOOLEAN, deduplicate against target
        # ---------------------------------------------------------
        is_active_cast = exp.Cast(
            this=exp.column(is_active_col, table="ri"),
            to=bool_type,
        ).as_(exp.Identifier(this=is_active_col, quoted=True))

        final_cols = [
            exp.column(hk_col, table="ri").as_(hk_col),
            *[exp.column(col, table="ri") for col in extra_cols],
            exp.column(ldts_col, table="ri").as_(ldts_col),
            exp.column(rsrc_col, table="ri").as_(rsrc_col),
            is_active_cast,
        ]

        ri_tbl = exp.alias_(
            exp.Table(this=exp.Identifier(this="records_to_insert")), "ri", table=True
        )
        final_query = exp.select(*final_cols).from_(ri_tbl)

        if self.is_incremental:
            not_exists_target = (
                exp.select(exp.Literal.number(1))
                .from_(exp.alias_(target_exp, "t", table=True))
                .where(
                    exp.and_(
                        exp.column(hk_col, table="t").eq(
                            exp.column(hk_col, table="ri")
                        ),
                        exp.column(ldts_col, table="t").eq(
                            exp.column(ldts_col, table="ri")
                        ),
                    )
                )
            )
            final_query = final_query.where(
                exp.Not(this=exp.Exists(this=not_exists_target))
            )

        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)

        return final_query
