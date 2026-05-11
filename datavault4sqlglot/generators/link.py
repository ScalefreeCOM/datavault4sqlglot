from typing import List, Optional

from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceBinding
from datavault4sqlglot.config import config


class LinkGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Link entity.
    """

    def __init__(
        self,
        target_table: str,
        sources: List[SourceBinding],
        link_hash_key: str,
        foreign_hash_keys: List[str],
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        additional_columns: Optional[List[str]] = None,
        dialect: Optional[str] = None
    ):

        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.sources = sources
        self.link_hash_key = link_hash_key
        self.foreign_hash_keys = foreign_hash_keys
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.additional_columns = additional_columns or []

        # By DV2 definition a Link relates two or more business entities — fail
        # at construction so a malformed UNION never reaches downstream code.
        if len(self.foreign_hash_keys) < 2:
            raise ValueError(
                f"LinkGenerator must declare at least 2 foreign_hash_keys, "
                f"got {len(self.foreign_hash_keys)}."
            )

        # Per-source fk_columns must match the canonical foreign_hash_keys
        # positionally. Catch length mismatches at construction time so we
        # never emit a malformed UNION downstream.
        for idx, binding in enumerate(self.sources):
            if binding.fk_columns is not None and len(binding.fk_columns) != len(self.foreign_hash_keys):
                raise ValueError(
                    f"LinkGenerator: sources[{idx}].fk_columns has "
                    f"length {len(binding.fk_columns)}, but the link has "
                    f"{len(self.foreign_hash_keys)} foreign_hash_keys."
                )


    def generate_sql(self) -> exp.Expression:
        # Configuration
        hashkey_col = self.link_hash_key
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        beginning_of_all_times = config.beginning_of_all_times
        end_of_all_times = config.end_of_all_times

        # Helper for target table
        target_exp = self._get_table_expression(self.target_table, self.target_schema, self.target_database)

        # ---------------------------------------------------------
        # 1. HWM Logic
        # ---------------------------------------------------------
        hwm_cte_name = "max_ldts_per_rsrc_static_in_target"
        ctes = {}

        if self.is_incremental and not self.disable_hwm:
            hwm_query = self._build_rsrc_static_hwm_query(
                self.sources, target_exp, ldts_col, rsrc_col, end_of_all_times
            )
            if hwm_query is not None:
                ctes[hwm_cte_name] = hwm_query

        # ---------------------------------------------------------
        # 2. Process Sources
        # ---------------------------------------------------------
        source_cte_names = []

        for idx, binding in enumerate(self.sources):
            src = binding.source
            src_table_exp = self._get_table_expression(src.table_name, src.schema_name, src.database)

            src_link_hk = binding.hash_key_col or hashkey_col
            src_ldts = src.load_date_col or ldts_col
            src_rsrc = src.record_source_col or rsrc_col
            extra_cols = binding.additional_columns or self.additional_columns
            statics = binding.rsrc_statics or []

            select_expressions: list[exp.Expression] = [
                exp.column(src_link_hk).as_(hashkey_col),
            ]
            # Per-source foreign-hash-key columns are aliased positionally to
            # the canonical link-level names, so multi-source UNIONs line up by
            # name (not just by position) regardless of physical naming
            # differences across sources.
            src_fk_cols = binding.fk_columns or self.foreign_hash_keys
            for src_col, target_col in zip(src_fk_cols, self.foreign_hash_keys):
                col_expr = exp.column(src_col)
                if src_col != target_col:
                    col_expr = col_expr.as_(target_col)
                select_expressions.append(col_expr)
            for col in extra_cols:
                select_expressions.append(exp.column(col))
            select_expressions.append(exp.column(src_ldts).as_(ldts_col))
            select_expressions.append(exp.column(src_rsrc).as_(rsrc_col))

            src_query = exp.select(*select_expressions).from_(src_table_exp)

            # 2.2 Incremental Logic (Source Filter)
            if self.is_incremental and not self.disable_hwm:
                if statics and hwm_cte_name in ctes:
                    src_query = src_query.where(
                        self._build_rsrc_static_or_filter(
                            statics, src_ldts, src_rsrc, hwm_cte_name, beginning_of_all_times
                        )
                    )
                elif not statics and len(self.sources) == 1:
                    subquery = (
                        exp.select(
                            exp.Coalesce(
                                this=exp.Max(this=exp.column(ldts_col)),
                                expressions=[exp.Literal.string(beginning_of_all_times)],
                            )
                        )
                        .from_(target_exp)
                        .where(exp.column(ldts_col).neq(exp.Literal.string(end_of_all_times)))
                    )
                    src_query = src_query.where(exp.column(src_ldts) > exp.Paren(this=subquery))

            cte_name = f"src_new_{idx}"
            ctes[cte_name] = src_query
            source_cte_names.append(cte_name)

        # ---------------------------------------------------------
        # 3. Union All Sources
        # ---------------------------------------------------------
        if len(source_cte_names) > 1:
            union_query = exp.select("*").from_(source_cte_names[0])
            for name in source_cte_names[1:]:
                union_query = union_query.union(
                    exp.select("*").from_(name),
                    distinct=False
                )
            ctes["source_new_union"] = union_query
            last_cte = "source_new_union"
        else:
            last_cte = source_cte_names[0]

        # ---------------------------------------------------------
        # 4. Deduplication
        # ---------------------------------------------------------
        dedup_query = exp.select("*").from_(last_cte)
        
        # ROW_NUMBER() OVER (PARTITION BY hk ORDER BY ldts)
        window_expression = exp.Window(
            this=exp.RowNumber(),
            partition_by=[exp.column(hashkey_col)],
            order=exp.Order(expressions=[exp.Ordered(this=exp.column(ldts_col))])
        )
        
        dedup_query = dedup_query.qualify(window_expression.eq(1))
        
        ctes["earliest_hk_over_all_sources"] = dedup_query
        last_cte = "earliest_hk_over_all_sources"

        # ---------------------------------------------------------
        # 5. Incremental Logic: Target Check
        # ---------------------------------------------------------
        if self.is_incremental:
            target_cte_name = "distinct_target_hashkeys"
            target_select = exp.select(hashkey_col).from_(target_exp)
            ctes[target_cte_name] = target_select
            
            insert_cte_name = "records_to_insert"
            insert_query = exp.select("*").from_(last_cte).where(
                exp.column(hashkey_col).isin(exp.select(hashkey_col).from_(target_cte_name)).not_()
            )
            ctes[insert_cte_name] = insert_query
            last_cte = insert_cte_name

        # ---------------------------------------------------------
        # 6. Final Select
        # ---------------------------------------------------------
        final_query = exp.select("*").from_(last_cte)

        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)
            
        return final_query
