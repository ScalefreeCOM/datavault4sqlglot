from __future__ import annotations

from typing import List, Optional

from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceBinding
from datavault4sqlglot.config import config


class NonHistorizedLinkGenerator(BaseGenerator):
    """
    Generates SQL for a Non-Historized Link (nh_link).

    Like a standard Link but includes payload columns on the relationship record
    and supports a union_strategy ('UNION ALL' or 'UNION') for multi-source loads.
    Matches the datavault4dbt nh_link pattern.
    """

    def __init__(
        self,
        target_table: str,
        sources: list[SourceBinding],
        link_hash_key: str,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        source_is_single_batch: bool = False,
        additional_columns: Optional[List[str]] = None,
        union_strategy: str = "UNION ALL",
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.sources = sources
        self.link_hash_key = link_hash_key
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.source_is_single_batch = source_is_single_batch
        self.additional_columns = additional_columns or []
        self.union_strategy = union_strategy.upper()
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

    def generate_sql(self) -> exp.Expression:
        hashkey_col = self.link_hash_key
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        boa = self.beginning_of_all_times

        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )

        ctes: dict = {}

        # ---------------------------------------------------------
        # 1. HWM Logic (per-source rsrc_static)
        # ---------------------------------------------------------
        hwm_cte_name = "max_ldts_per_rsrc_static_in_target"

        if self.is_incremental and not self.disable_hwm:
            hwm_query = self._build_rsrc_static_hwm_query(
                self.sources, target_exp, ldts_col, rsrc_col, self.end_of_all_times
            )
            if hwm_query is not None:
                ctes[hwm_cte_name] = hwm_query

        # ---------------------------------------------------------
        # 2. Process Sources
        # ---------------------------------------------------------
        source_cte_names = []

        for idx, binding in enumerate(self.sources):
            src = binding.source
            src_table_exp = self._get_table_expression(
                src.table_name, src.schema_name, src.database
            )
            src_link_hk = binding.hash_key_col or hashkey_col
            src_ldts = src.load_date_col or ldts_col
            src_rsrc = src.record_source_col or rsrc_col
            foreign_hks = binding.foreign_hash_keys or []
            payload = binding.payload or []
            extra_cols = binding.additional_columns or self.additional_columns
            statics = binding.rsrc_statics or []

            select_exprs = [
                exp.column(src_link_hk).as_(hashkey_col),
                *[exp.column(fhk) for fhk in foreign_hks],
                *[exp.column(p) for p in payload],
                *[exp.column(col) for col in extra_cols],
                exp.column(src_ldts).as_(ldts_col),
                exp.column(src_rsrc).as_(rsrc_col),
            ]
            src_query = exp.select(*select_exprs).from_(src_table_exp)

            if self.is_incremental and not self.disable_hwm:
                if statics and hwm_cte_name in ctes:
                    src_query = src_query.where(
                        self._build_rsrc_static_or_filter(
                            statics, src_ldts, src_rsrc, hwm_cte_name, boa
                        )
                    )
                elif not statics and len(self.sources) == 1:
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

            cte_name = f"src_new_{idx}"
            ctes[cte_name] = src_query
            source_cte_names.append(cte_name)

        # ---------------------------------------------------------
        # 3. Union Sources (configurable UNION ALL vs UNION DISTINCT)
        # ---------------------------------------------------------
        distinct = self.union_strategy == "UNION"
        if len(source_cte_names) > 1:
            union_query = exp.select("*").from_(source_cte_names[0])
            for name in source_cte_names[1:]:
                union_query = union_query.union(
                    exp.select("*").from_(name), distinct=distinct
                )
            ctes["source_new_union"] = union_query
            last_cte = "source_new_union"
        else:
            last_cte = source_cte_names[0]

        # ---------------------------------------------------------
        # 4. Deduplication (skip when source_is_single_batch)
        # ---------------------------------------------------------
        if not self.source_is_single_batch:
            dedup_window = exp.Window(
                this=exp.RowNumber(),
                partition_by=[exp.column(hashkey_col)],
                order=exp.Order(
                    expressions=[exp.Ordered(this=exp.column(ldts_col))]
                ),
            )
            dedup_query = exp.select("*").from_(last_cte).qualify(dedup_window.eq(1))
            ctes["earliest_hk_over_all_sources"] = dedup_query
            last_cte = "earliest_hk_over_all_sources"

        # ---------------------------------------------------------
        # 5. Incremental — filter to new link hash keys only
        # ---------------------------------------------------------
        if self.is_incremental:
            target_cte = "distinct_target_hashkeys"
            ctes[target_cte] = exp.select(hashkey_col).from_(target_exp)

            insert_query = exp.select("*").from_(last_cte).where(
                exp.column(hashkey_col)
                .isin(exp.select(hashkey_col).from_(target_cte))
                .not_()
            )
            ctes["records_to_insert"] = insert_query
            last_cte = "records_to_insert"

        # ---------------------------------------------------------
        # 6. Final Select + Assemble CTEs
        # ---------------------------------------------------------
        final_query = exp.select("*").from_(last_cte)
        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)

        return final_query
