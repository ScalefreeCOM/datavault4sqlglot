from __future__ import annotations

from typing import List, Optional

from sqlglot import exp

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceBinding


class HubGenerator(BaseGenerator):
    """Generates SQL for a Data Vault Hub entity."""

    def __init__(
        self,
        target_table: str,
        sources: List[SourceBinding],
        hashkey: str,
        business_keys: List[str],
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        additional_columns: Optional[List[str]] = None,
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ):
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.sources = sources
        self.hashkey = hashkey
        self.business_keys = business_keys
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.additional_columns = additional_columns or []
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

        # Per-source bk_columns must match the canonical hub-level
        # business_keys positionally. Catch length mismatches at construction
        # time so we never emit a malformed UNION downstream.
        for idx, binding in enumerate(self.sources):
            if binding.bk_columns is not None and len(binding.bk_columns) != len(self.business_keys):
                raise ValueError(
                    f"HubGenerator: sources[{idx}].bk_columns has "
                    f"length {len(binding.bk_columns)}, but the hub has "
                    f"{len(self.business_keys)} business_keys."
                )

    def generate_sql(self) -> exp.Expression:
        hashkey_col = self.hashkey
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        boa = self.beginning_of_all_times

        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )

        ctes: dict = {}

        # ---------------------------------------------------------
        # 1. HWM CTE (per-source rsrc_static)
        # ---------------------------------------------------------
        hwm_cte_name = "max_ldts_per_rsrc_static_in_target"

        if self.is_incremental and not self.disable_hwm:
            hwm_query = self._build_rsrc_static_hwm_query(
                self.sources, target_exp, ldts_col, rsrc_col, self.end_of_all_times
            )
            if hwm_query is not None:
                ctes[hwm_cte_name] = hwm_query

        # ---------------------------------------------------------
        # 2. Per-source CTEs
        # ---------------------------------------------------------
        source_cte_names = []

        for idx, binding in enumerate(self.sources):
            src = binding.source
            src_table_exp = self._get_table_expression(
                src.table_name, src.schema_name, src.database
            )
            src_hk = binding.hash_key_col or hashkey_col
            src_ldts = src.load_date_col or ldts_col
            src_rsrc = src.record_source_col or rsrc_col
            statics = binding.rsrc_statics or []
            extra_cols = binding.additional_columns or self.additional_columns

            select_exprs = [exp.column(src_hk).as_(hashkey_col)]
            # Per-source business-key columns are aliased positionally to the
            # canonical hub-level names, so multi-source UNIONs line up by name
            # (not just by position) regardless of physical naming differences.
            src_bk_cols = binding.bk_columns or self.business_keys
            for src_col, target_col in zip(src_bk_cols, self.business_keys):
                col_expr = exp.column(src_col)
                if src_col != target_col:
                    col_expr = col_expr.as_(target_col)
                select_exprs.append(col_expr)
            for col in extra_cols:
                select_exprs.append(exp.column(col))
            select_exprs.append(exp.column(src_ldts).as_(ldts_col))
            select_exprs.append(exp.column(src_rsrc).as_(rsrc_col))

            src_query = exp.select(*select_exprs).from_(src_table_exp)

            if self.is_incremental and not self.disable_hwm:
                if statics and hwm_cte_name in ctes:
                    src_query = src_query.where(
                        self._build_rsrc_static_or_filter(
                            statics, src_ldts, src_rsrc, hwm_cte_name, boa
                        )
                    )
                elif not statics and len(self.sources) == 1:
                    subquery = (
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
                        exp.column(src_ldts) > exp.Paren(this=subquery)
                    )

            cte_name = f"src_new_{idx}"
            ctes[cte_name] = src_query
            source_cte_names.append(cte_name)

        # ---------------------------------------------------------
        # 3. Union all sources
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
        # 4. Deduplication — earliest occurrence per hash key
        # ---------------------------------------------------------
        window_expression = exp.Window(
            this=exp.RowNumber(),
            partition_by=[exp.column(hashkey_col)],
            order=exp.Order(expressions=[exp.Ordered(this=exp.column(ldts_col))]),
        )
        ctes["earliest_hk_over_all_sources"] = (
            exp.select("*").from_(last_cte).qualify(window_expression.eq(1))
        )
        last_cte = "earliest_hk_over_all_sources"

        # ---------------------------------------------------------
        # 5. Incremental — exclude existing hash keys
        # ---------------------------------------------------------
        if self.is_incremental:
            target_cte = "distinct_target_hashkeys"
            ctes[target_cte] = exp.select(hashkey_col).from_(target_exp)

            ctes["records_to_insert"] = (
                exp.select("*")
                .from_(last_cte)
                .where(
                    exp.column(hashkey_col)
                    .isin(exp.select(hashkey_col).from_(target_cte))
                    .not_()
                )
            )
            last_cte = "records_to_insert"

        # ---------------------------------------------------------
        # 6. Final SELECT + assemble CTEs
        # ---------------------------------------------------------
        final_query = exp.select("*").from_(last_cte)
        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)

        return final_query
