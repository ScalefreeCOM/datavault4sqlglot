from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from sqlglot import exp

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.base import BaseGenerator


@dataclass
class PitSatellite:
    """
    Defines one satellite to include in a PIT table.

    Args:
        sat_table:      Satellite table name.
        hub_hash_key:   Hash key column in the satellite that links back to the hub.
        sat_schema:     Optional schema override.
        sat_database:   Optional database override.
        alias:          Output column alias for the captured ldts value.
                        Defaults to ``<sat_table>_ldts``.
    """

    sat_table: str
    hub_hash_key: str
    sat_schema: Optional[str] = None
    sat_database: Optional[str] = None
    alias: Optional[str] = None

    def __post_init__(self) -> None:
        if self.alias is None:
            self.alias = f"{self.sat_table}_ldts"


class PITGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Point-in-Time (PIT) table.

    A PIT table provides a snapshot of which satellite records were valid at
    each point in time for a given hub entity. For each hub key × snapshot date
    combination it looks up the ``MAX(ldts)`` of every configured satellite
    where ``ldts <= snapshot_date``, falling back to ``beginning_of_all_times``
    when no record exists (ghost record).

    The generated query:
        SELECT  h.<hub_hash_key>,
                snaps.<snapshot_date_col>,
                COALESCE((SELECT MAX(ldts) FROM sat0 WHERE hk=h.hk AND ldts<=snap.dt), boa) AS sat0_ldts,
                ...
        FROM    <hub_table>  h
        CROSS JOIN <snapshot_table> snaps

    Args:
        target_table:       Target PIT table name.
        hub_table:          Hub table to use as the driver.
        hub_hash_key:       Hash key column in the hub.
        satellites:         List of PitSatellite definitions.
        snapshot_table:     Table containing snapshot dates.
        snapshot_date_col:  Date column in the snapshot table.
        beginning_of_all_times: Ghost record sentinel (overrides config).
    """

    def __init__(
        self,
        target_table: str,
        hub_table: str,
        hub_hash_key: str,
        satellites: List[PitSatellite],
        snapshot_table: str,
        snapshot_date_col: str = "snapshot_date",
        hub_schema: Optional[str] = None,
        hub_database: Optional[str] = None,
        snapshot_schema: Optional[str] = None,
        snapshot_database: Optional[str] = None,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        end_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.hub_table = hub_table
        self.hub_hash_key = hub_hash_key
        self.satellites = satellites
        self.snapshot_table = snapshot_table
        self.snapshot_date_col = snapshot_date_col
        self.hub_schema = hub_schema
        self.hub_database = hub_database
        self.snapshot_schema = snapshot_schema
        self.snapshot_database = snapshot_database
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times
        self.end_of_all_times = end_of_all_times or config.end_of_all_times

    def generate_sql(self) -> exp.Expression:
        hub_hk = self.hub_hash_key
        snap_col = self.snapshot_date_col
        ldts_col = config.ldts_alias
        boa = self.beginning_of_all_times
        eoa = self.end_of_all_times

        hub_exp = self._get_table_with_alias(
            self.hub_table, "h", self.hub_schema, self.hub_database
        )
        snap_exp = self._get_table_with_alias(
            self.snapshot_table, "snaps", self.snapshot_schema, self.snapshot_database
        )

        # ------------------------------------------------------------------
        # Build SELECT list: h.hub_hk, snaps.snap_col, + one subquery per sat
        # ------------------------------------------------------------------
        select_cols: list[exp.Expression] = [
            exp.column(hub_hk, "h"),
            exp.column(snap_col, "snaps"),
        ]

        for sat in self.satellites:
            sat_exp = self._get_table_with_alias(
                sat.sat_table, f"s_{sat.sat_table}", sat.sat_schema, sat.sat_database
            )
            # Correlated subquery: SELECT COALESCE(MAX(ldts), boa) FROM sat WHERE hk = h.hk AND ldts <= snaps.snap_col
            subq = (
                exp.select(
                    exp.Coalesce(
                        this=exp.Max(this=exp.column(ldts_col)),
                        expressions=[exp.Literal.string(boa)],
                    )
                )
                .from_(sat_exp)
                .where(
                    exp.and_(
                        exp.column(sat.hub_hash_key, f"s_{sat.sat_table}").eq(
                            exp.column(hub_hk, "h")
                        ),
                        exp.column(ldts_col, f"s_{sat.sat_table}")
                        <= exp.column(snap_col, "snaps"),
                        exp.column(ldts_col, f"s_{sat.sat_table}").neq(
                            exp.Literal.string(eoa)
                        ),
                    )
                )
            )
            select_cols.append(exp.Paren(this=subq).as_(sat.alias))

        # ------------------------------------------------------------------
        # Final SELECT: hub CROSS JOIN snapshots
        # ------------------------------------------------------------------
        query = (
            exp.select(*select_cols)
            .from_(hub_exp)
            .join(snap_exp, join_type="CROSS")
        )

        return query
