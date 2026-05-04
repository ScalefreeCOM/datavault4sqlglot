from __future__ import annotations

from typing import Dict, List, Optional, Union

import sqlglot
from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceModel
from datavault4sqlglot.config import config


class MultiActiveSatV0Generator(BaseGenerator):
    """
    Generates SQL for a Multi-Active Satellite v0 (ma_sat_v0).

    Multi-Active Satellites are always single-source. Handles multiple
    simultaneously-active records per parent hash key (e.g., multiple phone
    numbers per customer). Deduplication is LAG-based, partitioned by
    parent_hash_key, ordered by ldts — matching datavault4dbt ma_sat_v0.

    HWM uses the global MAX(ldts) from the target table (no rsrc_static scoping).

    CTE chain:
        src_new                 — SELECT with optional HWM filter
        latest_entries_in_sat   — most recent hashdiff per parent_hk (incremental)
        deduped_row_hashdiff    — consecutive-hashdiff dedup via LAG QUALIFY
        deduped_rows            — INNER JOIN source back to deduped keys
        records_to_insert       — NOT EXISTS filter against latest target state
    """

    def __init__(
        self,
        target_table: str,
        source_model: SourceModel,
        parent_hash_key: str,
        hash_diff: Union[str, Dict[str, str]],
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        payload: Optional[List[str]] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        additional_columns: Optional[List[str]] = None,
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.source_model = source_model
        self.parent_hash_key = parent_hash_key
        self.hash_diff = hash_diff
        self.payload = payload or []
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.additional_columns = additional_columns or []
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

    def generate_sql(self) -> exp.Expression:
        src = self.source_model
        parent_hk_col = self.parent_hash_key
        _, hash_diff_col = self._resolve_column_config(self.hash_diff)
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        boa = self.beginning_of_all_times

        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )
        src_table_exp = self._get_table_expression(
            src.table_name, src.schema_name, src.database
        )

        src_parent_hk = parent_hk_col
        src_hd_src, _ = self._resolve_column_config(self.hash_diff)
        src_payload = self.payload
        extra_cols = self.additional_columns
        src_ldts = src.load_date_col or ldts_col
        src_rsrc = src.record_source_col or rsrc_col

        ctes: dict = {}

        # ---------------------------------------------------------
        # 1. Source CTE with optional global HWM filter
        # ---------------------------------------------------------
        select_exprs = [
            exp.column(src_parent_hk).as_(parent_hk_col),
            exp.column(src_hd_src).as_(hash_diff_col),
            *[exp.column(p) for p in src_payload],
            *[exp.column(col) for col in extra_cols],
            exp.column(src_ldts).as_(ldts_col),
            exp.column(src_rsrc).as_(rsrc_col),
        ]
        src_query = exp.select(*select_exprs).from_(src_table_exp)

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
                    exp.column(ldts_col).neq(
                        exp.Literal.string(self.end_of_all_times)
                    )
                )
            )
            src_query = src_query.where(
                exp.column(src_ldts) > exp.Paren(this=hwm_sub)
            )

        ctes["src_new"] = src_query

        # ---------------------------------------------------------
        # 2. Incremental: latest hashdiff per parent_hk in target
        # ---------------------------------------------------------
        if self.is_incremental:
            latest_target_cte = "latest_entries_in_sat"
            target_window = exp.Window(
                this=exp.RowNumber(),
                partition_by=[exp.column(parent_hk_col)],
                order=exp.Order(
                    expressions=[exp.Ordered(this=exp.column(ldts_col), desc=True)]
                ),
            )
            ctes[latest_target_cte] = (
                exp.select(exp.column(parent_hk_col), exp.column(hash_diff_col))
                .from_(target_exp)
                .qualify(target_window.eq(1))
            )

        # ---------------------------------------------------------
        # 3. Consecutive-hashdiff dedup via LAG QUALIFY
        # ---------------------------------------------------------
        lag_window = exp.Window(
            this=exp.Lag(this=exp.column(hash_diff_col)),
            partition_by=[exp.column(parent_hk_col)],
            order=exp.Order(
                expressions=[exp.Ordered(this=exp.column(ldts_col))]
            ),
        )
        qualify_case = (
            exp.Case()
            .when(exp.column(hash_diff_col).eq(lag_window), exp.false())
            .else_(exp.true())
        )
        ctes["deduped_row_hashdiff"] = (
            exp.select(
                exp.column(parent_hk_col),
                exp.column(ldts_col),
                exp.column(hash_diff_col),
            )
            .from_("src_new")
            .qualify(qualify_case)
        )

        # ---------------------------------------------------------
        # 4. Re-join source to recover all columns for deduped rows
        # ---------------------------------------------------------
        src_alias = "sd"
        drh_alias = "drh"

        src_tbl = exp.alias_(
            exp.Table(this=exp.Identifier(this="src_new")),
            src_alias,
            table=True,
        )
        drh_tbl = exp.alias_(
            exp.Table(this=exp.Identifier(this="deduped_row_hashdiff")),
            drh_alias,
            table=True,
        )

        join_on = exp.and_(
            exp.column(parent_hk_col, table=src_alias).eq(
                exp.column(parent_hk_col, table=drh_alias)
            ),
            exp.column(ldts_col, table=src_alias).eq(
                exp.column(ldts_col, table=drh_alias)
            ),
            exp.column(hash_diff_col, table=src_alias).eq(
                exp.column(hash_diff_col, table=drh_alias)
            ),
        )

        all_cols = (
            [parent_hk_col, hash_diff_col]
            + list(src_payload)
            + list(extra_cols)
            + [ldts_col, rsrc_col]
        )
        deduped_select = [
            exp.column(col, table=src_alias).as_(col) for col in all_cols
        ]
        ctes["deduped_rows"] = (
            exp.select(*deduped_select)
            .from_(src_tbl)
            .join(drh_tbl, on=join_on, join_type="INNER")
        )

        # ---------------------------------------------------------
        # 5. records_to_insert — NOT EXISTS against latest target
        # ---------------------------------------------------------
        if self.is_incremental:
            not_exists_sub = (
                exp.select(exp.Literal.number(1))
                .from_(latest_target_cte)
                .where(
                    exp.and_(
                        exp.column(parent_hk_col, table=latest_target_cte).eq(
                            exp.column(parent_hk_col, table="deduped_rows")
                        ),
                        exp.column(hash_diff_col, table=latest_target_cte).eq(
                            exp.column(hash_diff_col, table="deduped_rows")
                        ),
                    )
                )
            )
            ctes["records_to_insert"] = (
                exp.select("*")
                .from_("deduped_rows")
                .where(exp.Not(this=exp.Exists(this=not_exists_sub)))
            )
        else:
            ctes["records_to_insert"] = exp.select("*").from_("deduped_rows")

        # ---------------------------------------------------------
        # 6. Final Select + Assemble CTEs
        # ---------------------------------------------------------
        final_query = exp.select("*").from_("records_to_insert")
        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)

        return final_query
