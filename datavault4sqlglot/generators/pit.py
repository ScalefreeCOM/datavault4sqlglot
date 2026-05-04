from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field
from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.config import config


class PitSatConfig(BaseModel):
    """Configuration for a satellite referenced inside a PIT table."""

    name: str = Field(..., description="Satellite CTE/table name (used as alias in JOIN).")
    table_name: str = Field(..., description="Physical satellite table name.")
    hashkey: str = Field(..., description="Hash key column in the satellite.")
    ldts: Optional[str] = Field(default=None, description="Load-date column. Defaults to global ldts_alias.")
    ledts: Optional[str] = Field(default=None, description="Load-end-date column. If absent, computed via LEAD.")
    schema_name: Optional[str] = Field(default=None)
    database: Optional[str] = Field(default=None)


class PITGenerator(BaseGenerator):
    """
    Generates SQL for a Point-in-Time (PIT) table.

    Cross-joins distinct hash keys from the tracked hub/link entity with
    snapshot dates, then LEFT JOINs each satellite to find the valid record
    at each snapshot point. Matches the core datavault4dbt pit Snowflake pattern.

    Args:
        tracked_entity:    Hub/link table providing distinct hash keys.
        hashkey:           Hash key column shared by hub and all satellites.
        sat_configs:       List of PitSatConfig — one per satellite.
        snapshot_relation: Table containing snapshot date-time stamps.
        sdts:              Snapshot date column name in snapshot_relation.
        dimension_key:     Column name for the computed PIT surrogate key.
        refer_to_ghost_records: If True, COALESCE satellite hk/ldts to ghost values.
        is_incremental:    If True, filter out already-existing dimension keys.
        end_of_all_times:  End-of-all-times sentinel.
        beginning_of_all_times: Beginning-of-all-times sentinel.
    """

    def __init__(
        self,
        target_table: str,
        tracked_entity: str,
        hashkey: str,
        sat_configs: List[PitSatConfig],
        snapshot_relation: str,
        sdts: str,
        dimension_key: str,
        tracked_entity_schema: Optional[str] = None,
        tracked_entity_database: Optional[str] = None,
        snapshot_schema: Optional[str] = None,
        snapshot_database: Optional[str] = None,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        ledts_alias: Optional[str] = None,
        refer_to_ghost_records: bool = True,
        is_incremental: bool = False,
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.tracked_entity = tracked_entity
        self.tracked_entity_schema = tracked_entity_schema
        self.tracked_entity_database = tracked_entity_database
        self.hashkey = hashkey
        self.sat_configs = sat_configs
        self.snapshot_relation = snapshot_relation
        self.snapshot_schema = snapshot_schema
        self.snapshot_database = snapshot_database
        self.sdts = sdts
        self.dimension_key = dimension_key
        self.ledts_alias = ledts_alias or config.ledts_alias
        self.refer_to_ghost_records = refer_to_ghost_records
        self.is_incremental = is_incremental
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

    def generate_sql(self) -> exp.Expression:
        hk_col = self.hashkey
        sdts_col = self.sdts
        dim_key_col = self.dimension_key
        ldts_col = config.ldts_alias
        ledts_col = self.ledts_alias
        eoa = self.end_of_all_times
        boa = self.beginning_of_all_times

        tracked_exp = self._get_table_expression(
            self.tracked_entity, self.tracked_entity_schema, self.tracked_entity_database
        )
        snapshot_exp = self._get_table_expression(
            self.snapshot_relation, self.snapshot_schema, self.snapshot_database
        )
        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )

        ctes: dict = {}

        # ---------------------------------------------------------
        # 1. Incremental: existing dimension keys to exclude
        # ---------------------------------------------------------
        if self.is_incremental:
            ctes["existing_dimension_keys"] = (
                exp.select(exp.column(dim_key_col)).from_(target_exp)
            )

        # ---------------------------------------------------------
        # 2. pit_records — FULL OUTER JOIN hub × snapshots, LEFT JOIN sats
        # ---------------------------------------------------------
        te_alias = "te"
        snap_alias = "snap"

        te_tbl = exp.alias_(tracked_exp, te_alias, table=True)
        snap_tbl = exp.alias_(snapshot_exp, snap_alias, table=True)

        # Dimension key: hash of (hk_col, sdts) — columns are unambiguous in scope
        dim_key_expr = self._build_hash_expression(
            columns=[hk_col, sdts_col],
            is_hashdiff=False,
        ).as_(exp.Identifier(this=dim_key_col, quoted=True))

        pit_cols: list[exp.Expression] = [
            dim_key_expr,
            exp.column(hk_col, table=te_alias).as_(hk_col),
            exp.column(sdts_col, table=snap_alias).as_(sdts_col),
        ]

        # Build per-satellite expressions
        sat_joins: list[tuple] = []

        for sat in self.sat_configs:
            sat_ldts = sat.ldts or ldts_col
            sat_ledts_col = sat.ledts  # None means we need to compute via LEAD
            sat_alias = sat.name
            sat_tbl_exp = self._get_table_expression(
                sat.table_name, sat.schema_name, sat.database
            )

            if sat_ledts_col:
                # Satellite already has ledts column — join directly
                join_subq = exp.select(
                    exp.column(sat.hashkey),
                    exp.column(sat_ldts),
                    exp.column(sat_ledts_col),
                ).from_(sat_tbl_exp)
                sat_source = exp.Subquery(
                    this=join_subq,
                    alias=exp.TableAlias(this=exp.Identifier(this=sat_alias)),
                )
                sat_ldts_col_in_join = sat_ledts_col
            else:
                # Compute ledts via LEAD
                lead_w = exp.Window(
                    this=exp.Lead(this=exp.column(sat_ldts)),
                    partition_by=[exp.column(sat.hashkey)],
                    order=exp.Order(
                        expressions=[exp.Ordered(this=exp.column(sat_ldts))]
                    ),
                )
                ledts_computed = exp.Coalesce(
                    this=lead_w,
                    expressions=[exp.Literal.string(eoa)],
                ).as_(exp.Identifier(this=ledts_col, quoted=True))

                join_subq = exp.select(
                    exp.column(sat.hashkey),
                    exp.column(sat_ldts),
                    ledts_computed,
                ).from_(sat_tbl_exp)
                sat_source = exp.Subquery(
                    this=join_subq,
                    alias=exp.TableAlias(this=exp.Identifier(this=sat_alias)),
                )
                sat_ldts_col_in_join = ledts_col

            # JOIN condition: sat.hk = te.hk AND snap.sdts BETWEEN sat.ldts AND sat.ledts
            join_on = exp.and_(
                exp.column(sat.hashkey, table=sat_alias).eq(
                    exp.column(hk_col, table=te_alias)
                ),
                exp.Between(
                    this=exp.column(sdts_col, table=snap_alias),
                    low=exp.column(sat_ldts, table=sat_alias),
                    high=exp.column(sat_ldts_col_in_join, table=sat_alias),
                ),
            )
            sat_joins.append((sat_source, join_on, sat_alias, sat_ldts, sat.hashkey))

            # Columns for this satellite in the SELECT
            if self.refer_to_ghost_records:
                hex_len = 64 if config.hash.upper() == "SHA256" else 32
                unknown_key = "0" * hex_len
                pit_cols.append(
                    exp.Coalesce(
                        this=exp.column(sat.hashkey, table=sat_alias),
                        expressions=[exp.Literal.string(unknown_key)],
                    ).as_(f"hk_{sat_alias}")
                )
                pit_cols.append(
                    exp.Coalesce(
                        this=exp.column(sat_ldts, table=sat_alias),
                        expressions=[exp.Literal.string(boa)],
                    ).as_(f"{ldts_col}_{sat_alias}")
                )
            else:
                pit_cols.append(
                    exp.column(sat.hashkey, table=sat_alias).as_(f"hk_{sat_alias}")
                )
                pit_cols.append(
                    exp.column(sat_ldts, table=sat_alias).as_(f"{ldts_col}_{sat_alias}")
                )

        # Build the FROM + JOINs
        pit_query = exp.select(*pit_cols).from_(te_tbl)

        # FULL OUTER JOIN snapshots ON 1=1
        pit_query = pit_query.join(
            snap_tbl,
            on=exp.Literal.number(1).eq(exp.Literal.number(1)),
            join_type="FULL OUTER",
        )

        # LEFT JOIN each satellite
        for sat_source, join_on, *_ in sat_joins:
            pit_query = pit_query.join(sat_source, on=join_on, join_type="LEFT")

        ctes["pit_records"] = pit_query

        # ---------------------------------------------------------
        # 3. records_to_insert — deduplicate against existing keys
        # ---------------------------------------------------------
        if self.is_incremental:
            insert_query = (
                exp.select("*")
                .distinct()
                .from_("pit_records")
                .where(
                    exp.column(dim_key_col)
                    .isin(
                        exp.select(exp.column(dim_key_col)).from_("existing_dimension_keys")
                    )
                    .not_()
                )
                .order_by(exp.column(sdts_col))
            )
        else:
            insert_query = (
                exp.select("*")
                .distinct()
                .from_("pit_records")
                .order_by(exp.column(sdts_col))
            )

        ctes["records_to_insert"] = insert_query

        # ---------------------------------------------------------
        # 4. Final SELECT + assemble CTEs
        # ---------------------------------------------------------
        final_query = exp.select("*").from_("records_to_insert")
        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)

        return final_query
