from typing import List, Dict

import sqlglot
from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata.source import SourceTable


class HubGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Hub entity.
    """

    def __init__(
        self, 
        target_table_name: str, 
        source_models: List[SourceTable], 
        is_incremental: bool = False,
        disable_hwm: bool = False,
        end_of_all_times: str = "9999-12-31"
    ):
        super().__init__(target_table_name)
        self.source_models = source_models
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.end_of_all_times = end_of_all_times

    def generate_sql(self) -> exp.Expression:
        # Configuration
        # These are target names, but could be configurable via init if needed
        hashkey_col = "hash_key"
        ldts_col = "load_date"
        rsrc_col = "record_source"
        
        # ---------------------------------------------------------
        # 1. HWM Logic
        # ---------------------------------------------------------
        hwm_cte_name = "max_ldts_per_rsrc_static_in_target"
        ctes = {}
        union_selects = []
        has_rsrc_static_logic = False

        if self.is_incremental and not self.disable_hwm:
            for src in self.source_models:
                statics = src.rsrc_statics or []
                if statics:
                    has_rsrc_static_logic = True
                    for static_val in statics:
                        q = (
                            exp.select(
                                exp.func("MAX", exp.column(ldts_col)).as_("max_ldts"),
                                exp.Literal.string(static_val).as_("rsrc_static")
                            )
                            .from_(self.target_table_name)
                            .where(exp.column(rsrc_col).like(static_val))
                            .where(f"{ldts_col} != '{self.end_of_all_times}'")
                        )
                        union_selects.append(q)

            if has_rsrc_static_logic and union_selects:
                if len(union_selects) > 1:
                    final_hwm_query = sqlglot.union(*union_selects, distinct=False)
                else:
                    final_hwm_query = union_selects[0]
                ctes[hwm_cte_name] = final_hwm_query

        # ---------------------------------------------------------
        # 2. Process Sources
        # ---------------------------------------------------------
        source_cte_names = []
        
        for idx, src in enumerate(self.source_models):
            src_id = str(idx) # Use index for unique source naming
            src_name = src.name
            bk_columns = src.business_keys
            statics = src.rsrc_statics or []
            
            # Determine source HK column name (default to 'hash_key' if not set)
            src_hk = src.hash_key_col if src.hash_key_col else hashkey_col

            # 2.1 Build Source Selection
            select_expressions = [
                exp.column(src_hk).as_(hashkey_col)
            ]

            # Business Keys
            for bk in bk_columns:
                select_expressions.append(exp.column(bk))

            select_expressions.append(exp.column(src.load_date_col).as_(ldts_col))
            select_expressions.append(exp.column(src.record_source_col).as_(rsrc_col))

            src_query = exp.select(*select_expressions).from_(src_name)

            # 2.2 Incremental Logic
            if self.is_incremental and not self.disable_hwm:
                 if statics and hwm_cte_name in ctes:
                    or_conditions = []
                    for static_val in statics:
                         subquery = (
                             exp.select("MAX(max_ldts)")
                             .from_(hwm_cte_name)
                             .where(f"rsrc_static = '{static_val}'")
                         )
                         cond = sqlglot.and_(
                             exp.column(rsrc_col).eq(static_val),
                             exp.column(ldts_col) > subquery
                         )
                         or_conditions.append(cond)
                    
                    if or_conditions:
                        src_query = src_query.where(sqlglot.or_(*or_conditions))
                 
                 elif not statics:
                     # Generic HWM
                     subquery = exp.select(f"MAX({ldts_col})").from_(self.target_table_name)
                     src_query = src_query.where(exp.column(ldts_col) > subquery)

            cte_name = f"src_new_{src_id}"
            ctes[cte_name] = src_query
            source_cte_names.append(cte_name)

        # ---------------------------------------------------------
        # 3. Union All Sources
        # ---------------------------------------------------------
        if len(source_cte_names) > 1:
            # We select from the first source and union the rest
            union_query = exp.select("*").from_(source_cte_names[0])
            for name in source_cte_names[1:]:
                # Use query.union(other) which returns a Union expression
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
        # Select from the last CTE name (string)
        dedup_query = exp.select("*").from_(last_cte)
        
        # ROW_NUMBER() OVER (PARTITION BY hk ORDER BY ldts)
        window_sql = f"ROW_NUMBER() OVER (PARTITION BY {hashkey_col} ORDER BY {ldts_col})"
        window_expression = sqlglot.parse_one(window_sql)
        
        # Use qualify with exp.EQ - this is exactly what's in the original hub.py
        dedup_query = dedup_query.qualify(exp.EQ(this=window_expression, expression=exp.Literal.number(1)))
        
        ctes["earliest_hk_over_all_sources"] = dedup_query
        last_cte = "earliest_hk_over_all_sources"

        # ---------------------------------------------------------
        # 5. Target Check
        # ---------------------------------------------------------
        final_query = exp.select("*").from_(last_cte)

        if self.is_incremental:
            target_check = exp.select(hashkey_col).from_(self.target_table_name)
            final_query = final_query.where(
                exp.column(hashkey_col).isin(query=target_check).not_()
            )

        # ---------------------------------------------------------
        # 6. Assemble CTEs
        # ---------------------------------------------------------
        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)
            
        return final_query
