from __future__ import annotations

from typing import List, Optional

import sqlglot
from sqlglot import exp
from sqlglot.expressions import DataType

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceBinding
from datavault4sqlglot.config import config


class RecordTrackingSatGenerator(BaseGenerator):
    """
    Generates SQL for a Record Tracking Satellite (rec_track_sat).

    Tracks which source staging models contributed each hash key + load date
    combination. One DISTINCT row per (tracked_hk, ldts, rsrc, stg) — matching
    the datavault4dbt rec_track_sat Snowflake pattern.

    Incremental deduplication is done via CONCAT(hk || ldts || rsrc) comparison
    against the existing target rather than a hash comparison.

    Args:
        tracked_hashkey:  Hash key column to track.
        source_models:    List of SourceModel; each produces a src_new_N CTE.
        stg_alias:        Column name for the staging-model-name column (default: "stg").
        additional_columns: Extra columns to carry through.
        is_incremental:   If True, generate incremental-mode SQL.
        disable_hwm:      If True, skip high-water-mark filter.
        end_of_all_times: End-of-all-times sentinel.
        beginning_of_all_times: Beginning-of-all-times sentinel.
    """

    def __init__(
        self,
        target_table: str,
        sources: List[SourceBinding],
        tracked_hashkey: str,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        stg_alias: str = "stg",
        additional_columns: Optional[List[str]] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.sources = sources
        self.tracked_hashkey = tracked_hashkey
        self.stg_alias = stg_alias
        self.additional_columns = additional_columns or []
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

    def generate_sql(self) -> exp.Expression:
        hk_col = self.tracked_hashkey
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        stg_col = self.stg_alias
        extra_cols = self.additional_columns
        eoa = self.end_of_all_times
        boa = self.beginning_of_all_times

        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )

        varchar_type = self._get_type(DataType.Type.VARCHAR, 4000)

        ctes: dict = {}

        # ---------------------------------------------------------
        # Determine whether any source has rsrc_statics defined
        # ---------------------------------------------------------
        has_rsrc_statics = any(bool(b.rsrc_statics) for b in self.sources)

        # ---------------------------------------------------------
        # 1. Incremental dedup anchor: distinct CONCAT in target
        # ---------------------------------------------------------
        if self.is_incremental:
            concat_expr = exp.Concat(
                expressions=[
                    exp.Cast(this=exp.column(hk_col), to=varchar_type),
                    exp.column(ldts_col),
                    exp.column(rsrc_col),
                ]
            ).as_("concat")
            ctes["distinct_concated_target"] = (
                exp.select(concat_expr).from_(target_exp)
            )

        # ---------------------------------------------------------
        # 2. HWM CTE (per-rsrc_static, when rsrc_statics defined)
        # ---------------------------------------------------------
        hwm_cte_name = "max_ldts_per_rsrc_static_in_target"

        if self.is_incremental and has_rsrc_statics and not self.disable_hwm:
            hwm_query = self._build_rsrc_static_hwm_query(
                self.sources, target_exp, ldts_col, rsrc_col, eoa
            )
            if hwm_query is not None:
                ctes[hwm_cte_name] = hwm_query

        # ---------------------------------------------------------
        # 3. Per-source src_new_N CTEs
        # ---------------------------------------------------------
        source_cte_names = []

        for idx, binding in enumerate(self.sources):
            src = binding.source
            src_table_exp = self._get_table_expression(
                src.table_name, src.schema_name, src.database
            )
            src_hk = binding.hash_key_col or hk_col
            src_ldts = src.load_date_col or ldts_col
            src_rsrc = src.record_source_col or rsrc_col
            statics = binding.rsrc_statics or []
            src_extra = binding.additional_columns or extra_cols

            # Stage name literal: UPPER(table_name)
            stg_literal = exp.Cast(
                this=exp.Upper(this=exp.Literal.string(src.table_name)),
                to=varchar_type,
            ).as_(stg_col)

            if statics:
                # One UNION ALL branch per rsrc_static — rsrc is the static literal
                per_static_selects = []
                for sv in statics:
                    rsrc_literal = exp.Cast(
                        this=exp.Literal.string(sv),
                        to=varchar_type,
                    ).as_(rsrc_col)
                    select_exprs = [
                        exp.column(src_hk).as_(hk_col),
                        exp.column(src_ldts).as_(ldts_col),
                        rsrc_literal,
                        stg_literal,
                        *[exp.column(col) for col in src_extra],
                    ]
                    q = exp.select(*select_exprs).distinct().from_(
                        exp.alias_(src_table_exp, "src", table=True)
                    )
                    if (
                        self.is_incremental
                        and has_rsrc_statics
                        and hwm_cte_name in ctes
                        and not self.disable_hwm
                    ):
                        max_sub = (
                            exp.select(exp.column("max_ldts"))
                            .from_(hwm_cte_name)
                            .where(
                                exp.column("rsrc_static").like(exp.Literal.string(sv))
                            )
                        )
                        q = q.join(
                            exp.alias_(
                                exp.Table(this=exp.Identifier(this=hwm_cte_name)),
                                "max",
                                table=True,
                            ),
                            on=exp.column("rsrc_static", table="max").like(
                                exp.Literal.string(sv)
                            ),
                            join_type="LEFT",
                        ).where(
                            exp.column(src_ldts, table="src")
                            > exp.Coalesce(
                                this=exp.column("max_ldts", table="max"),
                                expressions=[exp.Literal.string(boa)],
                            )
                        )
                    per_static_selects.append(q)

                if len(per_static_selects) > 1:
                    src_query = sqlglot.union(*per_static_selects, distinct=False)
                else:
                    src_query = per_static_selects[0]

            else:
                # No rsrc_statics — use actual rsrc column
                rsrc_cast = exp.Cast(
                    this=exp.column(src_rsrc),
                    to=varchar_type,
                ).as_(rsrc_col)
                select_exprs = [
                    exp.column(src_hk).as_(hk_col),
                    exp.column(src_ldts).as_(ldts_col),
                    rsrc_cast,
                    stg_literal,
                    *[exp.column(col) for col in src_extra],
                ]
                src_query = exp.select(*select_exprs).distinct().from_(
                    exp.alias_(src_table_exp, "src", table=True)
                )
                if self.is_incremental and not self.disable_hwm and len(self.sources) == 1:
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
                    src_query = src_query.where(
                        exp.column(src_ldts, table="src") > exp.Paren(this=hwm_sub)
                    )

            cte_name = f"src_new_{idx}"
            ctes[cte_name] = src_query
            source_cte_names.append(cte_name)

        # ---------------------------------------------------------
        # 4. Union all sources
        # ---------------------------------------------------------
        if len(source_cte_names) > 1:
            union_query = exp.select("*").from_(source_cte_names[0])
            for name in source_cte_names[1:]:
                union_query = union_query.union(
                    exp.select("*").from_(name), distinct=False
                )
            ctes["source_new_union"] = union_query
            last_cte = "source_new_union"
        else:
            last_cte = source_cte_names[0]

        # ---------------------------------------------------------
        # 5. records_to_insert — exclude ghost records and existing rows
        # ---------------------------------------------------------
        final_cols = [hk_col, ldts_col, rsrc_col, stg_col, *extra_cols]
        insert_query = (
            exp.select(*[exp.column(c) for c in final_cols])
            .from_(last_cte)
            .where(
                exp.not_(
                    exp.column(ldts_col).isin(
                        exp.Literal.string(eoa), exp.Literal.string(boa)
                    )
                )
            )
        )

        if self.is_incremental:
            concat_check = exp.Concat(
                expressions=[
                    exp.Cast(this=exp.column(hk_col), to=varchar_type),
                    exp.column(ldts_col),
                    exp.column(rsrc_col),
                ]
            )
            insert_query = insert_query.where(
                concat_check.isin(
                    exp.select(exp.column("concat")).from_("distinct_concated_target")
                ).not_()
            )

        ctes["records_to_insert"] = insert_query

        # ---------------------------------------------------------
        # 6. Final SELECT + assemble CTEs
        # ---------------------------------------------------------
        final_query = exp.select("*").from_("records_to_insert")
        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)

        return final_query
