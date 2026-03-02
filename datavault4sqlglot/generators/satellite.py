from typing import List, Dict, Optional

import sqlglot
from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceModel
from datavault4sqlglot.config import config


class SatelliteGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Satellite entity.
    """

    def __init__(
        self, 
        target_table: str, 
        source_models: List[SourceModel], 
        parent_hash_key: str,
        hash_diff: str,
        target_schema: Optional[str] = None, 
        target_database: Optional[str] = None,
        payload: List[str] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        end_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None
    ):

        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.source_models = source_models
        self.parent_hash_key = parent_hash_key
        self.hash_diff = hash_diff
        self.payload = payload or []
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.end_of_all_times = end_of_all_times or config.end_of_all_times


    def generate_sql(self) -> exp.Expression:
        # Configuration
        parent_hk_col = self.parent_hash_key
        hash_diff_col = self.hash_diff
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias

        
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
                                exp.Max(this=exp.column(ldts_col)).as_("max_ldts"),
                                exp.Literal.string(static_val).as_("rsrc_static")
                            )
                            .from_(target_exp)
                            .where(exp.column(rsrc_col).like(exp.Literal.string(static_val)))
                            .where(exp.column(ldts_col).neq(exp.Literal.string(self.end_of_all_times)))
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
            
            src_parent_hk = src.hash_key_col if src.hash_key_col else parent_hk_col
            src_hash_diff = src.hash_diff if src.hash_diff else hash_diff_col
            src_payload = src.payload if src.payload else self.payload
            src_ldts = src.load_date_col or ldts_col
            src_rsrc = src.record_source_col or rsrc_col
            
            statics = src.rsrc_statics or []

            # 2.1 Build Source Selection
            select_expressions = [
                exp.column(src_parent_hk).as_(parent_hk_col),
                exp.column(src_hash_diff).as_(hash_diff_col)
            ]

            # Payload
            for p in src_payload:
                select_expressions.append(exp.column(p))

            select_expressions.append(exp.column(src_ldts).as_(ldts_col))
            select_expressions.append(exp.column(src_rsrc).as_(rsrc_col))

            src_query = exp.select(*select_expressions).from_(src_table_exp)

            # 2.2 Incremental Logic (Source Filter)
            if self.is_incremental and not self.disable_hwm:
                 if statics and hwm_cte_name in ctes:
                    or_conditions = []
                    for static_val in statics:
                         subquery = (
                             exp.select(exp.Max(this=exp.column("max_ldts")))
                             .from_(hwm_cte_name)
                             .where(exp.column("rsrc_static").eq(exp.Literal.string(static_val)))
                         )
                         cond = exp.and_(
                             exp.column(src_rsrc).eq(exp.Literal.string(static_val)),
                             exp.column(src_ldts) > exp.Paren(this=subquery)
                         )
                         or_conditions.append(cond)
                    
                    if or_conditions:
                        src_query = src_query.where(exp.or_(*or_conditions))
                 
                 elif not statics:
                     # Generic HWM
                     subquery = exp.select(exp.Max(this=exp.column(ldts_col))).from_(target_exp)
                     src_query = src_query.where(exp.column(src_ldts) > exp.Paren(this=subquery))

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
        
        # ROW_NUMBER() OVER (PARTITION BY hk, hd ORDER BY ldts)
        window_expression = exp.Window(
            this=exp.RowNumber(),
            partition_by=[exp.column(parent_hk_col), exp.column(hash_diff_col)],
            order=exp.Order(expressions=[exp.Ordered(this=exp.column(ldts_col))])
        )
        
        dedup_query = dedup_query.qualify(window_expression.eq(1))
        
        ctes["earliest_hk_over_all_sources"] = dedup_query
        last_cte = "earliest_hk_over_all_sources"

        # ---------------------------------------------------------
        # 5. Incremental Logic: Change Detection
        # ---------------------------------------------------------
        if self.is_incremental:
            # 5.1 CTE: latest_records_in_target
            latest_target_cte = "latest_records_in_target"
            
            # Use native Window expression
            target_window = exp.Window(
                this=exp.RowNumber(),
                partition_by=[exp.column(parent_hk_col)],
                order=exp.Order(expressions=[exp.Ordered(this=exp.column(ldts_col), desc=True)])
            )
            
            target_query = (
                exp.select(parent_hk_col, hash_diff_col)
                .from_(target_exp)
                .qualify(target_window.eq(1))
            )
            ctes[latest_target_cte] = target_query

            # 5.2 CTE: records_to_insert
            insert_cte_name = "records_to_insert"
            
            # Join new records with latest target records
            src_alias = "src"
            tgt_alias = "tgt"
            
            insert_query = (
                exp.select(f"{src_alias}.*")
                .from_(exp.alias_(exp.column(last_cte), src_alias))
                .join(exp.alias_(exp.column(latest_target_cte), tgt_alias), 
                      on=exp.column(parent_hk_col, table=src_alias).eq(exp.column(parent_hk_col, table=tgt_alias)),
                      join_type="LEFT")
                .where(
                    exp.or_(
                        exp.column(parent_hk_col, table=tgt_alias).is_(exp.null()),
                        exp.column(hash_diff_col, table=src_alias).neq(exp.column(hash_diff_col, table=tgt_alias))
                    )
                )
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
