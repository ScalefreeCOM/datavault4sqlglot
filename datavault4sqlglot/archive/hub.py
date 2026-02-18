import sqlglot
from sqlglot import exp

class HubGenerator:
    @staticmethod
    def generate_sql(
        source_models,
        target_table,
        hashkey_col,
        ldts_col,
        rsrc_col,
        is_incremental=False,
        disable_hwm=False,
        end_of_all_times="9999-12-31"
    ):
        # ---------------------------------------------------------
        # 1. High Water Mark (HWM) Logik
        # ---------------------------------------------------------
        hwm_cte_name = "max_ldts_per_rsrc_static_in_target"
        ctes = {}
        
        union_selects = []
        has_rsrc_static_logic = False
    
        if is_incremental and not disable_hwm:
            for src in source_models:
                statics = src.get("rsrc_statics", [])
                if statics:
                    has_rsrc_static_logic = True
                    for static_val in statics:
                        q = (
                            exp.select(
                                exp.func("MAX", exp.column(ldts_col)).as_("max_ldts"),
                                exp.Literal.string(static_val).as_("rsrc_static")
                            )
                            .from_(target_table)
                            .where(exp.column(rsrc_col).like(static_val))
                            .where(f"{ldts_col} != '{end_of_all_times}'")
                        )
                        union_selects.append(q)
    
            if has_rsrc_static_logic and union_selects:
                if len(union_selects) > 1:
                    final_hwm_query = sqlglot.union(*union_selects, distinct=False)
                else:
                    final_hwm_query = union_selects[0]
                
                ctes[hwm_cte_name] = final_hwm_query
    
        # ---------------------------------------------------------
        # 2. Source Models verarbeiten
        # ---------------------------------------------------------
        source_cte_names = []
    
        for src in source_models:
            src_id = str(src["id"])
            src_name = src["name"]
            bk_columns = src["bk_columns"]
            statics = src.get("rsrc_statics", [])
            
            select_expressions = [
                exp.column(src.get("hk_column", hashkey_col)).as_(hashkey_col)
            ]
            
            for idx, bk in enumerate(bk_columns):
                select_expressions.append(exp.column(bk).as_(f"bk_{idx+1}"))
    
            select_expressions.append(exp.column(ldts_col))
            select_expressions.append(exp.column(rsrc_col))
    
            src_query = exp.select(*select_expressions).from_(src_name)
    
            if is_incremental and not disable_hwm:
                if statics and hwm_cte_name in ctes:
                    or_conditions = []
                    for static_val in statics:
                        subquery = (
                            exp.select("MAX(max_ldts)")
                            .from_(hwm_cte_name)
                            .where(f"rsrc_static = '{static_val}'")
                        )
                        
                        # Logik mit Python Operatoren (== und >)
                        cond = sqlglot.and_(
                            exp.column(rsrc_col).eq(static_val),
                            exp.column(ldts_col) > subquery  
                        )
                        
                        or_conditions.append(cond)
                    
                    if or_conditions:
                        src_query = src_query.where(sqlglot.or_(*or_conditions))
                
                elif not statics:
                     subquery = exp.select(f"MAX({ldts_col})").from_(target_table)
                     src_query = src_query.where(exp.column(ldts_col) > subquery)
    
            cte_name = f"src_new_{src_id}"
            ctes[cte_name] = src_query
            source_cte_names.append(cte_name)
    
        # ---------------------------------------------------------
        # 3. Union aller Sources
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
        # 4. Deduplizierung (Fix mit parse_one)
        # ---------------------------------------------------------
        dedup_query = exp.select("*").from_(last_cte)
        
        # Wir parsen den Window-Ausdruck. Das ist sicher und vermeidet API-Fehler.
        window_sql = f"ROW_NUMBER() OVER (PARTITION BY {hashkey_col} ORDER BY {ldts_col})"
        window_expression = sqlglot.parse_one(window_sql)
        
        dedup_query = dedup_query.qualify(exp.EQ(this=window_expression, expression=exp.Literal.number(1)))
        
        ctes["earliest_hk_over_all_sources"] = dedup_query
        last_cte = "earliest_hk_over_all_sources"
    
        # ---------------------------------------------------------
        # 5. Target Check
        # ---------------------------------------------------------
        final_query = exp.select("*").from_(last_cte)
    
        if is_incremental:
            target_check = exp.select(hashkey_col).from_(target_table)
            final_query = final_query.where(
                exp.column(hashkey_col).isin(query=target_check).not_()
            )
    
        # ---------------------------------------------------------
        # 6. Alles zusammenbauen
        # ---------------------------------------------------------
        for name, cte_expression in ctes.items():
            final_query = final_query.with_(name, as_=cte_expression)
    
        return final_query
