from typing import List, Dict, Optional

import sqlglot
from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceTable


class LinkGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Link entity.
    """

    def __init__(
        self, 
        target_table: str, 
        source_models: List[SourceTable], 
        target_schema: Optional[str] = None, 
        target_database: Optional[str] = None,
        link_hash_key: str = "hash_key",
        is_incremental: bool = False,
        disable_hwm: bool = False,
        end_of_all_times: str = "9999-12-31"
    ):
        super().__init__(target_table, target_schema, target_database)
        self.source_models = source_models
        self.link_hash_key = link_hash_key
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.end_of_all_times = end_of_all_times

    def generate_sql(self) -> exp.Expression:
        # Configuration
        hashkey_col = self.link_hash_key
        ldts_col = "load_date"
        rsrc_col = "record_source"
        
        # Helper for target table
        target_exp = self._get_table_expression(self.target_table, self.target_schema, self.target_database)

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
                            .from_(target_exp)
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
            src_id = str(idx)
            src_table_exp = self._get_table_expression(src.table_name, src.schema_name, src.database)
            
            # Use link_hash_key from source if provided, otherwise fallback to generator's default
            src_link_hk = src.link_hash_key if src.link_hash_key else hashkey_col
            # Use foreign_hash_keys from source
            foreign_hks = src.foreign_hash_keys or []
            
            statics = src.rsrc_statics or []

            # 2.1 Build Source Selection
            select_expressions = [
                exp.column(src_link_hk).as_(hashkey_col)
            ]

            # Foreign Hash Keys
            for fhk in foreign_hks:
                select_expressions.append(exp.column(fhk))

            select_expressions.append(exp.column(src.load_date_col).as_(ldts_col))
            select_expressions.append(exp.column(src.record_source_col).as_(rsrc_col))

            src_query = exp.select(*select_expressions).from_(src_table_exp)

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
                     subquery = exp.select(f"MAX({ldts_col})").from_(target_exp)
                     src_query = src_query.where(exp.column(ldts_col) > subquery)

            cte_name = f"src_new_{src_id}"
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
        
        window_sql = f"ROW_NUMBER() OVER (PARTITION BY {hashkey_col} ORDER BY {ldts_col})"
        window_expression = sqlglot.parse_one(window_sql)
        
        dedup_query = dedup_query.qualify(exp.EQ(this=window_expression, expression=exp.Literal.number(1)))
        
        ctes["earliest_hk_over_all_sources"] = dedup_query
        last_cte = "earliest_hk_over_all_sources"

        # ---------------------------------------------------------
        # 5. Incremental Logic: Target Check
        # ---------------------------------------------------------
        target_cte_name = "distinct_target_hashkeys"
        target_select = exp.select(hashkey_col).from_(target_exp)
        ctes[target_cte_name] = target_select
        
        insert_cte_name = "records_to_insert"
        insert_query = exp.select("*").from_(last_cte).where(
            exp.column(hashkey_col).isin(query=exp.select("*").from_(target_cte_name)).not_()
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
