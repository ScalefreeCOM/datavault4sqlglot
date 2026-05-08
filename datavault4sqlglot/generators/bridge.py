from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from sqlglot import exp

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.base import BaseGenerator


@dataclass
class BridgeLink:
    """
    Defines one link leg to traverse in a Bridge table.

    Args:
        link_table:         NH link or historized link table name.
        link_hash_key:      The link's own hash key column.
        driving_hash_key:   Foreign hash key connecting back to the hub
                            (the join condition to the hub).
        foreign_hash_keys:  Other foreign hash keys to surface in the bridge.
        link_schema:        Optional schema override.
        link_database:      Optional database override.
        eff_sat_table:      Optional effectivity satellite to filter active records.
                            When set, only records where the relationship was active
                            at the snapshot date are included.
        eff_sat_hash_key:   Hash key in the eff_sat that matches link_hash_key.
                            Defaults to ``link_hash_key``.
        eff_sat_schema:     Optional schema override for eff_sat.
        eff_sat_database:   Optional database override for eff_sat.
    """

    link_table: str
    link_hash_key: str
    driving_hash_key: str
    foreign_hash_keys: List[str]
    link_schema: Optional[str] = None
    link_database: Optional[str] = None
    eff_sat_table: Optional[str] = None
    eff_sat_hash_key: Optional[str] = None
    eff_sat_schema: Optional[str] = None
    eff_sat_database: Optional[str] = None

    def __post_init__(self) -> None:
        if self.eff_sat_hash_key is None:
            self.eff_sat_hash_key = self.link_hash_key


class BridgeGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Bridge table.

    A Bridge table traverses one or more Links from a central Hub, joining
    them via CROSS JOIN with a snapshot date table. For each snapshot it
    exposes the link hash keys and foreign hash keys that were active at that
    point in time.

    Optional effectivity satellite filtering ensures only active relationships
    (``is_active = TRUE`` at the snapshot date) appear in the output.

    The generated query:
        SELECT h.<hub_hk>, snaps.<snap_col>,
               l0.<link_hk>, l0.<fk1>, ...,
               ...
        FROM   <hub> h
        CROSS JOIN <snapshot_table> snaps
        LEFT JOIN  <link0> l0
               ON  l0.<driving_hk> = h.<hub_hk>
               AND l0.ldts <= snaps.<snap_col>
        [LEFT JOIN <eff_sat0> e0
               ON  e0.<eff_sat_hk> = l0.<link_hk>
               AND e0.ldts <= snaps.<snap_col>
               AND e0.ledts > snaps.<snap_col>]
        ...

    Args:
        target_table:       Target bridge table name.
        hub_table:          Hub driving the bridge.
        hub_hash_key:       Hash key column in the hub.
        links:              Ordered list of BridgeLink definitions.
        snapshot_table:     Table containing snapshot dates.
        snapshot_date_col:  Date column in the snapshot table.
        beginning_of_all_times: BOA sentinel.
        end_of_all_times:   EOA sentinel (for ledts comparison).
    """

    def __init__(
        self,
        target_table: str,
        hub_table: str,
        hub_hash_key: str,
        links: List[BridgeLink],
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
        self.links = links
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
        ledts_col = config.ledts_alias
        eoa = self.end_of_all_times

        hub_exp = self._get_table_with_alias(
            self.hub_table, "h", self.hub_schema, self.hub_database
        )
        snap_exp = self._get_table_with_alias(
            self.snapshot_table, "snaps", self.snapshot_schema, self.snapshot_database
        )

        # ------------------------------------------------------------------
        # Build SELECT list
        # ------------------------------------------------------------------
        select_cols: list[exp.Expression] = [
            exp.column(hub_hk, "h"),
            exp.column(snap_col, "snaps"),
        ]

        joins: list[exp.Join] = []

        for idx, link in enumerate(self.links):
            l_alias = f"l{idx}"
            link_exp = self._get_table_with_alias(
                link.link_table, l_alias, link.link_schema, link.link_database
            )

            # Surface link hash key + foreign hash keys
            select_cols.append(exp.column(link.link_hash_key, l_alias))
            for fhk in link.foreign_hash_keys:
                select_cols.append(exp.column(fhk, l_alias))

            # LEFT JOIN link ON l.driving_hk = h.hub_hk AND l.ldts <= snaps.snap_col
            join_cond = exp.and_(
                exp.column(link.driving_hash_key, l_alias).eq(
                    exp.column(hub_hk, "h")
                ),
                exp.column(ldts_col, l_alias) <= exp.column(snap_col, "snaps"),
            )
            joins.append(
                exp.Join(this=link_exp, on=join_cond, kind="LEFT")
            )

            # Optional effectivity satellite filter
            if link.eff_sat_table:
                e_alias = f"e{idx}"
                eff_exp = self._get_table_with_alias(
                    link.eff_sat_table, e_alias, link.eff_sat_schema, link.eff_sat_database
                )
                eff_hk = link.eff_sat_hash_key
                eff_join_cond = exp.and_(
                    exp.column(eff_hk, e_alias).eq(
                        exp.column(link.link_hash_key, l_alias)
                    ),
                    exp.column(ldts_col, e_alias) <= exp.column(snap_col, "snaps"),
                    exp.column(ledts_col, e_alias) > exp.column(snap_col, "snaps"),
                )
                joins.append(
                    exp.Join(this=eff_exp, on=eff_join_cond, kind="LEFT")
                )

        # ------------------------------------------------------------------
        # Assemble: FROM hub CROSS JOIN snaps [+ left joins]
        # ------------------------------------------------------------------
        query = (
            exp.select(*select_cols)
            .from_(hub_exp)
            .join(snap_exp, join_type="CROSS")
        )
        for j in joins:
            query = query.join(j)

        return query
