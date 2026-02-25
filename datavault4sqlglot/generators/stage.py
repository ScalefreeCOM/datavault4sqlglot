from __future__ import annotations

from typing import Optional

from sqlglot import exp, parse_one

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceModel


class StageGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Stage (Hash) Layer.
    """

    def __init__(
        self,
        source_model: SourceModel,
        target_table: str = "stage_view",
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database)
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

        # 2. Main Select (Read from CTE if exists)
        if self.source_model.derived_columns:
            from_table = exp.Table(
                this=exp.Identifier(this=derived_cte_name, quoted=True)
            )
        else:
            src = self.source_model
            from_table = self._get_table_expression(
                src.table_name, src.schema_name, src.database
            )

        # Build Projection
        projection: list[exp.Expression] = (
            [exp.Star()] if self.source_model.include_source_columns else []
        )

        # Hashes
        if self.source_model.hashed_columns:
            for alias, cols in self.source_model.hashed_columns.items():
                hash_expr = self._build_hash_expression(cols)
                projection.append(
                    hash_expr.as_(exp.Identifier(this=alias, quoted=True))
                )

        main_query = exp.select(*projection).from_(from_table)

        if self.source_model.derived_columns:
            main_query = main_query.with_(derived_cte_name, as_=derived_with)

        return main_query

    def _build_derived_cte(self, cte_name: str) -> exp.Expression:
        """Build the CTE for derived columns."""
        src = self.source_model
        src_table = self._get_table_expression(
            src.table_name, src.schema_name, src.database
        )

        selection: list[exp.Expression] = [exp.Star()]

        if self.source_model.derived_columns:
            for alias, expr_str in self.source_model.derived_columns.items():
                expression = parse_one(expr_str)
                selection.append(
                    expression.as_(exp.Identifier(this=alias, quoted=True))
                )

        return exp.select(*selection).from_(src_table)
