from __future__ import annotations

from typing import Optional

from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.config import config


class SatelliteV1Generator(BaseGenerator):
    """
    Generates SQL for a Data Vault Satellite (v1) end-dating view.

    Wraps an existing v0 satellite and adds a LEDTS column computed as
    LEAD(ldts) OVER (PARTITION BY parent_hash_key ORDER BY ldts), with
    the most recent record per key receiving end_of_all_times.

    Column selection uses SELECT * so no payload or hash_diff list is needed.

    Args:
        source_satellite: Table name of the underlying v0 satellite.
        parent_hash_key: Column name of the parent hub/link hash key.
        source_satellite_schema: Optional schema of the v0 satellite.
        source_satellite_database: Optional database of the v0 satellite.
        ledts_alias: Output column name for the load-end-date timestamp.
        end_of_all_times: Sentinel value for open-ended records.
        dialect: SQL dialect override.
    """

    def __init__(
        self,
        source_satellite: str,
        parent_hash_key: str,
        source_satellite_schema: Optional[str] = None,
        source_satellite_database: Optional[str] = None,
        ledts_alias: Optional[str] = None,
        end_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ):
        super().__init__(dialect=dialect)
        self.source_satellite = source_satellite
        self.source_satellite_schema = source_satellite_schema
        self.source_satellite_database = source_satellite_database
        self.parent_hash_key = parent_hash_key
        self.ledts_alias = ledts_alias or config.ledts_alias
        self.end_of_all_times = end_of_all_times or config.end_of_all_times

    def generate_sql(self) -> exp.Expression:
        """Generates SELECT *, <ledts_window> FROM source_satellite."""
        ldts_col = config.ldts_alias

        source_exp = self._get_table_expression(
            self.source_satellite,
            self.source_satellite_schema,
            self.source_satellite_database,
        )

        lead_window = exp.Window(
            this=exp.Lead(this=exp.column(ldts_col)),
            partition_by=[exp.column(self.parent_hash_key)],
            order=exp.Order(
                expressions=[exp.Ordered(this=exp.column(ldts_col))]
            ),
        )

        ledts_expr = exp.Coalesce(
            this=lead_window,
            expressions=[
                exp.Cast(
                    this=exp.Literal.string(self.end_of_all_times),
                    to=exp.DataType.build("TIMESTAMP"),
                )
            ],
        ).as_(self.ledts_alias)

        return exp.select(exp.Star(), ledts_expr).from_(source_exp)
