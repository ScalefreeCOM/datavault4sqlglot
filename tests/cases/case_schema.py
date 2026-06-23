"""
Pydantic schema for data-driven Data Vault test cases.

A *case* is the data form of one hand-written execution test: it carries the
data (current state + input + expected output) and the entity configuration,
while the mechanics (seed → generate → run → compare) live in the runner.

This module is pure data + validation — it imports neither DuckDB nor sqlglot.
The canonical fields mirror the test-spec hierarchy in the team's Excel
(``datavault4sqlglot test cases.xlsx``); each case file is named after its
spec id (e.g. ``hub/2_2_2_3.yml``).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Entity(str, Enum):
    """Which generator a case targets."""

    hub = "hub"
    link = "link"
    satellite = "satellite"
    satellite_v1 = "satellite_v1"


class Mode(str, Enum):
    """Load mode — maps to the generator's ``is_incremental`` flag."""

    initial = "initial"
    incremental = "incremental"


class MatchMode(str, Enum):
    """How the runner compares actual rows against ``expect``."""

    set = "set"          # set of key-column tuples (order/dup independent)
    exact = "exact"      # multiset of key-column tuples (counts matter)
    subset = "subset"    # expected ⊆ actual (on key columns)
    count = "count"      # only the row count matters
    empty = "empty"      # no rows expected


class TargetSpec(BaseModel):
    """Physical target table the entity loads into."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    database: Optional[str] = None
    schema_name: Optional[str] = Field(default=None, alias="schema")
    table: str


class SourceSpec(BaseModel):
    """
    One staging source plus its per-source DV loading metadata.

    Maps onto a ``SourceModel`` (the physical reference) wrapped in a
    ``SourceBinding`` (the per-source extraction metadata).
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    database: Optional[str] = None
    schema_name: Optional[str] = Field(default=None, alias="schema")
    table: str
    load_date_col: Optional[str] = None
    record_source_col: Optional[str] = None

    # Per-source physical columns; map positionally to the entity-level names.
    # Omit (→ None) when the source already uses the canonical names — passing
    # [] would trip the generator's length check.
    bk_columns: Optional[list[str]] = None
    fk_columns: Optional[list[str]] = None
    hash_key_col: Optional[str] = None
    payload: Optional[list[str]] = None
    rsrc_statics: Optional[list[str]] = None
    additional_columns: Optional[list[str]] = None


class EntitySpec(BaseModel):
    """
    Generator wiring for a case. Which fields are required depends on
    ``Case.entity`` — enforced by ``Case`` below, not here, so the schema stays
    open for future entities.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    target: TargetSpec

    # hub / link: multiple sources
    sources: Optional[list[SourceSpec]] = None
    # satellite: a single source
    source: Optional[SourceSpec] = None

    # hub
    hashkey: Optional[str] = None
    business_keys: Optional[list[str]] = None
    # link
    link_hash_key: Optional[str] = None
    foreign_hash_keys: Optional[list[str]] = None
    # satellite
    parent_hash_key: Optional[str] = None
    hash_diff: Optional[Any] = None          # str or {alias: expr}
    source_is_single_batch: Optional[bool] = None
    # satellite_v1
    sat_v0: Optional[TargetSpec] = None

    # shared
    payload: Optional[list[str]] = None
    additional_columns: Optional[list[str]] = None
    disable_hwm: Optional[bool] = None


class TableState(BaseModel):
    """A table plus the rows to seed into it."""

    model_config = ConfigDict(extra="forbid")

    table: str
    rows: list[dict[str, Any]]


class ExpectSpec(BaseModel):
    """The assertion: comparison mode + the expected output."""

    model_config = ConfigDict(extra="forbid")

    match_mode: MatchMode = MatchMode.set
    key_columns: Optional[list[str]] = None
    rows: Optional[list[dict[str, Any]]] = None
    count: Optional[int] = None

    @model_validator(mode="after")
    def _check_required_for_mode(self) -> "ExpectSpec":
        if self.match_mode in (MatchMode.set, MatchMode.exact, MatchMode.subset):
            if self.rows is None:
                raise ValueError(
                    f"expect.match_mode '{self.match_mode.value}' requires 'rows'"
                )
        if self.match_mode == MatchMode.count and self.count is None:
            raise ValueError("expect.match_mode 'count' requires 'count'")
        return self


class Case(BaseModel):
    """One data-driven test case."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str
    title: str = ""
    entity: Entity
    mode: Mode
    dialect: str = "duckdb"
    config: dict[str, Any] = Field(default_factory=dict)
    entity_spec: EntitySpec
    current_state: list[TableState] = Field(default_factory=list)
    input: list[TableState]
    expect: ExpectSpec

    @model_validator(mode="after")
    def _check_entity_requirements(self) -> "Case":
        es = self.entity_spec
        if self.entity == Entity.hub:
            if not es.sources:
                raise ValueError("hub case requires entity_spec.sources")
            if not es.hashkey:
                raise ValueError("hub case requires entity_spec.hashkey")
            if not es.business_keys:
                raise ValueError("hub case requires entity_spec.business_keys")
        elif self.entity == Entity.link:
            if not es.sources:
                raise ValueError("link case requires entity_spec.sources")
            if not es.link_hash_key:
                raise ValueError("link case requires entity_spec.link_hash_key")
            if not es.foreign_hash_keys:
                raise ValueError("link case requires entity_spec.foreign_hash_keys")
        elif self.entity == Entity.satellite:
            if not es.source:
                raise ValueError("satellite case requires entity_spec.source (single)")
            if not es.parent_hash_key:
                raise ValueError("satellite case requires entity_spec.parent_hash_key")
            if not es.hash_diff:
                raise ValueError("satellite case requires entity_spec.hash_diff")
        elif self.entity == Entity.satellite_v1:
            if not es.sat_v0:
                raise ValueError("satellite_v1 case requires entity_spec.sat_v0")
            if not es.parent_hash_key:
                raise ValueError("satellite_v1 case requires entity_spec.parent_hash_key")
            if not es.hash_diff:
                raise ValueError("satellite_v1 case requires entity_spec.hash_diff")
        return self
