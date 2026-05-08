from __future__ import annotations

from typing import List, Optional

from sqlglot import exp

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceBinding


class LinkNHGenerator(BaseGenerator):
    """
    Generates SQL for a Non-Historized Link (NH Link).

    Like a regular Link but without history: only the **latest** record per
    ``driving_hash_key`` is kept. Intended for MERGE/upsert materialization.

    Args:
        target_table:       Target NH link table.
        sources:            Source bindings (each needs >= 2 foreign_hash_keys).
        link_hash_key:      The link's own hash key column.
        driving_hash_key:   Hash key to partition by for the ROW_NUMBER window
                            (the "owner" side). Defaults to ``link_hash_key``.
        is_incremental:     Whether to apply a global HWM filter before dedup.
        disable_hwm:        Skip the HWM filter even when incremental.
        additional_columns: Extra columns to carry through.
    """

    def __init__(
        self,
        target_table: str,
        sources: List[SourceBinding],
        link_hash_key: str,
        driving_hash_key: Optional[str] = None,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        additional_columns: Optional[List[str]] = None,
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.sources = sources
        self.link_hash_key = link_hash_key
        self.driving_hash_key = driving_hash_key or link_hash_key
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.additional_columns = additional_columns or []
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

    def generate_sql(self) -> exp.Expression:
        hashkey_col = self.link_hash_key
        driving_col = self.driving_hash_key
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        boa = self.beginning_of_all_times

        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )

        ctes: dict = {}

        # ------------------------------------------------------------------
        # 1. Source CTEs — one per binding, with optional global HWM filter
        # ------------------------------------------------------------------
        source_cte_names: list[str] = []

        for idx, binding in enumerate(self.sources):
            src = binding.source
            src_table_exp = self._get_table_expression(
                src.table_name, src.schema_name, src.database
            )
            src_lhk = binding.hash_key_col or hashkey_col
            src_ldts = src.load_date_col or ldts_col
            src_rsrc = src.record_source_col or rsrc_col
            foreign_hks = binding.foreign_hash_keys or []
            extra_cols = binding.additional_columns or self.additional_columns

            if len(foreign_hks) < 2:
                raise ValueError(
                    f"Source '{src.table_name}' must define at least 2 foreign_hash_keys "
                    f"for a Link entity, got {len(foreign_hks)}."
                )

            select_exprs = (
                [exp.column(src_lhk).as_(hashkey_col)]
                + [exp.column(fhk) for fhk in foreign_hks]
                + [exp.column(c) for c in extra_cols]
                + [exp.column(src_ldts).as_(ldts_col), exp.column(src_rsrc).as_(rsrc_col)]
            )
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
                        exp.column(ldts_col).neq(exp.Literal.string(self.end_of_all_times))
                    )
                )
                src_query = src_query.where(
                    exp.column(src_ldts) > exp.Paren(this=hwm_sub)
                )

            cte_name = f"src_new_{idx}"
            ctes[cte_name] = src_query
            source_cte_names.append(cte_name)

        # ------------------------------------------------------------------
        # 2. Union all sources
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # 3. Deduplication — latest record per driving_hash_key (ROW_NUMBER DESC)
        # ------------------------------------------------------------------
        window_expression = exp.Window(
            this=exp.RowNumber(),
            partition_by=[exp.column(driving_col)],
            order=exp.Order(
                expressions=[exp.Ordered(this=exp.column(ldts_col), desc=True)]
            ),
        )
        ctes["latest_records"] = (
            exp.select("*").from_(last_cte).qualify(window_expression.eq(1))
        )

        # ------------------------------------------------------------------
        # 4. Final SELECT + assemble CTEs
        # ------------------------------------------------------------------
        final_query = exp.select("*").from_("latest_records")
        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)

        return final_query
