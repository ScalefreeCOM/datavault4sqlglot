from sqlglot import exp, parse_one

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata.stage import StageSource


class StageGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Stage (Hash) Layer.
    """

    def __init__(self, source_model: StageSource):
        # Target table name is not strictly required for Stage generation (usually a view or CTE), 
        # but BaseGenerator expects it. We can pass a dummy or change Base. 
        # For now, we'll pass the source name as a placeholder or make it optional in Base.
        # Actually, Stage is often a View, so 'target_table' could be the view name.
        # But StageSource doesn't have a target name. 
        # Let's pass "stage_view" for now.
        super().__init__("stage_view") 
        self.source_model = source_model

    def generate_sql(self) -> exp.Expression:
        """
        Generates the SQL for the Stage layer:
        1. Derived columns (CTE)
        2. Hashed columns
        3. Metadata columns (Load Date, Record Source)
        """
        # 1. Derived Columns (CTE)
        derived_cte_name = "derived_columns_cte"
        derived_with = self._build_derived_cte(derived_cte_name)
        
        # 2. Main Select (Read from CTE)
        # If we have derived columns, we select from the CTE. 
        # If not, we could select from source. But for consistency, let's strictly follow logic.
        
        from_table = derived_cte_name if self.source_model.derived_columns else self.source_model.source_model
        if isinstance(from_table, str):
            from_table = exp.Table(this=from_table)
        elif hasattr(from_table, "name"): # Handle SourceTable object
            from_table = exp.Table(this=from_table.name)

        # Build Projection
        projection = [exp.Star()] if self.source_model.include_source_columns else []
        
        # Hashes
        if self.source_model.hashed_columns:
            for alias, cols in self.source_model.hashed_columns.items():
                # Uses BaseGenerator._build_hash_expression logic now
                hash_expr = self._build_hash_expression(cols)
                projection.append(hash_expr.as_(alias))

        main_query = exp.select(*projection).from_(from_table)
        
        if self.source_model.derived_columns:
            main_query = main_query.with_(derived_cte_name, as_=derived_with)

        return main_query

    def _build_derived_cte(self, cte_name: str) -> exp.Expression:
        src = self.source_model.source_model
        src_name = src.name if hasattr(src, "name") else src 
        
        selection = [exp.Star()]
        
        if self.source_model.derived_columns:
            for alias, expr_str in self.source_model.derived_columns.items():
                # Parse the raw SQL expression string
                expression = parse_one(expr_str)
                selection.append(expression.as_(alias))
        
        return exp.select(*selection).from_(src_name)
